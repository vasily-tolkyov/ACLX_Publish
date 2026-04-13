from __future__ import annotations

from pathlib import Path

from ..contract import TaskContract
from .base import ResumeDelta


class RepoCustomAdapter:
    id = "repo-custom"

    def match(self, repo_snapshot: Path, contract: TaskContract) -> float:
        if (repo_snapshot / "AGENTS.md").exists() and (repo_snapshot / "configs").exists():
            return 0.2
        return 0.0

    def enrich_contract(self, repo_snapshot: Path, contract: TaskContract) -> TaskContract:
        metadata = dict(contract.metadata)
        metadata.setdefault("repo_has_agents", (repo_snapshot / "AGENTS.md").exists())
        metadata.setdefault("repo_has_configs", (repo_snapshot / "configs").exists())
        return contract.with_updates(metadata=metadata)

    def build_read_hints(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        return []

    def build_validator_plan(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        return []

    def build_artifact_manifest(self, repo_snapshot: Path, contract: TaskContract) -> list[str]:
        return []

    def build_resume_delta(
        self,
        repo_snapshot: Path,
        contract: TaskContract,
        checkpoint: dict[str, object] | None,
    ) -> ResumeDelta:
        return ResumeDelta()
