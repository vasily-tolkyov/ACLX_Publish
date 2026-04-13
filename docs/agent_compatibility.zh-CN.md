# Agent 兼容性说明

这份文档用于明确当前 ACL-X 公开发布版里，“默认启用 hybrid 安装”到底覆盖到什么边界。

英文版见 [agent_compatibility.md](agent_compatibility.md)。

## 摘要

- 当前 share pack 安装器支持把 adaptive hybrid 作为 Codex 的默认运行时策略启用。
- 仓库中的协议、prompt 和 runtime 组件本身仍然可以被其他 agent 宿主手动集成复用。
- 当前公开发布版还没有为任意非 Codex agent 宿主提供“一键默认启用”的安装器。

## 目前真正支持默认启用的范围

当前仓库里的默认启用能力，范围仅限 Codex 宿主。

发布包通过以下位置挂接默认策略：

- `CODEX_HOME/AGENTS.md`
- `CODEX_HOME/config.toml`
- vendored 的 `aclx-runtime` skill
- runtime guide 里说明的本地 Codex plugin cache 路径
- 隔离启动器 `start_hybrid_codex.ps1`

随仓库提供的 share pack 会复制稳定的 Codex home 项到一个隔离 home，写入 Codex 专用 `AGENTS.md`，并在启动时把 `CODEX_HOME` 指向这个隔离环境。

## 这在行为上意味着什么

如果一台机器严格按文档安装这份 share pack，那么通过安装后启动器拉起的目标 Codex，会把这套策略作为新会话的默认可见运行时策略。

这并不意味着该机器上的所有 AI agent 都会自动默认使用 ACL-X hybrid。

## 其它 agent 宿主仍可复用的部分

即便不是 Codex，其它宿主仍然可以手动复用这个项目。

可移植部分包括：

- ACL-X handoff 编解码
- 紧凑 delegation payload 生成
- hybrid prompt 构造
- `t0/t1/t2/t3` 路由语义
- `Machine contract` 与 `Loop invariants` 的 runtime 契约措辞
- checkpoint 与可恢复状态约定

CLI 里直接暴露了其中一部分：

- `aclx handoff`
- `aclx handoff-json`
- `aclx delegate`
- `aclx delegate-aclx`
- `aclx hybrid-prompt`

## 其它 agent 宿主当前拿不到的东西

对于非 Codex 宿主，当前仓库还没有提供：

- 开箱即用的默认启用安装器
- 宿主专用启动器
- 宿主专用持久化设置写入器
- 宿主专用 plugin 或 skill 安装链路
- 与 Codex `AGENTS.md` 加 `CODEX_HOME` 等价的默认策略注入路径

因此，下面这类宿主目前都需要手动集成：

- 通用 OpenAI agent runtime
- 自定义 orchestration framework
- agent SDK 包装层
- 编辑器内置助手
- 其他 CLI-first agent shell

## 其它宿主手动接入时需要补的能力

如果要在 Codex 之外采用这套策略，目标宿主至少需要自己补齐：

1. 持久化顶层指令或系统策略注入
2. 可选的 skill 或 plugin 发现机制
3. delegation 与 handoff 注入
4. `t2/t3` 需要的可复用机器状态存储
5. checkpoint 与 resume prompt 重建
6. 让这套策略成为宿主默认行为所需的启动器或环境引导

在这些宿主专用接线完成前，ACL-X 更准确的对外表述应是“可手动集成移植”，而不是“已默认安装”。

## 推荐发布口径

对外建议使用这类表述：

- “当前版本支持 Codex 默认启用安装。”
- “其它 agent 宿主可以手动接入这套策略，但本仓库还没有给它们提供打包好的默认安装器。”
- “ACL-X hybrid 当前是 Codex-default，而不是 universal-host-default。”
