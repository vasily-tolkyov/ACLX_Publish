from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from aclx.adapters import ACLXAdapter


@dataclass(slots=True)
class Constraint:
    target: str
    action: str
    note: str = ""

    def allows(self, target: str, action: str) -> bool:
        return fnmatch(target, self.target) and fnmatch(action, self.action)

    def applies_to(self, target: str) -> bool:
        return fnmatch(target, self.target)

    def to_aclx(self) -> str:
        adapter = ACLXAdapter()
        handoff = {
            "current_state": [f"target={self.target}", f"action={self.action}"],
            "evidence": [self.note] if self.note else [],
            "source": "ctx.policy",
            "scope": "policy",
            "certainty": 1.0,
        }
        return adapter.handoff_obj_to_aclx(handoff, mode="c")


@dataclass(slots=True)
class PolicySpec:
    constraints: list[Constraint]

    def to_aclx_block(self) -> str:
        adapter = ACLXAdapter()
        evidence = [f"{constraint.target}:{constraint.action}" for constraint in self.constraints]
        return adapter.handoff_obj_to_aclx(
            {
                "current_state": [f"constraints={len(self.constraints)}"],
                "evidence": evidence,
                "source": "ctx.policy",
                "scope": "policy",
                "certainty": 1.0,
            },
            mode="c",
        )
    def validate_action(self, target: str, action: str) -> tuple[bool, str]:
        relevant = [constraint for constraint in self.constraints if constraint.applies_to(target)]
        if not relevant:
            return True, "no matching constraint"
        for constraint in relevant:
            if constraint.allows(target, action):
                return True, f"allowed by {constraint.target} -> {constraint.action}"
        allowed = ", ".join(sorted({constraint.action for constraint in relevant}))
        return False, f"blocked for {target}; allowed actions: {allowed}"


DEFAULT_CONSTRAINTS = [
    Constraint("mod=aclx/*", "readonly", "Do not edit ACL-X core codec without explicit reason."),
    Constraint("mod=reasoner/*", "readonly", "Do not edit reasoner internals during ctx integration."),
    Constraint("mod=ctx/*", "write_ok", "Ctx modules are the main implementation surface."),
    Constraint("dir=.aclx_runtime/snapshots/*", "write_ok", "Snapshots are runtime state artifacts."),
    Constraint("dir=.aclx_runtime/checkpoints/*", "write_ok", "Checkpoints are resumable state artifacts."),
    Constraint("gate=human", "no_auto", "Human approval gates stay explicit."),
]


def generate_policy_file(
    root: str | Path,
    constraints: Iterable[Constraint] | None = None,
    policy_file: str = ".aclx_runtime/policy_active.aclx",
) -> Path:
    base = Path(root)
    path = base / policy_file
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = PolicySpec(list(constraints or DEFAULT_CONSTRAINTS))
    content = spec.to_aclx_block()
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return path
    path.write_text(content, encoding="utf-8")
    return path
