# ACL-X Runtime

Use this guide when the goal is to maximize ACL-X usage across local Codex agent workflows.

## What can be the default visible runtime

- layered runtime context
- agent-to-agent handoffs
- resumable state bundles
- machine-only summaries
- parent/child delegation payloads
- tool-summary replay
- policy-aware session assembly

## What cannot be directly enforced

- hidden model-internal chain-of-thought
- tool-native external schemas
- human-facing final prose unless the user asks for ACL-X

## Default runtime rule

If an artifact is:

- not primarily for a human, and
- not directly for an external tool

then prefer ACL-X.

## Runtime order

1. Keep runtime-visible state in ACL-X.
2. Build layered context from schema, policy, active phase, summaries, and snapshots.
3. Pass ACL-X directly between local agents.
4. Convert to compact tool JSON only at tool boundaries.
5. Convert to natural-language gloss only at human boundaries.

## Default guidance

- Use the local ctx runtime when it exists.
- Keep delegation payloads compact and incremental.
- Prefer ACL-X snapshots over long prose restatements.
- Do not ask the operator to run manual ACL-X commands unless debugging the runtime itself.
