# ACL-X Delegation

Use ACL-X as the default parent/child handoff format for local Codex agents.

## Rule

- If the recipient is another local Codex agent, ACL-X can be the primary payload.
- If compatibility is uncertain, prepend one short natural-language header and then the ACL-X bundle.
- Do not expand a compact ACL-X state bundle back into long prose unless the recipient is human.

## Recommended parent-to-child shape

Optional one-line header:

```text
Continue from this ACL-X state bundle.
```

Primary payload:

```text
h|c|c0|1~f|$1|ac=E.ga;aa=A.up;ob=E.tk;st=Q.op~m|sc=session;py=1;cy=.92~k|abcd1234
```

## Recommended semantic coverage

Include as needed:

- goal
- completed work
- current state
- blockers or risks
- next actions
- evidence
- certainty
- priority

## Performance guidance

- Keep ACL-X bundles compact and incremental.
- Prefer delta patches over full restatement when continuing an existing thread.
- Avoid translating natural language into ACL-X unless the artifact will actually be reused by another agent or later step.
