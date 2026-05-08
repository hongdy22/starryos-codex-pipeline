#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from artifacts import capture_git_artifacts, write_pr_body_draft, write_round_summary, write_verification
from hooks import HookRunner


PIPELINE = Path(__file__).resolve().parents[1]
ROOT = PIPELINE.parent
PROMPTS = PIPELINE / "prompts"
SCHEMAS = PIPELINE / "schemas"
RESULTS = PIPELINE / "results"
RESULT_STATE = RESULTS / "state"
ROUNDS = RESULTS / "rounds"


class PipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cmd(
    cmd: list[str],
    cwd: Path,
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
        env=env,
        timeout=timeout,
    )


def load_config(path: Path) -> dict[str, Any]:
    config = read_json(path)
    if not isinstance(config, dict):
        raise PipelineError(f"invalid config JSON: {path}")
    return config


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (ROOT / path).resolve()


def as_path(config: dict[str, Any], key: str) -> Path:
    value = os.environ.get(key.upper()) or config.get(key)
    if not value:
        raise PipelineError(f"missing config key: {key}")
    return resolve_repo_path(value)


def safe_extract_single_codex(tar_path: Path, dest_dir: Path, expected_name: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members if m.isfile()]
        if expected_name not in names:
            if len(names) != 1:
                raise PipelineError(f"cannot identify Codex binary in {tar_path}: {names}")
            expected_name = names[0]
        member = archive.getmember(expected_name)
        target = dest_dir / Path(member.name).name
        with archive.extractfile(member) as src:
            if src is None:
                raise PipelineError(f"failed to extract {member.name} from {tar_path}")
            target.write_bytes(src.read())
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return target


def prepare_codex(config: dict[str, Any]) -> tuple[Path, dict[str, str]]:
    codex_bin = resolve_repo_path(os.environ.get("CODEX_BIN", config["codex_bin"]))
    if not codex_bin.exists():
        tar_path = as_path(config, "codex_tar")
        if not tar_path.exists():
            raise PipelineError(f"Codex binary missing and tarball not found: {tar_path}")
        codex_bin = safe_extract_single_codex(
            tar_path,
            codex_bin.parent,
            codex_bin.name,
        )
    if not os.access(codex_bin, os.X_OK):
        codex_bin.chmod(codex_bin.stat().st_mode | stat.S_IXUSR)

    auth_source = resolve_repo_path(os.environ.get("CODEX_AUTH_JSON", config["codex_auth_json"]))
    if not auth_source.exists():
        raise PipelineError(f"Codex auth file not found: {auth_source}")

    codex_home = resolve_repo_path(os.environ.get("CODEX_HOME", config["codex_home"]))
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_dest = codex_home / "auth.json"
    if auth_source != auth_dest:
        shutil.copyfile(auth_source, auth_dest)
    auth_dest.chmod(0o600)

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    return codex_bin, env


def git_snapshot(project_root: Path) -> dict[str, str]:
    commands = {
        "status": ["git", "status", "--short"],
        "branch": ["git", "branch", "--show-current"],
        "head": ["git", "rev-parse", "--short", "HEAD"],
    }
    snapshot: dict[str, str] = {}
    for key, cmd in commands.items():
        proc = run_cmd(cmd, project_root)
        if proc.returncode == 0:
            snapshot[key] = proc.stdout.strip()
        else:
            snapshot[key] = f"ERROR({proc.returncode}): {proc.stderr.strip()}"
    return snapshot


