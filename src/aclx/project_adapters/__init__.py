from __future__ import annotations

from pathlib import Path

from ..contract import TaskContract
from .base import ProjectAdapter, ProjectContext, ResumeDelta
from .docs_adapter import DocsProjectAdapter
from .generic_fs import GenericFilesystemAdapter
from .python_adapter import PythonProjectAdapter
from .repo_custom import RepoCustomAdapter


def default_project_adapters() -> list[ProjectAdapter]:
    return [
        GenericFilesystemAdapter(),
        PythonProjectAdapter(),
        DocsProjectAdapter(),
        RepoCustomAdapter(),
    ]


def select_project_adapters(repo_snapshot: Path, contract: TaskContract) -> list[ProjectAdapter]:
    selected: list[tuple[float, ProjectAdapter]] = []
    for adapter in default_project_adapters():
        score = float(adapter.match(repo_snapshot, contract))
        if score <= 0.0:
            continue
        selected.append((score, adapter))
    selected.sort(key=lambda item: item[0], reverse=True)
    ordered = [adapter for _score, adapter in selected]
    generic = next((adapter for adapter in ordered if adapter.id == "generic-fs"), None)
    if generic is not None:
        ordered = [generic] + [adapter for adapter in ordered if adapter.id != "generic-fs"]
    return ordered


def build_project_context(
    repo_snapshot: str | Path,
    contract: TaskContract,
    *,
    checkpoint: dict[str, object] | None = None,
) -> ProjectContext:
    root = Path(repo_snapshot)
    selected = select_project_adapters(root, contract)
    enriched = contract
    adapter_ids: list[str] = []
    read_hints: list[str] = []
    validator_plan: list[str] = []
    artifact_manifest: list[str] = []
    resume_delta = ResumeDelta()
    for adapter in selected:
        adapter_ids.append(adapter.id)
        enriched = adapter.enrich_contract(root, enriched)
    for adapter in selected:
        read_hints.extend(adapter.build_read_hints(root, enriched))
        validator_plan.extend(adapter.build_validator_plan(root, enriched))
        artifact_manifest.extend(adapter.build_artifact_manifest(root, enriched))
        delta = adapter.build_resume_delta(root, enriched, checkpoint)
        if not delta.is_empty():
            resume_delta = resume_delta.merged(delta)
    return ProjectContext(
        contract=enriched,
        adapter_id="+".join(adapter_ids) if adapter_ids else "generic-fs",
        read_hints=_unique(read_hints),
        validator_plan=_unique(validator_plan),
        artifact_manifest=_unique(artifact_manifest or enriched.output_artifacts),
        resume_delta=resume_delta,
    )


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


__all__ = [
    "ProjectAdapter",
    "ProjectContext",
    "ResumeDelta",
    "GenericFilesystemAdapter",
    "PythonProjectAdapter",
    "DocsProjectAdapter",
    "RepoCustomAdapter",
    "build_project_context",
    "default_project_adapters",
    "select_project_adapters",
]
