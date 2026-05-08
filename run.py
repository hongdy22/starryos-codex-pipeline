#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "pipeline"
SCRIPTS = PIPELINE / "scripts"


def run(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    return subprocess.run(cmd, cwd=str(ROOT), check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One small entrypoint for the StarryOS Codex pipeline.",
        usage="""python3 run.py <command> [args]

Commands:
  dry-run      Generate the next Developer prompt without calling Codex
  loop         Run the Developer -> Reviewer loop

Examples:
  python3 run.py dry-run --max-rounds 1
  python3 run.py loop --max-rounds 1
  python3 run.py loop --max-rounds 3 --continue-after-pass
""",
    )
    parser.add_argument("command", nargs="?")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()

    if not parsed.command:
        parser.print_help()
        return 0

    command = parsed.command
    rest = parsed.args

    if command == "dry-run":
        return run("agent_loop.py", ["--dry-run", *rest])
    if command == "loop":
        return run("agent_loop.py", rest)

    print(f"unknown command: {command}", file=sys.stderr)
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