def build_developer_prompt(
    config: dict[str, Any],
    round_no: int,
    previous_review: dict[str, Any] | None,
) -> str:
    project_root = as_path(config, "project_root")
    snapshot = git_snapshot(project_root)
    previous_review_block = (
        json.dumps(previous_review, ensure_ascii=False, indent=2) if previous_review else "无上一轮 reviewer 反馈。"
    )
    journal_block = read_text(RESULT_STATE / "journal.md", "暂无已完成轮次。")[:12000]

    return f"""{read_text(PROMPTS / "developer_role.md")}

{read_text(PROMPTS / "shared_main.md")}

# 当前业务目标
{read_text(PROMPTS / "goal.md")}

# 当前策略状态
{json.dumps(read_json(PROMPTS / "strategy.json", {}), ensure_ascii=False, indent=2)}

# 已完成轮次摘要
{journal_block}

# 当前轮次
round = {round_no}

# 当前 tgoskits 轻量 git 状态
branch = {snapshot.get("branch", "")}
head = {snapshot.get("head", "")}

## git status --short
{snapshot.get("status", "") or "(clean)"}

说明：prompt 中不内嵌 git diff。你需要审查代码状态时，请自己运行 `git status`、`git diff --stat`、`git diff` 或针对具体文件的读取命令。

# 上一轮 reviewer 结论
{previous_review_block}

# Developer 输出要求
- 严格输出符合 `pipeline/schemas/developer.json` 的 JSON。
- 如果本轮修改代码，必须在 `changed_files`、`commands_run`、`evidence` 中写清楚。
- 如果证据链未闭合，必须在 `summary`、`evidence`、`next_action` 中写清楚缺口。
- 如果上一轮或 journal 中某个 target 已经 `PASS`，不要重复选择同一个 target；已通过但尚未提交的源码改动视为当前基线。
- 不要输出 Markdown，不要输出 schema 之外的字段。
"""


def build_reviewer_prompt(
    config: dict[str, Any],
    round_no: int,
    developer_output: dict[str, Any],
) -> str:
    project_root = as_path(config, "project_root")
    snapshot = git_snapshot(project_root)

    return f"""{read_text(PROMPTS / "reviewer_role.md")}

{read_text(PROMPTS / "shared_main.md")}

# 当前业务目标
{read_text(PROMPTS / "goal.md")}

# 当前轮次
round = {round_no}

# Developer 结构化输出
{json.dumps(developer_output, ensure_ascii=False, indent=2)}

# 当前 tgoskits 轻量 git 状态
branch = {snapshot.get("branch", "")}
head = {snapshot.get("head", "")}

## git status --short
{snapshot.get("status", "") or "(clean)"}

说明：prompt 中不内嵌 git diff。你需要审查代码状态时，请自己运行 `git status`、`git diff --stat`、`git diff` 或针对具体文件的读取命令。

# Reviewer 输出要求
- 严格输出符合 `pipeline/schemas/reviewer.json` 的 JSON。
- 若证据不足、测试不足、Linux 基准不足、回归不足、补丁风险未解释，必须返回 `REVISE` 或 `REJECT`。
- `next_prompt_to_developer` 必须写成下一轮可以直接交给 Developer 的整改要求。
- 你可以执行验证命令，但不要留下对 Developer 正式补丁、正式测试或仓库源码的修改。
- 如果你为了验证临时改了文件，结束前必须只恢复你自己造成的改动，并在 JSON 输出中说明。
- 不要输出 Markdown，不要输出 schema 之外的字段。
"""


