---
name: acl-x-protocol
description: Use only for real reusable ACL-X handoffs or resumable machine-only state.
---

# ACL-X Protocol
Use ACL-X only for handoffs, shared packages, resumable state, or compact deltas another round will reuse.
Do not load it for tasks that only mention, port, document, or configure ACL-X.
Do not use it for normal replies or single-surface work.
- `t0`: never load.
- `t1`: one tiny handoff bundle.
- `t2`: compact reusable state across steps.
- `t3`: handles, checkpoints, and resumable loop state.
