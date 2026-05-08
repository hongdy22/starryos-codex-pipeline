---
name: qemu-verify
description: Run and interpret StarryOS QEMU verification. Use when Codex needs to list StarryOS QEMU cases, run a focused qemu test, classify kernel panic versus test assertion failure versus hang, or record architecture-specific verification for riscv64, aarch64, x86_64, or loongarch64.
---

# QEMU Verify

Use this skill to validate a StarryOS change with the repository's native QEMU test flow.

## Workflow

1. List available cases when unsure:
   ```bash
   cargo xtask starry test qemu --arch riscv64 --list
   ```
2. Run the most focused case first:
   ```bash
   cargo xtask starry test qemu --arch riscv64 --test-group normal --test-case <case>
   ```
3. Run adjacent smoke or bugfix suites when the changed subsystem has nearby coverage.
4. Record the exact command, architecture, test group, test case, and pass/fail result.

## Failure Classification

- Test assertion failure: userspace test reports FAIL or nonzero exit.
- Kernel panic: log contains panic/trap/backtrace from kernel.
- Hang: QEMU timeout or no shell/test completion.
- Environment failure: missing toolchain, rootfs, QEMU binary, package, or host dependency.

## Notes

- Default first-pass architecture is `riscv64`.
- Only add `qemu-<arch>.toml` for architectures actually validated.
- If local dependencies prevent reaching QEMU, report the dependency issue separately from kernel behavior.
