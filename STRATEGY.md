# ACL-X Tier Strategy

Chinese version: [STRATEGY.zh-CN.md](STRATEGY.zh-CN.md).

## Purpose

ACL-X uses four runtime tiers to decide how much natural language, ACL-X transport state, and session wrapping to add around a task. The goal is to keep simple work simple while preserving machine-readable state only when the runtime structure truly needs it.

## Tier Triggers

| Tier | Label | Trigger signals | Result |
| --- | --- | --- | --- |
| `t0` | `nl-lean` | single-surface work; no real handoff; no shared machine state; no loop; meta-only ACL-X/router/skill work | pure natural-language prompt, no ACL-X runtime bundle |
| `t1` | `handoff-lite` | exactly one real handoff, one reviewer pass, or one child agent | one compact ACL-X C-layer bundle alongside a short NL contract |
| `t2` | `balanced` | reusable machine state, shared artifacts, multi-step repair, or 2+ handoffs/agents | session-wrapped prompt with `Machine contract:` and explicit artifact rules |
| `t3` | `loop-heavy` | loop, checkpoint/resume, replay, or repeated rounds | session-wrapped prompt with loop invariants, checkpoint targets, and resume handles |

Automatic routing is implemented in `src/aclx/hybrid.py` and enforced by `src/aclx/supervisor.py`.

## Bundle Caps By Tier

The runtime keeps each ACL-X bundle deliberately small. The current caps come from `configs/hybrid_router_map.yaml` and `configs/tier_strategies/*.yaml`.

| Tier | Max items | State items | Evidence items | Risk items | Next items | Include completed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `t0` | 0 | 0 | 0 | 0 | 0 | no |
| `t1` | 1 | 0 | 2 | 1 | 2 | no |
| `t2` | 2 | 2 | 2 | 1 | 2 | no |
| `t3` | 3 | 3 | 2 | 2 | 2 | yes |

Practical reading:

- `t0` carries no machine bundle at all.
- `t1` keeps only enough state for one handoff contract.
- `t2` preserves outputs, constraints, scope, and next actions for multi-step repairs.
- `t3` allows one extra state slot and completed-state tracking because loop resume needs a richer cursor.

## Bridge Modes

| `bridge_mode` | Meaning | Used by |
| --- | --- | --- |
| `none` | Pure NL prompt. No ACL-X runtime bridge. | `t0` |
| `bundle` | One compact ACL-X C-layer bundle embedded directly in the prompt. | `t1` |
| `session` | Session-wrapped prompt with machine contract, artifact rules, and resumable runtime context. | `t2`, `t3` |

## Routing Signals

The classifier starts at `t0` and promotes only from runtime structure:

- Text signals such as `delegate once`, `one reviewer pass`, or `single handoff` promote to `t1`.
- Signals such as `shared state across steps`, `phase 1 and phase 2`, `implement then review`, or `multiple subagents` promote to `t2`.
- Signals such as `checkpoint and resume`, `run the verification loop`, `repeat until clean`, or `continue next round` promote to `t3`.
- Meta-only work that talks about ACL-X, routing, skills, protocols, or benchmarks without actually running handoffs stays in `t0`.

## How Users Can Override The Router

Current override surface:

- Force the style at the supervisor layer with `aclx supervisor --style adaptive|full` or `ACLXSupervisor.build_payload(..., style="adaptive")`.
- Override the profile with `aclx hybrid-prompt --profile review|implement|benchmark|debug|research` or `profile="review"` in Python.
- Override task shape in Python with `ACLXSupervisor.build_payload(..., task_shape="delegated_once"|"shared_state"|"loop")`.
- Provide hard runtime facts in Python with `expected_handoffs`, `expected_rounds`, `child_agents`, and `shared_state=True`.
- Bypass inference entirely in the prompt builder with `HybridTaskSpec(tier="t1"|"t2"|"t3")`.

Notes:

- The CLI currently exposes style and profile directly.
- Exact tier forcing is a Python API feature today.
- If `t2` or `t3` is selected without required outputs and constraints, the supervisor intentionally falls back to `t0`.

## Session Contract Rules

- `t2` preserves named files, literal format requirements, output targets, and acceptance checks.
- `t3` preserves loop invariants, checkpoint targets, and task-contract lines from `TASK.md` when the task names one.
- `style="hybrid"` is kept as a compatibility alias for `style="adaptive"`.
- `style="full"` exists for debug-heavy supervisor payloads, not as the default release path.

## Files That Define The Strategy

- `configs/hybrid_router_map.yaml`
- `configs/tier_strategies/t0.yaml`
- `configs/tier_strategies/t1.yaml`
- `configs/tier_strategies/t2.yaml`
- `configs/tier_strategies/t3.yaml`
- `src/aclx/hybrid.py`
- `src/aclx/supervisor.py`
- `configs/strategy_lock.json`
