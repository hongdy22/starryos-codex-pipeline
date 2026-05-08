#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def check_result(name: str, status: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def git_diff_hash(project_root: Path) -> str:
    proc = run_cmd(["git", "diff", "--binary"], project_root)
    if proc.returncode != 0:
        return ""
    return hashlib.sha256(proc.stdout.encode("utf-8", errors="replace")).hexdigest()


def git_snapshot(project_root: Path) -> dict[str, str]:
    commands = {
        "branch": ["git", "branch", "--show-current"],
        "head": ["git", "rev-parse", "--short", "HEAD"],
        "status": ["git", "status", "--short"],
        "diff_stat": ["git", "diff", "--stat"],
        "changed_files": ["git", "diff", "--name-only"],
    }
    snapshot: dict[str, str] = {}
    for key, cmd in commands.items():
        proc = run_cmd(cmd, project_root)
        snapshot[key] = proc.stdout.strip() if proc.returncode == 0 else proc.stderr.strip()
    snapshot["diff_hash"] = git_diff_hash(project_root)
    return snapshot


def is_tracked(repo_root: Path, rel_path: str) -> bool:
    return run_cmd(["git", "ls-files", "--error-unmatch", rel_path], repo_root).returncode == 0


def is_ignored(repo_root: Path, rel_path: str) -> bool:
    return run_cmd(["git", "check-ignore", "-q", rel_path], repo_root).returncode == 0


def validate_schema(data: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def type_ok(value: Any, expected: str) -> bool:
        if expected == "object":
            return isinstance(value, dict)
        if expected == "array":
            return isinstance(value, list)
        if expected == "string":
            return isinstance(value, str)
        if expected == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected == "boolean":
            return isinstance(value, bool)
        return True

    def walk(value: Any, spec: dict[str, Any], path: str) -> None:
        expected_type = spec.get("type")
        if isinstance(expected_type, str) and not type_ok(value, expected_type):
            errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
            return

        if "const" in spec and value != spec["const"]:
            errors.append(f"{path}: expected const {spec['const']!r}, got {value!r}")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{path}: value {value!r} not in enum {spec['enum']!r}")

        if expected_type == "object" and isinstance(value, dict):
            required = spec.get("required", [])
            for key in required:
                if key not in value:
                    errors.append(f"{path}.{key}: missing required field")
            properties = spec.get("properties", {})
            if spec.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        errors.append(f"{path}.{key}: additional property is not allowed")
            for key, child_spec in properties.items():
                if key in value and isinstance(child_spec, dict):
                    walk(value[key], child_spec, f"{path}.{key}")

        if expected_type == "array" and isinstance(value, list):
            item_spec = spec.get("items")
            if isinstance(item_spec, dict):
                for idx, item in enumerate(value):
                    walk(item, item_spec, f"{path}[{idx}]")

    walk(data, schema, "$")
    return errors


def validate_json_file(data_path: Path, schema_path: Path) -> dict[str, Any]:
    if not data_path.exists():
        return check_result("schema", "fail", f"missing data file: {data_path}")
    if not schema_path.exists():
        return check_result("schema", "fail", f"missing schema file: {schema_path}")
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return check_result("schema", "fail", str(exc))
    errors = validate_schema(data, schema)
    if errors:
        return check_result("schema", "fail", "; ".join(errors[:5]))
    return check_result("schema", "pass", f"{data_path.name} matches {schema_path.name}")


def builtin_check(
    name: str,
    *,
    root: Path,
    project_root: Path,
    starryos_root: Path,
    codex_bin: Path,
    codex_tar: Path,
    codex_auth_json: Path,
    dry_run: bool,
    round_dir: Path | None = None,
    schema_path: Path | None = None,
    output_path: Path | None = None,
    developer_diff_hash: str | None = None,
) -> dict[str, Any]:
    if name == "project_root_exists":
        return check_result(name, "pass" if project_root.exists() else "fail", str(project_root))
    if name == "starryos_root_exists":
        return check_result(name, "pass" if starryos_root.exists() else "fail", str(starryos_root))
    if name == "codex_auth_exists":
        if dry_run:
            return check_result(name, "skip", "dry-run does not invoke Codex")
        return check_result(name, "pass" if codex_auth_json.exists() else "fail", str(codex_auth_json))
    if name == "codex_auth_not_tracked":
        rel = str(codex_auth_json.relative_to(root)) if codex_auth_json.is_relative_to(root) else str(codex_auth_json)
        return check_result(name, "fail" if is_tracked(root, rel) else "pass", rel)
    if name == "codex_auth_ignored":
        rel = str(codex_auth_json.relative_to(root)) if codex_auth_json.is_relative_to(root) else str(codex_auth_json)
        return check_result(name, "pass" if is_ignored(root, rel) else "warn", rel)
    if name == "codex_binary_or_tarball_exists":
        if dry_run:
            return check_result(name, "skip", "dry-run does not invoke Codex")
        if codex_bin.exists() or codex_tar.exists():
            return check_result(name, "pass", f"bin={codex_bin.exists()} tar={codex_tar.exists()}")
        return check_result(name, "fail", f"missing {codex_bin} and {codex_tar}")
    if name == "schema_output_valid":
        if schema_path is None or output_path is None:
            return check_result(name, "fail", "schema_path/output_path missing")
        result = validate_json_file(output_path, schema_path)
        result["name"] = name
        return result
    if name == "git_diff_check":
        proc = run_cmd(["git", "diff", "--check"], project_root)
        status = "pass" if proc.returncode == 0 else "warn"
        detail = (proc.stdout + proc.stderr).strip() or "git diff --check passed"
        return check_result(name, status, detail[:1000])
    if name == "reviewer_preserved_developer_diff":
        if developer_diff_hash is None:
            return check_result(name, "skip", "developer diff hash unavailable")
        current = git_diff_hash(project_root)
        if current == developer_diff_hash:
            return check_result(name, "pass", "reviewer left developer diff unchanged")
        return check_result(name, "warn", "git diff changed during reviewer phase")
    if name == "round_dir_exists":
        if round_dir is None:
            return check_result(name, "skip", "round_dir unavailable")
        return check_result(name, "pass" if round_dir.exists() else "fail", str(round_dir))
    return check_result(name, "warn", f"unknown builtin check: {name}")
