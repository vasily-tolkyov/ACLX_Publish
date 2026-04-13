# ACL-X 分层策略

英文版见 [STRATEGY.md](STRATEGY.md)。

## 目的

ACL-X 使用四个运行时层级，决定在任务周围需要附加多少自然语言、ACL-X 传输状态与 session 包装。目标是让简单任务保持简单，同时只在运行时结构确实需要时保留 machine-readable state。

## 层级触发条件

| 层级 | 标签 | 触发信号 | 结果 |
| --- | --- | --- | --- |
| `t0` | `nl-lean` | 单表面任务；无真实 handoff；无共享 machine state；无 loop；仅讨论 ACL-X/router/skill 的元任务 | 纯自然语言 prompt，不带 ACL-X runtime bundle |
| `t1` | `handoff-lite` | 恰好一次真实 handoff、一次 reviewer pass，或一个 child agent | 在短 NL 契约旁附带一个紧凑 ACL-X C-layer bundle |
| `t2` | `balanced` | 可复用 machine state、共享工件、多步修复，或 2+ handoff/agents | 使用带 `Machine contract:` 和显式 artifact 规则的 session 包装 prompt |
| `t3` | `loop-heavy` | loop、checkpoint/resume、replay，或重复轮次 | 使用带 loop invariants、checkpoint 目标与 resume handle 的 session 包装 prompt |

自动路由由 `src/aclx/hybrid.py` 实现，并由 `src/aclx/supervisor.py` 强制执行。

## 各层 bundle 上限

运行时会刻意保持每个 ACL-X bundle 足够小。当前上限来自 `configs/hybrid_router_map.yaml` 与 `configs/tier_strategies/*.yaml`。

| 层级 | 最大条目数 | State 条目 | Evidence 条目 | Risk 条目 | Next 条目 | 是否包含 completed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `t0` | 0 | 0 | 0 | 0 | 0 | 否 |
| `t1` | 1 | 0 | 2 | 1 | 2 | 否 |
| `t2` | 2 | 2 | 2 | 1 | 2 | 否 |
| `t3` | 3 | 3 | 2 | 2 | 2 | 是 |

实际理解：

- `t0` 完全不携带 machine bundle。
- `t1` 只保留一次 handoff 契约所需的最小状态。
- `t2` 为多步修复保留输出、约束、范围与下一步动作。
- `t3` 允许额外一个 state 槽位并保留 completed-state，因为 loop resume 需要更丰富的游标。

## Bridge 模式

| `bridge_mode` | 含义 | 使用层级 |
| --- | --- | --- |
| `none` | 纯 NL prompt。不使用 ACL-X runtime bridge。 | `t0` |
| `bundle` | 一个紧凑 ACL-X C-layer bundle 直接嵌入 prompt。 | `t1` |
| `session` | 带 machine contract、artifact 规则与可恢复运行时上下文的 session 包装 prompt。 | `t2`, `t3` |

## 路由信号

分类器从 `t0` 开始，只根据运行时结构升级：

- `delegate once`、`one reviewer pass`、`single handoff` 这类文本信号会升级到 `t1`。
- `shared state across steps`、`phase 1 and phase 2`、`implement then review`、`multiple subagents` 这类信号会升级到 `t2`。
- `checkpoint and resume`、`run the verification loop`、`repeat until clean`、`continue next round` 这类信号会升级到 `t3`。
- 只是讨论 ACL-X、routing、skills、protocols 或 benchmarks、但并未真正发生 handoff 的元任务，仍停留在 `t0`。

## 用户如何覆盖路由器

当前可覆盖的接口：

- 在 supervisor 层强制 style：`aclx supervisor --style adaptive|full` 或 `ACLXSupervisor.build_payload(..., style="adaptive")`。
- 用 `aclx hybrid-prompt --profile review|implement|benchmark|debug|research` 或 Python 中的 `profile="review"` 覆盖 profile。
- 在 Python 中用 `ACLXSupervisor.build_payload(..., task_shape="delegated_once"|"shared_state"|"loop")` 覆盖任务形状。
- 在 Python 中提供硬运行时事实：`expected_handoffs`、`expected_rounds`、`child_agents`、`shared_state=True`。
- 直接在 prompt builder 中用 `HybridTaskSpec(tier="t1"|"t2"|"t3")` 完全绕过推断。

说明：

- CLI 当前直接暴露 style 与 profile。
- 精确强制 tier 目前还是 Python API 能力。
- 如果选中了 `t2` 或 `t3`，但缺少必需输出与约束，supervisor 会有意退回 `t0`。

## Session 契约规则

- `t2` 会保留命名文件、字面格式要求、输出目标与验收检查。
- `t3` 会保留 loop invariants、checkpoint 目标，以及任务显式命名 `TASK.md` 时其中的 task-contract 行。
- `style="hybrid"` 作为 `style="adaptive"` 的兼容别名保留。
- `style="full"` 用于 debug-heavy 的 supervisor payload，不是默认发布路径。

## 定义策略的文件

- `configs/hybrid_router_map.yaml`
- `configs/tier_strategies/t0.yaml`
- `configs/tier_strategies/t1.yaml`
- `configs/tier_strategies/t2.yaml`
- `configs/tier_strategies/t3.yaml`
- `src/aclx/hybrid.py`
- `src/aclx/supervisor.py`
- `configs/strategy_lock.json`
