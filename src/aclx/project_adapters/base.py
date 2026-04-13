from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..contract import TaskContract


@dataclass(slots=True)
class ResumeDelta:
    pending_artifacts: list[str] = field(default_factory=list)
    pending_validations: list[str] = field(default_factory=list)
    read_targets: list[str] = field(default_factory=list)
    carryover_items: list[str] = field(default_factory=list)

    def merged(self, other: "ResumeDelta" | None) -> "ResumeDelta":
        if other is None:
            return ResumeDelta.from_dict(self.to_dict())
        return ResumeDelta(
            pending_artifacts=normalize_adapter_items(self.pending_artifacts + other.pending_artifacts),
            pending_validations=normalize_adapter_items(self.pending_validations + other.pending_validations),
            read_targets=normalize_adapter_items(self.read_targets + other.read_targets),
            carryover_items=normalize_adapter_items(self.carryover_items + other.carryover_items),
        )

    def is_empty(self) -> bool:
        return not any(
            (
                self.pending_artifacts,
                self.pending_validations,
                self.read_targets,
                self.carryover_items,
            )
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "pending_artifacts": normalize_adapter_items(self.pending_artifacts),
            "pending_validations": normalize_adapter_items(self.pending_validations),
            "read_targets": normalize_adapter_items(self.read_targets),
            "carryover_items": normalize_adapter_items(self.carryover_items),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResumeDelta":
        if not isinstance(data, dict):
            return cls()
        return cls(
            pending_artifacts=normalize_adapter_items(
                _coerce_items(data.get("pending_artifacts"))
                + _coerce_items(data.get("missing_artifacts"))
                + _coerce_items(data.get("missing_outputs"))
                + _coerce_items(data.get("remaining_outputs"))
            ),
            pending_validations=normalize_adapter_items(
                _coerce_items(data.get("pending_validations"))
                + _coerce_items(data.get("pending_validators"))
                + _coerce_items(data.get("pending_tests"))
            ),
            read_targets=normalize_adapter_items(
                _coerce_items(data.get("read_targets"))
                + _coerce_items(data.get("review_targets"))
            ),
            carryover_items=normalize_adapter_items(
                _coerce_items(data.get("carryover_items"))
                + _coerce_items(data.get("unresolved_rules"))
                + _coerce_items(data.get("checkpoint_unresolved"))
                + _coerce_items(data.get("checkpoint_remaining"))
            ),
        )


@dataclass(slots=True)
class ProjectContext:
    contract: TaskContract
    adapter_id: str
    read_hints: list[str] = field(default_factory=list)
    validator_plan: list[str] = field(default_factory=list)
    artifact_manifest: list[str] = field(default_factory=list)
    resume_delta: ResumeDelta = field(default_factory=ResumeDelta)


class ProjectAdapter(Protocol):
    id: str

    def match(self, repo_snapshot: Path, contract: TaskContract) -> float:
        ...

    def enrich_contract(self, repo_snapshot: Path, contract: TaskContract) -> TaskContract:
        ...

    def build_read_hints(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        ...

    def build_validator_plan(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        ...

    def build_artifact_manifest(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        ...

    def build_resume_delta(
        self,
        repo_snapshot: Path,
        contract: TaskContract,
        checkpoint: dict[str, object] | None,
    ) -> ResumeDelta:
        ...


def _coerce_items(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        return normalize_adapter_items([str(item) for item in value])
    if value is None:
        return []
    text = str(value or "").strip()
    return [text] if text else []


def normalize_adapter_items(values: list[str] | tuple[str, ...] | None) -> list[str]:
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


def checkpoint_items(checkpoint: dict[str, Any] | None, key: str) -> list[str]:
    if not isinstance(checkpoint, dict):
        return []
    value = checkpoint.get(key)
    if not isinstance(value, list):
        return []
    return normalize_adapter_items([str(item) for item in value])


def resume_delta_from_legacy_items(values: list[str] | tuple[str, ...] | None) -> ResumeDelta:
    pending_artifacts: list[str] = []
    pending_validations: list[str] = []
    read_targets: list[str] = []
    carryover_items: list[str] = []
    for raw_value in normalize_adapter_items(list(values or [])):
        key, separator, remainder = raw_value.partition("=")
        if not separator:
            carryover_items.append(raw_value)
            continue
        items = normalize_adapter_items([item.strip() for item in remainder.split(",")])
        key_text = key.strip().lower()
        if key_text in {"pending_artifacts", "missing_artifacts", "missing_outputs", "remaining_outputs"}:
            pending_artifacts.extend(items)
            continue
        if key_text in {"pending_validations", "pending_validators", "pending_tests"}:
            pending_validations.extend(items)
            continue
        if key_text in {"read_targets", "review_targets"}:
            read_targets.extend(items)
            continue
        if key_text == "checkpoint_mismatch":
            carryover_items.extend([f"checkpoint mismatch: {item}" for item in items])
            continue
        if key_text in {"carryover_items", "unresolved_rules", "checkpoint_unresolved", "checkpoint_remaining"}:
            carryover_items.extend(items)
            continue
        carryover_items.append(raw_value)
    return ResumeDelta(
        pending_artifacts=normalize_adapter_items(pending_artifacts),
        pending_validations=normalize_adapter_items(pending_validations),
        read_targets=normalize_adapter_items(read_targets),
        carryover_items=normalize_adapter_items(carryover_items),
    )


def checkpoint_resume_delta(checkpoint: dict[str, Any] | None) -> ResumeDelta:
    if not isinstance(checkpoint, dict):
        return ResumeDelta()
    typed_delta = ResumeDelta.from_dict(checkpoint.get("resume_delta") if isinstance(checkpoint.get("resume_delta"), dict) else None)
    legacy_delta = resume_delta_from_legacy_items(checkpoint_items(checkpoint, "remaining_delta"))
    return typed_delta.merged(legacy_delta)


def completed_validator_plans(checkpoint: dict[str, Any] | None) -> set[str]:
    completed: set[str] = set()
    for item in checkpoint_items(checkpoint, "validator_results"):
        prefix, separator, plan = item.partition(":")
        if separator and prefix == "ok" and plan.strip():
            completed.add(plan.strip())
    return completed
