# ACL-X Reference

## Core idea

ACL-X is a compact ASCII protocol for agent-visible semantic frames.

- `T-layer`: lighter visible scratch or draft form
- `C-layer`: transport, persistence, handoff, and audit form

## Canonical clause slots

- `ac` actor
- `aa` action
- `ob` object
- `cx` context
- `ct` constraint
- `ev` evidence
- `st` status

## Common symbols in `c0@1`

- `E.ga` agent
- `E.tk` task
- `E.rs` result
- `E.tl` tool
- `E.er` error
- `A.pl` plan
- `A.rp` report
- `A.up` update
- `A.vf` verify
- `A.ex` explain
- `A.th` think
- `Q.go` goal
- `Q.dn` done
- `Q.bk` blocked
- `Q.qa` ask

## Minimal examples

Plan a task:

```text
h|c|c0|1~f|$1|ac=E.ga;aa=A.pl;ob=E.tk~k|daaf24c5
```

Conditional explanation:

```text
h|c|c0|1~f|$1|ac=E.ga;aa=A.ex;ob=E.tl|cd=true~k|fb8bf1fd
```

Visible thought draft:

```text
h|t|c0|1~f|$1|aa=A.th;ob=E.tk
```

Escape block for open text:

```text
h|c|c0|1~e|!1|raw|"Need a nuanced summary with edge cases."|"text/plain"~f|$1|ac=E.ga;aa=A.rp;ob=E.rs;cx=!1~k|1fa9f1ce
```

## Recommended usage split

- User-facing answer: natural language
- Agent-facing handoff: ACL-X
- Tool boundary: JSON or native schema
- Long-form semantics that cannot be safely compressed: escape block

## Local commands

```powershell
$env:PYTHONPATH='D:\codex\acl_x\src'; python -m aclx demo
$env:PYTHONPATH='D:\codex\acl_x\src'; python -m aclx benchmark
$env:PYTHONPATH='D:\codex\acl_x\src'; python -m aclx encode-nl "If the tool fails, explain the error."
```
