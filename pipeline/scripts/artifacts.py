#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from checks import git_diff_hash, git_snapshot


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture_git_artifacts(project_root: Path, round_dir: Path, prefix: str) -> dict[str, Any]:
    snapshot = git_snapshot(project_root)
    outputs = {
        "status": run_cmd(["git", "status", "--short"], project_root),
        "diff_stat": run_cmd(["git", "diff", "--stat"], project_root),
        "changed_files": run_cmd(["git", "diff", "--name-only"], project_root),
        "patch": run_cmd(["git", "diff", "--binary"], project_root),
    }
    paths = {
        "status": round_dir / f"{prefix}_git_status.txt",
        "diff_stat": round_dir / f"{prefix}_diff_stat.txt",
        "changed_files": round_dir / f"{prefix}_changed_files.txt",
        "patch": round_dir / f"{prefix}.patch",
    }
    for key, proc in outputs.items():
        text = proc.stdout if proc.returncode == 0 else proc.stderr
        write_text(paths[key], text)
    return {
        "prefix": prefix,
        "diff_hash": git_diff_hash(project_root),
        "snapshot": snapshot,
        "files": {key: str(path) for key, path in paths.items()},
    }


def write_verification(round_dir: Path, verification: dict[str, Any]) -> None:
    write_json(round_dir / "verification.json", verification)


def write_round_summary(
    *,
    round_dir: Path,
    round_no: int,
    developer: dict[str, Any] | None,
    reviewer: dict[str, Any] | None,
    hooks: dict[str, Any],
    artifacts: dict[str, Any],
) -> None:
    developer = developer or {}
    reviewer = reviewer or {}
    lines = [
        f"# round-{round_no:03d}",
        "",
        f"- target: {developer.get('target', '')}",
        f"- developer summary: {developer.get('summary', '')}",
        f"- reviewer decision: {reviewer.get('decision', '')}",
        f"- reviewer summary: {reviewer.get('summary', '')}",
        "",
        "## Evidence",
    ]
    for item in developer.get("evidence", []):
        lines.append(f"- {item}")
    if not developer.get("evidence"):
        lines.append("- No developer evidence recorded.")
    lines.extend(["", "## Commands"])
    for item in developer.get("commands_run", []):
        lines.append(f"- `{item}`")
    if not developer.get("commands_run"):
        lines.append("- No developer commands recorded.")
    lines.extend(["", "## Changed Files"])
    for item in developer.get("changed_files", []):
        lines.append(f"- `{item}`")
    if not developer.get("changed_files"):
        lines.append("- No developer changed files recorded.")
    lines.extend(["", "## Hook Results"])
    for hook_name, hook_result in hooks.items():
        lines.append(f"### {hook_name}")
        for check in hook_result.get("checks", []):
            detail = check.get("detail", "")
            lines.append(f"- {check.get('status', '')}: {check.get('name', '')} {detail}")
        for command in hook_result.get("commands", []):
            lines.append(f"- command {command.get('status', '')}: {command.get('name', '')}")
    lines.extend(["", "## Artifacts"])
    for name, value in artifacts.items():
        if isinstance(value, dict) and "files" in value:
            lines.append(f"- {name}:")
            for file_name, file_path in value["files"].items():
                lines.append(f"  - {file_name}: `{file_path}`")
        else:
            lines.append(f"- {name}: `{value}`")
    write_text(round_dir / "summary.md", "\n".join(lines).rstrip() + "\n")


def write_pr_body_draft(round_dir: Path, developer: dict[str, Any], reviewer: dict[str, Any]) -> str:
    lines = [
        "## Summary",
        "",
        developer.get("summary", ""),
        "",
        "## Evidence",
        "",
    ]
    for item in developer.get("evidence", []):
        lines.append(f"- {item}")
    if not developer.get("evidence"):
        lines.append("- See round summary for details.")
    lines.extend(["", "## Test plan", ""])
    for command in developer.get("commands_run", []):
        lines.append(f"- `{command}`")
    if not developer.get("commands_run"):
        lines.append("- Not recorded.")
    lines.extend(
        [
            "",
            "## Reviewer",
            "",
            f"- Decision: {reviewer.get('decision', '')}",
            f"- Summary: {reviewer.get('summary', '')}",
        ]
    )
    path = round_dir / "pr_body_draft.md"
    write_text(path, "\n".join(lines).rstrip() + "\n")
    return str(path)
