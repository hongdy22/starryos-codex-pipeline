# StarryOS Codex 闭环 Pipeline

这套代码只做一件事：用本地 Codex CLI 驱动外部 checkout 的
`tgoskits/os/StarryOS` 做自动闭环迭代。

闭环形态：

```text
Developer Codex 写测例/跑差分/修补丁
        |
        v
Reviewer Codex 复核证据链/必要时执行验证
        |
        v
PASS 默认停止，REVISE/REJECT 进入下一轮
```

## 1. 顶层目录

```text
<repo>/
├── run.py        # 唯一入口，只保留 dry-run 和 loop
├── pipeline/     # prompt、schema、调度脚本
├── codex/        # Codex wrapper 和 auth 示例
└── tgoskits/     # 本地外部 checkout
```

建议先看：

1. [run.py](run.py)
2. [pipeline/config.json](pipeline/config.json)
3. [pipeline/prompts/shared_main.md](pipeline/prompts/shared_main.md)
4. [pipeline/scripts/agent_loop.py](pipeline/scripts/agent_loop.py)

## 2. 本地准备

`tgoskits/` 是 StarryOS 所在的本地 checkout，默认由
[pipeline/config.json](pipeline/config.json) 里的相对路径指定。

推荐初始化方式：

```bash
git clone https://github.com/rcore-os/tgoskits.git tgoskits
cd tgoskits
git switch dev
```

如果你要向上游提 PR，更推荐把 `origin` 设为自己的 fork，把上游设为
`upstream`：

```bash
git clone git@github.com:<your-user>/tgoskits.git tgoskits
cd tgoskits
git remote add upstream https://github.com/rcore-os/tgoskits.git
git fetch upstream
git switch -C dev upstream/dev
```

这样 pipeline 可以在 `tgoskits/` 里改代码、跑测试、开分支。

准备 Codex 登录态：

```bash
cp codex/auth.example.json codex/auth.json
```

上面的 example 只是占位说明，不是真实可用的 auth。实际使用时，把 Codex CLI
登录生成的 `auth.json` 放到 `codex/auth.json`，或者用环境变量指定：

```bash
export CODEX_AUTH_JSON=/path/to/your/local/auth.json
```

准备 Codex 可执行文件：

- 可以从 <https://github.com/openai/codex/releases?page=3> 下载对应平台的 Codex 可执行文件。
- 可以把本地 tarball 放到 `codex/codex-x86_64-unknown-linux-musl.tar.gz`。
- 也可以直接设置 `CODEX_BIN` 指向已经安装好的 Codex 可执行文件。

## 3. 命令

只生成下一轮 prompt，不调用 Codex：

```bash
python3 run.py dry-run --max-rounds 1
```

运行真正闭环：

```bash
python3 run.py loop --max-rounds 3
```

默认行为是：某一轮 Reviewer 返回 `PASS` 就停止。如果想连续跑多个目标，用：

```bash
python3 run.py loop --max-rounds 3 --continue-after-pass
```

现在没有额外 helper 命令。Codex 需要看测试、跑 QEMU、写 case 时，直接在 `tgoskits/` 工作目录里使用原生命令，例如：

```bash
cargo xtask starry test qemu --arch riscv64 --list
cargo xtask starry test qemu --arch riscv64 --test-group normal --test-case <case>
```

## 4. pipeline 目录

```text
pipeline/
├── config.json
├── prompts/
├── schemas/
├── scripts/
└── results/     # 本地运行结果
```

[pipeline/config.json](pipeline/config.json)

主配置。包括：

- `tgoskits` 相对路径
- `StarryOS` 相对路径
- Codex binary、tarball、auth 路径
- Developer/Reviewer 的模型、推理强度、沙箱策略

[pipeline/prompts/](pipeline/prompts)

人工定义的目标、策略和角色规则：

