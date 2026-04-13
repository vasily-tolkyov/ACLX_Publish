from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


def _clean_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


@dataclass(slots=True)
class RuntimeNeeds:
    surface_count: int = 1
    expected_handoffs: int = 0
    expected_rounds: int = 1
    child_agents: int = 0
    shared_state: bool = False
    checkpointable: bool = False
    resumable: bool = False
    loop_heavy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface_count": int(self.surface_count),
            "expected_handoffs": int(self.expected_handoffs),
            "expected_rounds": int(self.expected_rounds),
            "child_agents": int(self.child_agents),
            "shared_state": bool(self.shared_state),
            "checkpointable": bool(self.checkpointable),
            "resumable": bool(self.resumable),
            "loop_heavy": bool(self.loop_heavy),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RuntimeNeeds":
        payload = data or {}
        return cls(
            surface_count=max(1, int(payload.get("surface_count", 1) or 1)),
            expected_handoffs=max(0, int(payload.get("expected_handoffs", 0) or 0)),
            expected_rounds=max(1, int(payload.get("expected_rounds", 1) or 1)),
            child_agents=max(0, int(payload.get("child_agents", 0) or 0)),
            shared_state=bool(payload.get("shared_state", False)),
            checkpointable=bool(payload.get("checkpointable", False)),
            resumable=bool(payload.get("resumable", False)),
            loop_heavy=bool(payload.get("loop_heavy", False)),
        )


@dataclass(slots=True)
class TaskContract:
    goal: str
    operation: str
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    input_artifacts: list[str] = field(default_factory=list)
    output_artifacts: list[str] = field(default_factory=list)
    exactness_rules: list[str] = field(default_factory=list)
    acceptance_rules: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    validator_kinds: list[str] = field(default_factory=list)
    validator_targets: list[str] = field(default_factory=list)
    runtime_needs: RuntimeNeeds = field(default_factory=RuntimeNeeds)
    source_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.goal = str(self.goal or "").strip()
        self.operation = str(self.operation or "inspect").strip() or "inspect"
        self.scope_in = _clean_list(self.scope_in)
        self.scope_out = _clean_list(self.scope_out)
        self.input_artifacts = _clean_list(self.input_artifacts)
        self.output_artifacts = _clean_list(self.output_artifacts)
        self.exactness_rules = _clean_list(self.exactness_rules)
        self.acceptance_rules = _clean_list(self.acceptance_rules)
        self.stop_conditions = _clean_list(self.stop_conditions)
        self.next_actions = _clean_list(self.next_actions)
        self.validator_kinds = _clean_list(self.validator_kinds)
        self.validator_targets = _clean_list(self.validator_targets)
        self.source_refs = _clean_list(self.source_refs)
        if not isinstance(self.runtime_needs, RuntimeNeeds):
            self.runtime_needs = RuntimeNeeds.from_dict(dict(self.runtime_needs or {}))
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["runtime_needs"] = self.runtime_needs.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskContract":
        payload = dict(data or {})
        return cls(
            goal=str(payload.get("goal", "") or ""),
            operation=str(payload.get("operation", "inspect") or "inspect"),
            scope_in=list(payload.get("scope_in") or []),
            scope_out=list(payload.get("scope_out") or []),
            input_artifacts=list(payload.get("input_artifacts") or []),
            output_artifacts=list(payload.get("output_artifacts") or []),
            exactness_rules=list(payload.get("exactness_rules") or []),
            acceptance_rules=list(payload.get("acceptance_rules") or []),
            stop_conditions=list(payload.get("stop_conditions") or []),
            next_actions=list(payload.get("next_actions") or []),
            validator_kinds=list(payload.get("validator_kinds") or []),
            validator_targets=list(payload.get("validator_targets") or []),
            runtime_needs=RuntimeNeeds.from_dict(payload.get("runtime_needs")),
            source_refs=list(payload.get("source_refs") or []),
            metadata=dict(payload.get("metadata") or {}),
        )

    def contract_hash(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def with_updates(self, **updates: Any) -> "TaskContract":
        data = self.to_dict()
        data.update(updates)
        return TaskContract.from_dict(data)

    def merge_missing(self, other: "TaskContract | None") -> "TaskContract":
        if other is None:
            return self
        merged = self.to_dict()
        other_data = other.to_dict()
        for key in (
            "scope_in",
            "scope_out",
            "input_artifacts",
            "output_artifacts",
            "exactness_rules",
            "acceptance_rules",
            "stop_conditions",
            "next_actions",
            "validator_kinds",
            "validator_targets",
            "source_refs",
        ):
            merged[key] = _clean_list(list(merged.get(key) or []) + list(other_data.get(key) or []))
        metadata = dict(other_data.get("metadata") or {})
        metadata.update(dict(merged.get("metadata") or {}))
        merged["metadata"] = metadata
        if not str(merged.get("goal") or "").strip():
            merged["goal"] = other.goal
        if not str(merged.get("operation") or "").strip():
            merged["operation"] = other.operation
        runtime = RuntimeNeeds.from_dict(other_data.get("runtime_needs")).to_dict()
        current_runtime = RuntimeNeeds.from_dict(merged.get("runtime_needs")).to_dict()
        merged["runtime_needs"] = {
            "surface_count": max(int(current_runtime["surface_count"]), int(runtime["surface_count"])),
            "expected_handoffs": max(int(current_runtime["expected_handoffs"]), int(runtime["expected_handoffs"])),
            "expected_rounds": max(int(current_runtime["expected_rounds"]), int(runtime["expected_rounds"])),
            "child_agents": max(int(current_runtime["child_agents"]), int(runtime["child_agents"])),
            "shared_state": bool(current_runtime["shared_state"] or runtime["shared_state"]),
            "checkpointable": bool(current_runtime["checkpointable"] or runtime["checkpointable"]),
            "resumable": bool(current_runtime["resumable"] or runtime["resumable"]),
            "loop_heavy": bool(current_runtime["loop_heavy"] or runtime["loop_heavy"]),
        }
        return TaskContract.from_dict(merged)
