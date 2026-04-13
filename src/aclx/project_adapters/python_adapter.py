from __future__ import annotations

from pathlib import Path

from ..contract import TaskContract
from .base import ResumeDelta, checkpoint_items, checkpoint_resume_delta, completed_validator_plans, normalize_adapter_items


class PythonProjectAdapter:
    id = "python"

    def match(self, repo_snapshot: Path, contract: TaskContract) -> float:
        refs = contract.source_refs + contract.scope_in + contract.input_artifacts + contract.output_artifacts
        if any(str(ref).lower().endswith(".py") for ref in refs):
            return 0.95
        if (repo_snapshot / "src").exists() and (repo_snapshot / "tests").exists():
            return 0.5
        return 0.0

    def enrich_contract(self, repo_snapshot: Path, contract: TaskContract) -> TaskContract:
        source_refs = list(contract.source_refs)
        validator_targets = list(contract.validator_targets)
        for ref in contract.scope_in + contract.input_artifacts + contract.source_refs:
            normalized = str(ref or "").replace("\\", "/").strip()
            if not normalized.endswith(".py"):
                continue
            test_path = _map_python_test(repo_snapshot, normalized)
            if test_path and test_path not in source_refs:
                source_refs.append(test_path)
            if test_path and test_path not in validator_targets:
                validator_targets.append(test_path)
            if normalized not in validator_targets:
                validator_targets.append(normalized)
        validator_kinds = list(contract.validator_kinds)
        if validator_targets and "tests" not in validator_kinds:
            validator_kinds.append("tests")
        return contract.with_updates(
            source_refs=source_refs,
            validator_targets=validator_targets,
            validator_kinds=validator_kinds,
        )

    def build_read_hints(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        hints: list[str] = []
        seen: set[str] = set()
        for ref in contract.scope_in + contract.input_artifacts + contract.source_refs:
            normalized = str(ref or "").replace("\\", "/").strip()
            if not normalized.endswith(".py"):
                continue
            test_path = _map_python_test(repo_snapshot, normalized)
            if test_path and test_path not in seen:
                seen.add(test_path)
                hints.append(test_path)
            if normalized not in seen and (repo_snapshot / normalized).exists():
                seen.add(normalized)
                hints.append(normalized)
        return hints[:4]

    def build_validator_plan(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        plan: list[str] = []
        test_targets = [
            target
            for target in contract.validator_targets
            if _looks_like_python_test(str(target))
        ]
        if not test_targets:
            test_targets = [target for target in contract.validator_targets if str(target).lower().endswith(".py")]
        if test_targets:
            plan.append(f"run python -m unittest {' '.join(test_targets[:2])}")
        if contract.acceptance_rules and not test_targets:
            plan.append("check python outputs against acceptance rules")
        return plan

    def build_artifact_manifest(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        manifest = list(contract.output_artifacts)
        if any(item.lower().endswith(".py") for item in contract.output_artifacts):
            manifest.append("python-module-change")
        return _unique(manifest)

    def build_resume_delta(
        self,
        repo_snapshot: Path,
        contract: TaskContract,
        checkpoint: dict[str, object] | None,
    ) -> ResumeDelta:
        artifacts = normalize_adapter_items(checkpoint_items(checkpoint, "artifact_manifest") + contract.output_artifacts)
        missing_artifacts = [
            artifact
            for artifact in artifacts
            if artifact and artifact != "python-module-change" and not (repo_snapshot / artifact.replace("\\", "/")).exists()
        ]
        completed = completed_validator_plans(checkpoint)
        pending_tests = [
            plan
            for plan in self.build_validator_plan(repo_snapshot, contract)
            if plan.startswith("run python -m unittest") and plan not in completed
        ]
        checkpoint_delta = checkpoint_resume_delta(checkpoint)
        return ResumeDelta(
            pending_artifacts=missing_artifacts[:3],
            pending_validations=pending_tests[:2],
            carryover_items=list(checkpoint_delta.carryover_items),
        )


def _map_python_test(repo_snapshot: Path, raw: str) -> str:
    normalized = raw.replace("\\", "/")
    path = Path(normalized)
    stem = path.stem
    direct = f"tests/test_{stem}.py"
    if (repo_snapshot / direct).exists():
        return direct
    if normalized.startswith("src/"):
        nested = "tests/" + normalized[len("src/") :]
        if (repo_snapshot / nested).exists():
            return nested
    return ""


def _looks_like_python_test(path_text: str) -> bool:
    normalized = str(path_text or "").replace("\\", "/").strip().lower()
    if not normalized.endswith(".py"):
        return False
    name = Path(normalized).name.lower()
    return normalized.startswith("tests/") or name.startswith("test_")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique
