from __future__ import annotations

from pathlib import Path

from ..contract import TaskContract
from ..contract_normalizer import extract_exactness_rules, extract_source_refs
from .base import ResumeDelta, checkpoint_items, checkpoint_resume_delta, completed_validator_plans, normalize_adapter_items


class DocsProjectAdapter:
    id = "docs"

    def match(self, repo_snapshot: Path, contract: TaskContract) -> float:
        refs = contract.source_refs + contract.output_artifacts + contract.input_artifacts
        if any(str(ref).lower().endswith((".md", ".rst", ".txt")) for ref in refs):
            return 0.92
        return 0.0

    def enrich_contract(self, repo_snapshot: Path, contract: TaskContract) -> TaskContract:
        exactness_rules = list(contract.exactness_rules)
        source_refs = list(contract.source_refs)
        for ref in list(contract.source_refs):
            normalized = str(ref or "").replace("\\", "/").strip()
            if not normalized.lower().endswith((".md", ".rst", ".txt")):
                continue
            path = repo_snapshot / normalized
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for rule in extract_exactness_rules(text):
                if rule not in exactness_rules:
                    exactness_rules.append(rule)
            for nested_ref in extract_source_refs(text):
                if nested_ref not in source_refs:
                    source_refs.append(nested_ref)
        return contract.with_updates(exactness_rules=exactness_rules, source_refs=source_refs)

    def build_read_hints(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        hints: list[str] = []
        seen: set[str] = set()
        for ref in contract.source_refs:
            normalized = str(ref or "").replace("\\", "/").strip()
            if not normalized.lower().endswith((".md", ".rst", ".txt")):
                continue
            if normalized not in seen and (repo_snapshot / normalized).exists():
                seen.add(normalized)
                hints.append(normalized)
        return hints[:3]

    def build_validator_plan(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        if _is_auxiliary_docs_validation(contract):
            return []
        plan: list[str] = []
        targets = _doc_targets(contract)
        if contract.exactness_rules and targets:
            plan.append(f"check docs wording: {'; '.join(targets[:2])}")
        if targets:
            plan.append(f"inspect docs outputs: {'; '.join(targets[:2])}")
        if contract.acceptance_rules and targets:
            plan.append(f"check docs acceptance: {'; '.join(targets[:2])}")
        return plan

    def build_artifact_manifest(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        return [
            item
            for item in contract.output_artifacts
            if str(item).lower().endswith((".md", ".rst", ".txt"))
        ]

    def build_resume_delta(
        self,
        repo_snapshot: Path,
        contract: TaskContract,
        checkpoint: dict[str, object] | None,
    ) -> ResumeDelta:
        unresolved = [rule for rule in contract.exactness_rules if "heading" in rule.lower() or "include" in rule.lower()]
        artifacts = normalize_adapter_items(checkpoint_items(checkpoint, "artifact_manifest") + contract.output_artifacts)
        missing_outputs = [
            artifact
            for artifact in artifacts
            if artifact and not (repo_snapshot / artifact.replace("\\", "/")).exists()
        ]
        completed = completed_validator_plans(checkpoint)
        pending_validators = [
            plan
            for plan in self.build_validator_plan(repo_snapshot, contract)
            if plan not in completed
        ]
        checkpoint_delta = checkpoint_resume_delta(checkpoint)
        return ResumeDelta(
            pending_artifacts=missing_outputs[:3],
            pending_validations=pending_validators[:3],
            carryover_items=normalize_adapter_items(
                unresolved[:6] + checkpoint_delta.carryover_items
            ),
        )


def _doc_targets(contract: TaskContract) -> list[str]:
    output_targets = _unique_doc_paths(contract.output_artifacts)
    if output_targets:
        return output_targets
    return _unique_doc_paths(contract.source_refs)


def _unique_doc_paths(values: list[str]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").replace("\\", "/").strip()
        if not normalized.lower().endswith((".md", ".rst", ".txt")):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        targets.append(normalized)
    return targets


def _is_auxiliary_docs_validation(contract: TaskContract) -> bool:
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
