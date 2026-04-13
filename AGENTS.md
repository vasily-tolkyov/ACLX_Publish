# Local ACL-X Runtime

Use adaptive ACL-X routing in this workspace.

Default behavior:

- route subagent selection through `codex-subagent-router` only after real delegation starts
- `T0`: one-shot, no real handoff or loop; stay in natural language
- `T1`: first real handoff or shared package; use compact ACL-X `C-layer`
- `T2`: repeated handoffs or reusable state; use compact ACL-X plus the runtime bridge
- `T3`: loop, checkpoint, resume, or replay; use `ctx/session.py` and the runtime bridge
- summarize shell and file reads through `ctx/tool_summary.py`
- create hidden `.aclx_runtime/` files only when the tier needs them
- once a run promotes to `t2/t3`, machine state, shared artifacts, and resume/checkpoint prompts must go through `aclx-runtime`
- if a `t2/t3` prompt already includes `Machine contract` or `Loop invariants` plus an ACL-X bundle, use that contract directly and reopen runtime docs only if a required fact is missing
- on contract-complete `t2/t3` runs, do not reread `fixture.json`, `AGENTS.md`, CODEX_HOME skill docs, or hidden runtime files unless a required fact is missing
- on contract-complete `t2/t3` runs, skip plan narration and go straight to edit -> verify -> finish unless blocked
- avoid anthropic-specific dependencies or assumptions
