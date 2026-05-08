---
name: pr-ready
description: Prepare a StarryOS fix for upstream PR review. Use when Codex needs to package a kernel fix and regression test into a minimal branch, write a conventional PR title/body, check local validation results, or ensure no pipeline artifacts, auth files, rootfs images, or build outputs are included.
---

# PR Ready

Use this skill after a StarryOS fix has evidence, review, and regression coverage.

## Workflow

1. Keep one PR focused on one bugfix or one tightly related syscall semantic group.
2. Inspect `git diff --name-only` and `git diff --stat`.
3. Verify the branch contains the kernel change and its regression test only.
4. Run the narrow validation commands recorded by the round, then run adjacent smoke checks when practical.
5. Draft a PR body with Summary, Root Cause, and Test plan.

## PR Shape

- Title format: `fix(scope): concise behavior change`
- Body sections:
  - `Summary`
  - `Root Cause`
  - `Test plan`
  - Optional `Notes` for limitations such as single-arch validation or non-atomic semantic scope

## Guardrails

- Do not include pipeline run outputs.
- Do not include Codex auth files.
- Do not include local rootfs images or `target/` outputs.
- Do not claim CI passed until GitHub checks actually report success.
