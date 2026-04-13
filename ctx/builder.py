from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import ACLX_SCHEMA_BLOCK, ContextBundle, ContextLayer
from .snapshot import SnapshotStore


def build_context(
    active_phase: str,
    active_content: Any,
    project_root: str | Path,
    hard_limit: int,
    *,
    include_archive: bool = True,
    layer0_budget: int = 600,
    layer1_budget: int = 2500,
    layer2_budget: int = 800,
    archive_keep: int | None = None,
    policy_file: str = ".aclx_runtime/policy_active.aclx",
    snapshot_dir: str = ".aclx_runtime/snapshots",
) -> str:
    root = Path(project_root)
    policy_path = root / policy_file
    if not policy_path.exists():
        legacy_policy = root / "ctx" / "policy_active.aclx"
        if legacy_policy.exists():
            policy_path = legacy_policy
    policy_text = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""
    resolved_snapshot_dir = snapshot_dir
    if include_archive:
        legacy_snapshot_dir = root / "snapshots"
        current_snapshot_dir = root / snapshot_dir
        if not current_snapshot_dir.exists() and legacy_snapshot_dir.exists():
            resolved_snapshot_dir = "snapshots"
    archive_store = SnapshotStore(root, resolved_snapshot_dir)
    archive_text = (
        archive_store.load_all_as_archive(limit=archive_keep) if include_archive else ""
    )
    active_text = _coerce_active_content(active_phase, active_content)
    layers = [
        ContextLayer(
            name="layer_permanent",
            header="[layer0]",
            content="\n".join(part for part in (ACLX_SCHEMA_BLOCK, policy_text) if part),
            token_budget=max(0, int(layer0_budget)),
            priority=100,
            required=True,
            drop_policy="never",
        ),
        ContextLayer(
            name="layer_active",
            header="[layer1]",
            content=active_text,
            token_budget=max(0, int(layer1_budget)),
            priority=80,
            required=True,
            drop_policy="over_budget",
        ),
    ]
    if include_archive and archive_text:
        layers.append(
            ContextLayer(
                name="layer_archive",
                header="[layer2]",
                content=archive_text,
                token_budget=max(0, int(layer2_budget)),
                priority=10,
                required=False,
                drop_policy="header_only",
            )
        )
    bundle = ContextBundle.from_layers(layers)
    return bundle.assemble(hard_limit)


def _coerce_active_content(active_phase: str, active_content: Any) -> str:
    if isinstance(active_content, str):
        return f"phase={active_phase}\n{active_content}"
    if isinstance(active_content, dict):
        lines = [f"phase={active_phase}"]
        for key, value in active_content.items():
            lines.append(f"{key}={value}")
        return "\n".join(lines)
    if isinstance(active_content, list):
        lines = [f"phase={active_phase}"]
        lines.extend(str(value) for value in active_content)
        return "\n".join(lines)
    return f"phase={active_phase}\n{active_content}"