def load_agent_output(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PipelineError(f"missing Codex output file: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"invalid JSON in {path}: {exc}\n{raw[:1000]}") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"expected JSON object in {path}, got {type(data).__name__}")
    return data


def run_codex_role(
    *,
    config: dict[str, Any],
    codex_bin: Path,
    codex_env: dict[str, str],
    role_name: str,
    prompt: str,
    schema_path: Path,
    output_path: Path,
    event_log_path: Path,
) -> dict[str, Any]:
    role_config = config[role_name]
    project_root = as_path(config, "project_root")
    model = os.environ.get(f"{role_name.upper()}_MODEL") or os.environ.get("CODEX_MODEL") or role_config["model"]
    effort = (
        os.environ.get(f"{role_name.upper()}_REASONING_EFFORT")
        or os.environ.get("CODEX_REASONING_EFFORT")
        or role_config.get("reasoning_effort", "high")
    )
    service_tier = (
        os.environ.get(f"{role_name.upper()}_SERVICE_TIER")
        or os.environ.get("CODEX_SERVICE_TIER")
        or role_config.get("service_tier", "auto")
    )

    cmd = [
        str(codex_bin),
        "exec",
        "--cd",
        str(project_root),
        "--skip-git-repo-check",
        "--model",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "-c",
        f'service_tier="{service_tier}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "--json",
        "--color",
        "never",
    ]
    if role_config.get("ephemeral", True):
        cmd.append("--ephemeral")
    if role_config.get("full_access"):
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        cmd.extend(["--sandbox", role_config.get("sandbox", "read-only")])
    cmd.append("-")

    print(f"[{role_name}] RUN: {' '.join(cmd[:-1])} -", file=sys.stderr)
    proc = run_cmd(cmd, project_root, input_text=prompt, env=codex_env)
    write_text(event_log_path, proc.stdout)
    if proc.stderr:
        write_text(event_log_path.with_suffix(event_log_path.suffix + ".stderr"), proc.stderr)
    if proc.returncode != 0:
        raise PipelineError(
            f"Codex {role_name} failed with code {proc.returncode}; "
            f"see {event_log_path} and {event_log_path}.stderr"
        )
    return load_agent_output(output_path)


def append_journal(round_no: int, developer: dict[str, Any], reviewer: dict[str, Any]) -> None:
    journal = RESULT_STATE / "journal.md"
    existing = read_text(journal, "# StarryOS AI Pipeline Journal\n\n---\n")
    entry = f"""## {utc_now()} round-{round_no:03d}

- target: {developer.get("target", "")}
- developer: {developer.get("summary", "")}
- reviewer decision: {reviewer.get("decision", "")}
- reviewer: {reviewer.get("summary", "")}

"""
    marker = "---\n"
    if marker in existing:
        head, tail = existing.split(marker, 1)
        write_text(journal, head + marker + "\n" + entry + tail.lstrip())
    else:
        write_text(journal, existing.rstrip() + "\n\n" + entry)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Codex-only StarryOS improvement loop.")
    parser.add_argument("--config", type=Path, default=PIPELINE / "config.json")
    parser.add_argument("--max-rounds", type=int, default=int(os.environ.get("MAX_ROUNDS", "3")))
    parser.add_argument("--dry-run", action="store_true", help="Generate prompts and state without invoking Codex.")
    parser.add_argument("--start-round", type=int, default=None, help="Override next round number.")
    parser.add_argument(
        "--continue-after-pass",
        action="store_true",
        help="Keep running until max-rounds even when a round receives PASS.",
    )
    args = parser.parse_args()

    config = load_config(args.config.resolve())
    project_root = as_path(config, "project_root")
    if not project_root.exists():
        raise PipelineError(f"project_root does not exist: {project_root}")
    if not as_path(config, "starryos_root").exists():
        raise PipelineError(f"starryos_root does not exist: {as_path(config, 'starryos_root')}")
    hook_runner = HookRunner(root=ROOT, pipeline=PIPELINE, config=config)
    preflight = hook_runner.run("preflight", dry_run=args.dry_run)
    if hook_runner.has_blocking_failure(preflight):
        raise PipelineError(f"preflight failed: {json.dumps(preflight, ensure_ascii=False)}")

    ROUNDS.mkdir(parents=True, exist_ok=True)
    RESULT_STATE.mkdir(parents=True, exist_ok=True)
    loop_state_path = RESULT_STATE / "loop_state.json"
    loop_state = read_json(loop_state_path, default={"last_round": 0, "status": "idle"})
    previous_review: dict[str, Any] | None = None

    if args.start_round is not None:
        first_round = args.start_round
    else:
        first_round = int(loop_state.get("last_round", 0)) + 1

    previous_review_path = ROUNDS / f"round-{first_round - 1:03d}" / "reviewer_output.json"
    if first_round > 1 and previous_review_path.exists():
        previous_review = read_json(previous_review_path)

    codex_bin: Path | None = None
    codex_env: dict[str, str] | None = None
    if not args.dry_run:
        codex_bin, codex_env = prepare_codex(config)

    for round_no in range(first_round, first_round + args.max_rounds):
        round_dir = ROUNDS / f"round-{round_no:03d}"
        round_dir.mkdir(parents=True, exist_ok=True)

        dev_prompt = build_developer_prompt(
            config,
            round_no,
            previous_review,
        )
        write_text(round_dir / "developer_prompt.txt", dev_prompt)

        if args.dry_run:
            dry_dev = {
                "round": round_no,
                "role": "DEVELOPER",
                "target": "DRY_RUN",
                "summary": "Prompt generated only; Codex was not invoked.",
                "priority_score": 0,
                "linux_baseline": [],
                "tests": [],
                "commands_run": [],
                "evidence": [],
                "changed_files": [],
                "risks": [],
                "reviewer_focus": [],
                "next_action": "Run without --dry-run to invoke Codex.",
            }
            write_json(round_dir / "developer_output.json", dry_dev)
            write_json(
                round_dir / "dry_run_state.json",
                {
                    "last_round": round_no,
                    "status": "dry-run",
                    "current_target": "DRY_RUN",
                    "updated_at": utc_now(),
                    "round_dir": str(round_dir.relative_to(ROOT)),
                },
            )
            write_verification(round_dir, {"hooks": {"preflight": preflight}, "dry_run": True})
            write_round_summary(
                round_dir=round_dir,
                round_no=round_no,
                developer=dry_dev,
                reviewer=None,
                hooks={"preflight": preflight},
                artifacts={},
            )
            print(json.dumps(dry_dev, ensure_ascii=False, indent=2))
            return 0

        assert codex_bin is not None and codex_env is not None
        hook_results: dict[str, Any] = {"preflight": preflight}
        artifact_results: dict[str, Any] = {}
        developer_output = run_codex_role(
            config=config,
            codex_bin=codex_bin,
            codex_env=codex_env,
            role_name="developer",
            prompt=dev_prompt,
            schema_path=SCHEMAS / "developer.json",
            output_path=round_dir / "developer_output.json",
            event_log_path=round_dir / "developer_events.jsonl",
        )
        developer_artifacts = capture_git_artifacts(project_root, round_dir, "developer")
        artifact_results["developer_git"] = developer_artifacts
        hook_results["post_developer"] = hook_runner.run(
            "post_developer",
            round_dir=round_dir,
            schema_path=SCHEMAS / "developer.json",
            output_path=round_dir / "developer_output.json",
        )
        developer_diff_hash = developer_artifacts["diff_hash"]

        reviewer_prompt = build_reviewer_prompt(config, round_no, developer_output)
        write_text(round_dir / "reviewer_prompt.txt", reviewer_prompt)

        reviewer_output = run_codex_role(
            config=config,
            codex_bin=codex_bin,
            codex_env=codex_env,
            role_name="reviewer",
            prompt=reviewer_prompt,
            schema_path=SCHEMAS / "reviewer.json",
            output_path=round_dir / "reviewer_output.json",
            event_log_path=round_dir / "reviewer_events.jsonl",
        )
        reviewer_artifacts = capture_git_artifacts(project_root, round_dir, "reviewer")
        artifact_results["reviewer_git"] = reviewer_artifacts
        hook_results["post_reviewer"] = hook_runner.run(
            "post_reviewer",
            round_dir=round_dir,
            schema_path=SCHEMAS / "reviewer.json",
            output_path=round_dir / "reviewer_output.json",
            developer_diff_hash=developer_diff_hash,
        )

        decision = reviewer_output["decision"]
        if decision == "PASS":
            hook_results["on_pass"] = hook_runner.run("on_pass", round_dir=round_dir)
            artifact_results["pr_body_draft"] = write_pr_body_draft(round_dir, developer_output, reviewer_output)

        write_verification(
            round_dir,
            {
                "round": round_no,
                "target": developer_output.get("target", ""),
                "decision": decision,
                "hooks": hook_results,
                "artifacts": artifact_results,
            },
        )
        write_round_summary(
            round_dir=round_dir,
            round_no=round_no,
            developer=developer_output,
            reviewer=reviewer_output,
            hooks=hook_results,
            artifacts=artifact_results,
        )

        loop_state = {
            "last_round": round_no,
            "status": decision,
            "current_target": developer_output.get("target", ""),
            "updated_at": utc_now(),
            "round_dir": str(round_dir.relative_to(ROOT)),
        }
        write_json(loop_state_path, loop_state)
        append_journal(round_no, developer_output, reviewer_output)

        print(
            json.dumps(
                {
                    "round": round_no,
                    "target": developer_output.get("target", ""),
                    "decision": decision,
                    "summary": reviewer_output.get("summary", ""),
                    "round_dir": str(round_dir.relative_to(ROOT)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        if decision == "PASS" and not args.continue_after_pass:
            return 0
        previous_review = reviewer_output

    if args.continue_after_pass:
        print("Reached max rounds in continue-after-pass mode.", file=sys.stderr)
        return 0
    print("Reached max rounds without PASS.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
