# StarryOS Codex 闭环 Pipeline

这套代码只做一件事：用本地 Codex CLI 驱动外部 checkout 的
`tgoskits/os/StarryOS` 做自动闭环迭代。

`exp3_busybox` 分支用于 BusyBox 兼容性实验：仍然基于 riscv64 QEMU、
Linux/StarryOS 差分、最小修复和 Reviewer 审查闭环，但选题从通用
syscall 源码级测例优先，调整为逐步修复 BusyBox applet/script 失败项。
失败项 backlog 来自
<https://github.com/rcore-os/linux-compatible-testsuit/issues/13>；当前已通过
的 BusyBox 脚本基线位于
`tgoskits/test-suit/starryos/normal/qemu-smp1/busybox/sh/busybox-tests.sh`。
本分支的自动提交分支前缀为 `exp3_busybox`。

闭环形态：

```text
Syncer Codex 先同步 tgoskits 到上游最新 dev
        |
        v
Developer Codex 写测例/跑差分/修补丁
        |
        v
Reviewer Codex 复核证据链/必要时执行验证
        |
        v
PASS 后 Committer 新建分支 commit 并 push 到 fork
        |
        v
切回本轮修改前的基线，REVISE/REJECT 则保留 diff 继续修
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
├── hooks/
├── prompts/
├── schemas/
├── scripts/
├── skills/
└── results/     # 本地运行结果
```

[pipeline/config.json](pipeline/config.json)

主配置。包括：

- `tgoskits` 相对路径
- `StarryOS` 相对路径
- Codex binary、tarball、auth 路径
- Syncer/Developer/Reviewer 的模型、推理强度、沙箱策略
- Committer 的目标 remote、分支前缀、是否 push

[pipeline/prompts/](pipeline/prompts)

人工定义的目标、策略和角色规则：

- `syncer_role.md`：启动前同步 `tgoskits` 到上游最新 `dev` 的规则
- `developer_role.md`：Developer 角色规则
- `reviewer_role.md`：Reviewer 角色规则
- `shared_main.md`：StarryOS 路径、闭环流程、测试先行、Linux 基准、输出要求
- `goal.md`：当前总体目标
- `strategy.json`：选题优先级和 review 策略

[pipeline/hooks/](pipeline/hooks)

确定性的执行护栏，不交给 AI 自由发挥：

- `preflight.json`：检查 `tgoskits`、StarryOS 路径、Codex auth、本地 Codex binary/tarball。
- `post_syncer.json`：校验 Syncer JSON，并记录同步后的 `git diff --check`。
- `post_developer.json`：校验 Developer JSON、保存 patch、记录 `git diff --check`。
- `post_reviewer.json`：校验 Reviewer JSON，并检查 Reviewer 是否改变了 Developer diff。
- `post_committer.json`：校验 Committer JSON，并确认提交后工作区没有格式空白问题。
- `on_pass.json`：PASS 后生成本轮摘要和 PR body 草稿。

[pipeline/skills/](pipeline/skills)

Codex 可安装格式的短 playbook，每个 skill 都是独立目录：

- `syscall-harness/SKILL.md`：syscall 源码级差分测例约定
- `linux-baseline/SKILL.md`：Linux 行为基准定义约定
- `qemu-verify/SKILL.md`：StarryOS QEMU 验证约定
- `pr-ready/SKILL.md`：上游 PR 准备约定

这些 skill 当前不自动注入 prompt，只作为框架资产保留，避免 prompt 变复杂。
如果要让本机 Codex 直接发现某个 skill，可以把对应目录复制到
`${CODEX_HOME:-~/.codex}/skills/`。

[pipeline/schemas/](pipeline/schemas)

Codex 最终输出必须符合的 JSON Schema：

- `syncer.json`
- `developer.json`
- `reviewer.json`
- `committer.json`

脚本靠这些 schema 稳定读取 `target`、`evidence`、`decision` 等字段。
当前 schema 刻意保持很小，只保留闭环调度需要的字段，不把完整报告结构强塞进 JSON。

[pipeline/scripts/](pipeline/scripts)

核心脚本：

