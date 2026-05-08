#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from checks import builtin_check


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class HookRunner:
    def __init__(self, *, root: Path, pipeline: Path, config: dict[str, Any]) -> None:
        self.root = root
        self.pipeline = pipeline
        self.config = config
        self.hooks_dir = self._resolve(config.get("hooks_dir", "pipeline/hooks"))

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (self.root / path).resolve()

    def _config_value(self, key: str) -> Any:
        return os.environ.get(key.upper()) or self.config[key]

    def _project_root(self) -> Path:
        return self._resolve(self._config_value("project_root"))

    def _starryos_root(self) -> Path:
        return self._resolve(self._config_value("starryos_root"))

    def _codex_bin(self) -> Path:
        return self._resolve(os.environ.get("CODEX_BIN") or self.config["codex_bin"])

    def _codex_tar(self) -> Path:
        return self._resolve(self._config_value("codex_tar"))

    def _codex_auth_json(self) -> Path:
        return self._resolve(self._config_value("codex_auth_json"))

    def run(self, hook_name: str, **context: Any) -> dict[str, Any]:
        context.setdefault("phase_name", hook_name)
        hook_path = self.hooks_dir / f"{hook_name}.json"
        hook = read_json(hook_path, default={"enabled": False})
        result: dict[str, Any] = {
            "name": hook_name,
            "enabled": bool(hook.get("enabled", False)),
            "checks": [],
            "commands": [],
            "fail_on_error": bool(hook.get("fail_on_error", False)),
        }
        if not result["enabled"]:
            return result

        for check_name in hook.get("checks", []):
            result["checks"].append(
                builtin_check(
                    check_name,
                    root=self.root,
                    project_root=self._project_root(),
                    starryos_root=self._starryos_root(),
                    codex_bin=self._codex_bin(),
                    codex_tar=self._codex_tar(),
                    codex_auth_json=self._codex_auth_json(),
                    dry_run=bool(context.get("dry_run", False)),
                    round_dir=context.get("round_dir"),
                    schema_path=context.get("schema_path"),
                    output_path=context.get("output_path"),
                    developer_diff_hash=context.get("developer_diff_hash"),
                )
            )

        for command in hook.get("commands", []):
            result["commands"].append(self._run_command(command, context))

        return result

    def has_blocking_failure(self, result: dict[str, Any]) -> bool:
        if not result.get("fail_on_error", False):
            return False
        return any(check.get("status") == "fail" for check in result.get("checks", [])) or any(
            command.get("required") and command.get("returncode", 0) != 0 for command in result.get("commands", [])
        )

    def _cwd_for(self, name: str, context: dict[str, Any]) -> Path:
        if name == "root":
            return self.root
        if name == "pipeline":
            return self.pipeline
        if name == "round_dir":
            return context.get("round_dir", self.pipeline)
        return self._project_root()

    def _run_command(self, command: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        name = command.get("name", "command")
        cmd = command.get("cmd")
        cwd = self._cwd_for(command.get("cwd", "project_root"), context)
        required = bool(command.get("required", False))
        if not cmd:
            return {"name": name, "status": "skip", "required": required, "returncode": 0}
        if isinstance(cmd, str):
            run_args = ["sh", "-lc", cmd]
        else:
            run_args = [str(part) for part in cmd]
        proc = subprocess.run(
            run_args,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            timeout=command.get("timeout"),
        )
        round_dir = context.get("round_dir")
        if isinstance(round_dir, Path):
            safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
            out_base = round_dir / "hook-logs" / f"{context.get('phase_name', 'hook')}_{safe_name}"
            write_text(out_base.with_suffix(".stdout"), proc.stdout)
            write_text(out_base.with_suffix(".stderr"), proc.stderr)
        status = "pass" if proc.returncode == 0 else ("fail" if required else "warn")
        return {
            "name": name,
            "status": status,
            "required": required,
            "returncode": proc.returncode,
            "cwd": str(cwd),
            "cmd": run_args,
        }
