from __future__ import annotations

from pathlib import Path

from ..contract import TaskContract
from .base import ResumeDelta, checkpoint_items, checkpoint_resume_delta, completed_validator_plans, normalize_adapter_items


class GenericFilesystemAdapter:
    id = "generic-fs"

    def match(self, repo_snapshot: Path, contract: TaskContract) -> float:
        return 1.0

    def enrich_contract(self, repo_snapshot: Path, contract: TaskContract) -> TaskContract:
        outputs = {str(item or "").replace("\\", "/").strip() for item in contract.output_artifacts}
        source_refs = _unique(
            [item for item in contract.source_refs if str(item or "").replace("\\", "/").strip() not in outputs]
            + list(contract.input_artifacts)
            + list(contract.scope_in)
        )
        validator_targets = _unique(
            list(contract.validator_targets)
            + list(contract.output_artifacts)
            + list(contract.input_artifacts)
            + list(contract.scope_in)
            + list(contract.source_refs)
        )
        validator_kinds = list(contract.validator_kinds)
        if contract.operation in {"inspect", "review", "summarize", "compare"} and "inspection" not in validator_kinds:
            validator_kinds.append("inspection")
        if any(_looks_like_text_artifact(item) for item in contract.output_artifacts) and "content" not in validator_kinds:
            validator_kinds.append("content")
        if contract.acceptance_rules and "acceptance" not in validator_kinds:
            validator_kinds.append("acceptance")
        return contract.with_updates(
            source_refs=source_refs,
            validator_targets=validator_targets,
            validator_kinds=validator_kinds,
        )

    def build_read_hints(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        hints: list[str] = []
        seen: set[str] = set()
        for ref in _read_hint_refs(contract):
            normalized = str(ref or "").replace("\\", "/").strip()
            if not normalized or normalized in seen:
                continue
            path = repo_snapshot / normalized
            if path.exists():
                seen.add(normalized)
                hints.append(normalized)
        return hints[:4]

    def build_validator_plan(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        plans: list[str] = []
        outputs = list(contract.output_artifacts)
        inputs = _source_inputs(contract)
        targets = [str(target) for target in normalize_adapter_items(contract.validator_targets or outputs or contract.source_refs)[:4]]
        if outputs:
            plans.append(f"verify artifacts exist: {'; '.join(outputs[:3])}")
        if _is_python_repair_contract(contract):
            return _unique(plans)
        if inputs and contract.operation == "compare":
            plans.append(f"inspect comparison sources: {'; '.join(inputs[:2])}")
        elif inputs and contract.operation in {"inspect", "review", "summarize", "rewrite", "implement"}:
            plans.append(f"inspect referenced artifacts: {'; '.join(inputs[:2])}")
        if inputs and outputs and contract.operation in {"compare", "summarize", "rewrite", "implement"}:
            plans.append(
                "check outputs against named inputs: "
                + "; ".join(inputs[:2])
                + " -> "
                + "; ".join(outputs[:2])
            )
        for target in targets:
            lowered = target.lower()
            if lowered.endswith((".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv")):
                plans.append(f"inspect structured content requirements in {target}")
            elif lowered.endswith(".py"):
                plans.append(f"inspect python target {target}")
            else:
                plans.append(f"inspect filesystem target {target}")
        if contract.exactness_rules:
            plans.append("check literal and structural rules on named artifacts")
        if contract.acceptance_rules:
            plans.append("check acceptance rules against edited artifacts")
        if not plans and targets:
            plans.append(f"inspect named task targets: {'; '.join(targets[:3])}")
        return _unique(plans)

    def build_artifact_manifest(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        manifest = list(contract.output_artifacts)
        if not manifest:
            manifest.extend(contract.input_artifacts[:2])
        return _unique(manifest)

    def build_resume_delta(
        self,
        repo_snapshot: Path,
        contract: TaskContract,
        checkpoint: dict[str, object] | None,
    ) -> ResumeDelta:
        artifacts = normalize_adapter_items(checkpoint_items(checkpoint, "artifact_manifest") + contract.output_artifacts)
        missing_outputs = [
            artifact
            for artifact in artifacts
            if artifact and not (repo_snapshot / artifact.replace("\\", "/")).exists()
        ]
        checkpoint_delta = checkpoint_resume_delta(checkpoint)
        completed_plans = completed_validator_plans(checkpoint)
        pending_validators = [
            plan
            for plan in self.build_validator_plan(repo_snapshot, contract)
            if plan and plan not in completed_plans
        ]
        review_targets = [
            target
            for target in contract.input_artifacts + contract.source_refs
            if target and (repo_snapshot / target.replace("\\", "/")).exists()
        ]
        return ResumeDelta(
            pending_artifacts=missing_outputs,
            pending_validations=pending_validators[:4],
            read_targets=_unique(review_targets[:4]),
            carryover_items=list(checkpoint_delta.carryover_items),
        )


def _read_hint_refs(contract: TaskContract) -> list[str]:
    return _unique(
        list(contract.source_refs)
        + list(contract.input_artifacts)
        + list(contract.scope_in)
    )


def _source_inputs(contract: TaskContract) -> list[str]:
    return _unique(list(contract.input_artifacts) + list(contract.source_refs) + list(contract.scope_in))


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _looks_like_text_artifact(path_text: str) -> bool:
    lowered = str(path_text or "").lower()
    return lowered.endswith((".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv", ".log"))


def _is_python_repair_contract(contract: TaskContract) -> bool:
    if contract.operation not in {"fix", "implement"}:
        return False
    refs = list(contract.scope_in) + list(contract.source_refs) + list(contract.validator_targets)
    has_python = any(str(item or "").replace("\\", "/").strip().lower().endswith(".py") for item in refs)
    has_tests = "tests" in {str(item or "").strip().lower() for item in contract.validator_kinds} or any(
        _looks_like_python_test(str(item)) for item in contract.validator_targets
    )
    return has_python and has_tests


def _looks_like_python_test(path_text: str) -> bool:
    normalized = str(path_text or "").replace("\\", "/").strip().lower()
    if not normalized.endswith(".py"):
        return False
    name = Path(normalized).name.lower()
    return normalized.startswith("tests/") or name.startswith("test_")
