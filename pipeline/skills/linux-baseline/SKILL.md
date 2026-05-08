---
name: linux-baseline
description: Define and validate Linux reference behavior for StarryOS syscall or kernel-compatibility work. Use when Codex needs to establish expected Linux return values, errno, stdout/stderr, side effects, blocking behavior, or edge cases before writing or reviewing StarryOS fixes.
---

# Linux Baseline

Use this skill to turn a suspected StarryOS behavior gap into a precise Linux reference.

## Workflow

1. Identify the smallest Linux behavior being tested.
2. Write or inspect a self-contained userspace test before changing StarryOS code.
3. Run the test on Linux first. If Linux fails, fix the test instead of reporting a StarryOS bug.
4. Record exact return values, `errno`, stdout/stderr, and side effects.
5. Only treat a StarryOS result as a confirmed bug after comparing it with the Linux baseline.

## Coverage Checklist

- Normal success path
- Invalid input path
- Boundary values
- `errno` value and priority
- Filesystem or memory side effects
- Blocking, wakeup, timing, or concurrency behavior when relevant
- Resource cleanup behavior when relevant

## Notes

- Do not use StarryOS current behavior to define correctness.
- Prefer minimal C tests with deterministic, machine-comparable output.
- Keep baseline claims tied to executable evidence or a precise Linux reference.