- `developer_role.md`：Developer 角色规则
- `reviewer_role.md`：Reviewer 角色规则
- `shared_main.md`：StarryOS 路径、闭环流程、测试先行、Linux 基准、输出要求
- `goal.md`：当前总体目标
- `strategy.json`：选题优先级和 review 策略

[pipeline/schemas/](pipeline/schemas)

Codex 最终输出必须符合的 JSON Schema：

- `developer.json`
- `reviewer.json`

脚本靠这些 schema 稳定读取 `target`、`evidence`、`decision` 等字段。
当前 schema 刻意保持很小，只保留闭环调度需要的字段，不把完整报告结构强塞进 JSON。

[pipeline/scripts/](pipeline/scripts)

只保留一个脚本：

```text
agent_loop.py    主调度器，负责拼 prompt、调 Codex、保存轮次结果
```

[pipeline/results/](pipeline/results)

运行结果，脚本自动生成：

```text
pipeline/results/
├── rounds/   # 每轮 prompt、Codex 输出、事件日志
└── state/    # loop_state.json 和 journal.md
```

`results/` 会随运行增长，不是核心代码。

## 5. 一轮怎么跑

`python3 run.py loop --max-rounds 3` 会做：

```text
1. 读取 config/prompts/schemas 和 results/state
2. 生成 Developer prompt
3. 调用 Developer Codex，可写 `tgoskits`
4. 保存 developer_output.json
5. 生成 Reviewer prompt
6. 调用 Reviewer Codex，拥有完整执行权限，但 prompt 要求不要留下源码改动
7. 保存 reviewer_output.json
8. Reviewer PASS 则停止，否则把意见带入下一轮
```

输出示例：

```text
pipeline/results/rounds/round-001/
├── developer_prompt.txt
├── developer_output.json
├── developer_events.jsonl
├── reviewer_prompt.txt
├── reviewer_output.json
└── reviewer_events.jsonl
```

`dry-run` 只生成 Developer prompt 和一个占位输出，不调用 Codex。

## 6. 为什么每轮都生成 prompt

每轮的 prompt 是：

```text
固定规则 + 本轮上下文
```

固定规则来自：

```text
pipeline/prompts/developer_role.md
pipeline/prompts/shared_main.md
pipeline/prompts/goal.md
pipeline/prompts/strategy.json
```

每轮变化的是：

```text
round number
git branch / HEAD
git status --short
pipeline/results/state/journal.md 的最近轮次摘要
上一轮 reviewer_output.json 的 PASS / REVISE / REJECT 意见
```

prompt 不内嵌完整 `git diff`。Codex 需要时自己运行 `git diff` 和读取文件，这样上下文更准，也不容易塞爆 prompt。
如果某个 target 已经 `PASS`，下一轮 prompt 会明确要求 Developer 不要重复选择它；只有 Reviewer 要求补测或修订时，才继续同一个 target。

## 7. StarryOS 测试约定

StarryOS 测试仍然走 `tgoskits` 原生命令：

```bash
cd tgoskits
cargo xtask starry test qemu --arch riscv64 --test-group normal --test-case <case>
```

新增源码级 C case 时，优先放到：

```text
tgoskits/test-suit/starryos/normal/qemu-smp1/<case>/
```

典型结构：

```text
<case>/
├── qemu-riscv64.toml
└── c/
    ├── CMakeLists.txt
    └── src/main.c
```

只给实际验证过的架构添加 `qemu-<arch>.toml`。

## 8. 硬规则

- Linux 行为是基准。
- 没有 Linux/StarryOS 差分证据，不算确认 bug。
- 没有长期回归测例，不算合格修复。
- 单轮只处理一个明确问题或一组强相关 syscall 语义。
- Reviewer 可以跑验证命令，但不应接管 Developer 的实现；如果临时修改文件，结束前必须只恢复自己的改动。
- Reviewer 返回 `REVISE` 或 `REJECT` 时，不进入下一个目标。
