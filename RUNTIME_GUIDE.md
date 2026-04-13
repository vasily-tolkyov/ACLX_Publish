# ACL-X Runtime Guide

Chinese version: [RUNTIME_GUIDE.zh-CN.md](RUNTIME_GUIDE.zh-CN.md).

This guide describes the adaptive default visible runtime path for ACL-X in local Codex.

## Tiered default

Start at the lowest fitting tier.

- `t0` `nl-lean`: single-shot or no-loop work. Stay in natural language and delay ACL-X activation.
- `t1` `handoff-lite`: one file-backed machine-only artifact or one real handoff. Keep the task in natural language and use only a tiny ACL-X package or pointer.
- `t2` `balanced`: multi-agent or reusable shared state. Keep task and answer text in natural language; move machine-only state through the runtime bridge with explicit `Must write` and `Done when` contracts.
- `t3` `loop-heavy`: repeated handoff or resume loop. The first prompt and every resume prompt must flow through the runtime bridge so checkpoint artifacts and loop invariants are restated alongside the ACL-X handle.

## Promotion rule

Promote only after real handoff, resume, or shared-state evidence exists. Do not pay ACL-X archive cost up front for single-shot tasks that merely mention handoffs, queues, triads, or ACL-X.

Once a run promotes to `t2` or `t3`, do not fall back to free-text machine state. Shared artifacts, checkpoint prompts, and resume prompts must continue through `ctx/session.py` or the plugin bridge.

## Files

- `configs/hybrid_router_map.yaml`
- `src/aclx/hybrid.py`
- `src/aclx/supervisor.py`
- `ctx/session.py`

## Machine hookup

The default policy is surfaced through:

- `<CODEX_HOME>/AGENTS.md`
- `<CODEX_HOME>/config.toml`
- `<ACLX_PLUGIN_SKILL_ROOT>/SKILL.md`
- `<CODEX_HOME>/plugins/cache/local-user-plugins/aclx-runtime/local`

Restart Codex after changing global instructions or plugin files so new sessions pick up the new default.

## Host Compatibility

The default-on installation path described in this guide is Codex-specific.

This repository can still provide portable routing, prompt, and runtime components to other agent hosts, but those hosts must integrate the strategy manually.

This guide does not claim a packaged default-on installer for arbitrary non-Codex hosts. For the exact release boundary, read [docs/agent_compatibility.md](docs/agent_compatibility.md).

`style="hybrid"` is a compatibility alias for `style="adaptive"`. It must not force a `t1` bundle when the runtime facts still fit `t0`.
