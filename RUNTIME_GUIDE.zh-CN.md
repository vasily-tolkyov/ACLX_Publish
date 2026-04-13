# ACL-X 运行时指南

英文版见 [RUNTIME_GUIDE.md](RUNTIME_GUIDE.md)。

本文说明 ACL-X 在本地 Codex 中的自适应默认可见运行时路径。

## 分层默认

从满足条件的最低层开始。

- `t0` `nl-lean`：单次、无循环任务。保持自然语言，不提前启用 ACL-X。
- `t1` `handoff-lite`：恰好一个基于文件的 machine-only 工件，或恰好一次真实 handoff。任务文本保持自然语言，只附带极小 ACL-X package 或 pointer。
- `t2` `balanced`：多 agent 或可复用共享状态。任务与回答文本保持自然语言；machine-only 状态通过 runtime bridge 传递，并带显式 `Must write` 与 `Done when` 契约。
- `t3` `loop-heavy`：重复 handoff 或 resume 循环。首个 prompt 与每次 resume prompt 都必须经过 runtime bridge，以便 checkpoint 工件和 loop invariants 能与 ACL-X handle 一起重述。

## 升级规则

只有在出现真实 handoff、resume 或共享状态证据之后才升级。对于只是提到 handoff、queue、triad 或 ACL-X 的单次任务，不要预先支付 ACL-X 的归档成本。

一旦运行升级到 `t2` 或 `t3`，就不要再退回自由文本的 machine state。共享工件、checkpoint prompt 与 resume prompt 必须持续经由 `ctx/session.py` 或 plugin bridge。

## 相关文件

- `configs/hybrid_router_map.yaml`
- `src/aclx/hybrid.py`
- `src/aclx/supervisor.py`
- `ctx/session.py`

## 机器侧挂接点

默认策略通过以下位置暴露：

- `<CODEX_HOME>/AGENTS.md`
- `<CODEX_HOME>/config.toml`
- `<ACLX_PLUGIN_SKILL_ROOT>/SKILL.md`
- `<CODEX_HOME>/plugins/cache/local-user-plugins/aclx-runtime/local`

修改全局指令或 plugin 文件后，请重启 Codex，让新会话拾取新的默认策略。

## 宿主兼容性

本文描述的默认启用安装路径是 Codex 专用。

本仓库仍可为其他 agent 宿主提供可移植的 routing、prompt 与 runtime 组件，但这些宿主需要自行完成集成。

本文不宣称为任意非 Codex 宿主提供打包好的默认启用安装器。准确的发布边界请阅读 [docs/agent_compatibility.zh-CN.md](docs/agent_compatibility.zh-CN.md)。

`style="hybrid"` 是 `style="adaptive"` 的兼容别名。只要运行时事实仍然符合 `t0`，它就不能强行触发 `t1` bundle。
