当前目标：构建并运行 Codex-only 的 StarryOS AI 自动闭环优化 pipeline。

首批工程目标：

1. 让 Codex Developer 能围绕 StarryOS syscall/应用兼容性问题自动选题、写最小 Linux 用户态测例、运行 Linux/StarryOS 差分、修复 bug、补回归。
2. 让 Codex Reviewer 以只读模式审查证据链、测试覆盖、补丁风险和回归充分性，并用 PASS / REVISE / REJECT 控制闭环。
3. 优先聚焦 2 到 3 组源码级 syscall 测例方向：文件/目录语义、进程等待退出语义、内存映射语义。
4. 默认先使用 riscv64 QEMU 跑通闭环，之后再扩展 aarch64、x86_64、loongarch64。

本阶段禁止大范围重构。每轮只处理一个明确问题或一组强相关语义。