```text
agent_loop.py    主调度器，负责拼 prompt、调 Codex、保存轮次结果
checks.py        确定性检查：schema、git、auth、路径
hooks.py         读取 hook 配置并执行检查/命令
artifacts.py     保存 patch、git 状态、summary、PR body 草稿
```

[pipeline/results/](pipeline/results)

运行结果，脚本自动生成：

```text
pipeline/results/
├── rounds/   # 每轮 prompt、Codex 输出、事件日志
└── state/    # loop_state.json、journal.md 和 passed_commits.json
```

`results/` 会随运行增长，不是核心代码。

## 5. 一轮怎么跑

`python3 run.py loop --max-rounds 3` 会做：

```text
1. 读取 config/prompts/schemas 和 results/state
2. 生成 Syncer prompt
3. 调用 Syncer Codex，确保 `tgoskits` 已 fetch/rebase 到最新 `upstream/dev`
4. Syncer 返回 READY 才继续；返回 BLOCKED 则停止并保存原因
5. 生成 Developer prompt
6. 调用 Developer Codex，可写 `tgoskits`
7. 保存 developer_output.json
8. 生成 Reviewer prompt
9. 调用 Reviewer Codex，拥有完整执行权限，但 prompt 要求不要留下源码改动
10. 保存 reviewer_output.json
11. Reviewer PASS 后，Committer 新建分支、commit、push 到 fork
12. Committer 切回本轮修改前的基线分支/HEAD
13. REVISE/REJECT 不 commit，保留当前 diff，把意见带入下一轮继续修
```

输出示例：

```text
pipeline/results/rounds/round-001/
├── syncer_prompt.txt
├── syncer_output.json
├── syncer_events.jsonl
├── syncer.patch
├── developer_prompt.txt
├── developer_output.json
├── developer_events.jsonl
├── developer.patch
├── developer_diff_stat.txt
├── reviewer_prompt.txt
├── reviewer_output.json
├── reviewer_events.jsonl
├── reviewer.patch
├── committer_output.json
├── committer_git_status.txt
├── verification.json
├── summary.md
└── pr_body_draft.md
```

`dry-run` 会生成 Syncer/Developer prompt 和占位输出，不调用 Codex。

## 6. 为什么每轮都生成 prompt

每轮的 prompt 是：

```text
固定规则 + 本轮上下文
```

固定规则来自：

```text
pipeline/prompts/syncer_role.md
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
pipeline/results/state/passed_commits.json 的已提交成果
上一轮 reviewer_output.json 的 PASS / REVISE / REJECT 意见
```

prompt 不内嵌完整 `git diff`。Codex 需要时自己运行 `git diff` 和读取文件，这样上下文更准，也不容易塞爆 prompt。
如果某个 target 已经 `PASS`，下一轮 prompt 会明确要求 Developer 不要重复选择它；只有 Reviewer 要求补测或修订时，才继续同一个 target。

Syncer prompt 只在每次 loop 启动后的第一轮前生成一次。它会让 Codex 自己检查远端、fetch 最新 `upstream/dev`、处理 rebase/冲突，并输出 `READY` 或 `BLOCKED`。这样仓库更新逻辑不靠脚本硬编码，遇到复杂冲突时由 Codex 读代码后处理。

Committer 不是 AI agent，而是脚本里的确定性阶段。Reviewer 返回 `PASS` 后，它会：

```text
1. 记录本轮开始前的 branch/HEAD
2. 从当前 diff 新建一个 `codex/round-...` 分支
3. `git add -A` 并提交
4. push 到 fork remote，默认是 `origin`
5. 切回本轮开始前的 branch/HEAD
6. 把 branch、commit、changed files 写入 passed_commits.json 和 journal
```

它不会自动打开 PR，也不会自动更新 fork 的 `dev` 分支。feature 分支直接基于本地最新 `upstream/dev` 推到 fork 即可；fork 的 `origin/dev` 是否同步不影响这些 feature 分支创建和后续手动 PR。

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
- Reviewer 返回 `PASS` 后才允许 Committer 提交；提交后下一轮从基线分支继续，不能依赖当前 `git diff` 记住旧成果。
