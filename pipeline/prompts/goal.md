当前目标：在 `exp3_busybox` 实验分支上运行 Codex-only 的 StarryOS BusyBox 兼容性闭环优化 pipeline。

首批工程目标：

1. 让 Codex Developer 能围绕 StarryOS 对 BusyBox 的支持自动选题：从 BusyBox 失败脚本/命令中选择一个明确 applet 或一组强相关 applet，建立 Linux BusyBox 基准，运行 Linux/StarryOS 差分，定位 StarryOS 内核或测试环境缺口，修复 bug 或补齐必要功能，并补回归。
2. 让 Codex Reviewer 以只读模式审查证据链、测试覆盖、补丁风险和回归充分性，并用 PASS / REVISE / REJECT 控制闭环。
3. 当前应用目标是 1 个 Linux 小应用：BusyBox。优先逐步解决 <https://github.com/rcore-os/linux-compatible-testsuit/issues/13> 中列出的 StarryOS riscv64 BusyBox 失败项。
4. issue #13 的 `FAIL 测试`、`测试命令`、`验证方式` 三列是本实验的权威 backlog 和 oracle。Developer 选择目标时必须记录对应行；Linux/StarryOS 验证必须优先使用该 `测试命令`，PASS/FAIL 判定必须优先使用该 `验证方式`。Reviewer 必须复核这三列是否被正确使用。
5. 已经通过的 BusyBox 脚本基线位于 `test-suit/starryos/normal/qemu-smp1/busybox/sh/busybox-tests.sh`。每轮修复后，应该把对应 BusyBox applet 的可维护回归沉淀到这个脚本或相邻的 BusyBox 测试资产中。
6. 默认先使用 riscv64 QEMU 跑通闭环，命令优先使用 `cargo xtask starry test qemu --arch riscv64 --test-group normal --test-case busybox`。之后再扩展 aarch64、x86_64、loongarch64。
7. Reviewer PASS 后的自动提交分支必须使用 `exp3_busybox` 前缀；具体后缀由 pipeline 根据轮次和目标生成。

本阶段禁止大范围重构。每轮只处理一个明确 BusyBox 失败项，或一组由同一根因导致的强相关 BusyBox 语义。
