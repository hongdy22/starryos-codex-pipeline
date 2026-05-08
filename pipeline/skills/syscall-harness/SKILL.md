---
name: syscall-harness
description: Create or review minimal syscall regression tests for StarryOS. Use when Codex needs to design a Linux/StarryOS differential C test, add a test-suit case under test-suit/starryos, choose success/fail regexes, or preserve a confirmed syscall bug as a long-term regression asset.
---

# Syscall Harness

Use this skill to convert a syscall behavior hypothesis into a reusable StarryOS regression case.

## Workflow

1. Define one syscall semantic point or one tightly related semantic group.
2. Write a self-contained C test that can run on Linux and StarryOS.
3. Make output deterministic and machine-comparable.
4. Validate Linux behavior before using the test against StarryOS.
5. For small syscall bugfixes, prefer adding a grouped `bugfix` subcase under:
   ```text
   test-suit/starryos/normal/qemu-smp1/bugfix/<bug-name>/
   ```
6. Add the subcase command to `test-suit/starryos/normal/qemu-smp1/bugfix/qemu-riscv64.toml`.
7. Run the focused grouped QEMU case after the fix:
   ```bash
   cargo xtask starry test qemu --arch riscv64 --test-group normal --test-case bugfix
   ```

## C Test Conventions

- Print clear `PASS` / `FAIL` lines.
- Return `0` only when all checks pass.
- Check return value and `errno` immediately after each syscall.
- Verify side effects such as file contents, link count, path existence, mappings, or process exit status.
- Avoid relying on timing unless testing blocking or concurrency semantics.

## Preferred Bugfix Grouped Case Shape

Use this shape for small syscall regressions that can share one StarryOS boot with other bugfixes:

```text
test-suit/starryos/normal/qemu-smp1/bugfix/
├── qemu-riscv64.toml
└── <bug-name>/
    └── c/
        ├── CMakeLists.txt
        └── src/main.c
```

Add one `test_commands` entry in `bugfix/qemu-riscv64.toml` for the installed binary.

## Standalone Case Shape

Use this shape only when the test needs a separate runtime config, rootfs setup, timeout, or success/fail regex:

```text
<case>/
├── qemu-riscv64.toml
└── c/
    ├── CMakeLists.txt
    └── src/main.c
```

Keep the case small enough that a reviewer can see which Linux behavior it proves.
