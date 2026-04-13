from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contract import TaskContract
from .project_adapters.base import ResumeDelta, resume_delta_from_legacy_items


def _clean_list(values: list[str] | None) -> list[str]:
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
class CheckpointState:
    active_phase: str
    task_description: str
    runtime_bundle: str
    runtime_tier: str
    required_artifacts: list[str] = field(default_factory=list)
    acceptance_contract: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)
    policy_hash: str = ""
    contract: TaskContract | None = None
    contract_hash: str = ""
    adapter_id: str = ""
    artifact_manifest: list[str] = field(default_factory=list)
    validator_plan: list[str] = field(default_factory=list)
    validator_results: list[str] = field(default_factory=list)
    unresolved_items: list[str] = field(default_factory=list)
    resume_delta: ResumeDelta = field(default_factory=ResumeDelta)

    def to_dict(self) -> dict[str, Any]:
        contract_dict = self.contract.to_dict() if self.contract is not None else None
        contract_hash = self.contract_hash or (self.contract.contract_hash() if self.contract is not None else "")
        return {
            "active_phase": self.active_phase,
            "task_description": self.task_description,
            "runtime_bundle": self.runtime_bundle,
            "required_artifacts": _clean_list(self.required_artifacts),
            "acceptance_contract": _clean_list(self.acceptance_contract),
            "stop_conditions": _clean_list(self.stop_conditions),
            "next_actions": _clean_list(self.next_actions),
            "tool_summaries": _clean_list(self.tool_summaries),
            "policy_hash": self.policy_hash,
            "runtime_tier": self.runtime_tier,
            "contract": contract_dict,
            "contract_hash": contract_hash,
            "adapter_id": self.adapter_id,
            "artifact_manifest": _clean_list(self.artifact_manifest),
            "validator_plan": _clean_list(self.validator_plan),
            "validator_results": _clean_list(self.validator_results),
            "unresolved_items": _clean_list(self.unresolved_items),
            "resume_delta": self.resume_delta.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CheckpointState":
        payload = dict(data or {})
        contract = payload.get("contract")
        resume_delta = ResumeDelta.from_dict(payload.get("resume_delta") if isinstance(payload.get("resume_delta"), dict) else None)
        resume_delta = resume_delta.merged(resume_delta_from_legacy_items(list(payload.get("remaining_delta") or [])))
        return cls(
            active_phase=str(payload.get("active_phase") or ""),
            task_description=str(payload.get("task_description") or ""),
            runtime_bundle=str(payload.get("runtime_bundle") or ""),
            runtime_tier=str(payload.get("runtime_tier") or ""),
            required_artifacts=list(payload.get("required_artifacts") or []),
            acceptance_contract=list(payload.get("acceptance_contract") or []),
            stop_conditions=list(payload.get("stop_conditions") or []),
            next_actions=list(payload.get("next_actions") or []),
            tool_summaries=list(payload.get("tool_summaries") or []),
            policy_hash=str(payload.get("policy_hash") or ""),
            contract=TaskContract.from_dict(contract) if isinstance(contract, dict) else None,
            contract_hash=str(payload.get("contract_hash") or ""),
            adapter_id=str(payload.get("adapter_id") or ""),
            artifact_manifest=list(payload.get("artifact_manifest") or []),
            validator_plan=list(payload.get("validator_plan") or []),
            validator_results=list(payload.get("validator_results") or []),
            unresolved_items=list(payload.get("unresolved_items") or []),
            resume_delta=resume_delta,
        )
