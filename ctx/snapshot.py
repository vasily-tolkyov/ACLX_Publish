from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aclx.adapters import ACLXAdapter

from .compressor import compress_phase_to_aclx


class SnapshotStore:
    def __init__(self, root: str | Path, snapshot_dir: str = "snapshots") -> None:
        self.root = Path(root)
        self.snapshot_dir = self.root / snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.adapter = ACLXAdapter()

    def write(
        self,
        phase_name: str,
        phase_idx: int,
        gate_passed: bool,
        metrics: dict[str, Any] | None,
        next_phase: str | None,
    ) -> Path:
        payload = compress_phase_to_aclx(phase_name, phase_idx, gate_passed, metrics, next_phase)
        path = self.snapshot_dir / f"{phase_idx:02d}_{_slugify(phase_name)}.aclx"
        path.write_text(payload, encoding="utf-8")
        return path

    def load_all(self) -> list[dict[str, Any]]:
        rows = []
        for path in self._snapshot_paths():
            aclx = path.read_text(encoding="utf-8")
            handoff = self.adapter.frame_to_handoff_obj(self.adapter.codec.decode(aclx))
            meta = _extract_meta(handoff)
            rows.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "aclx": aclx,
                    "handoff": handoff,
                    **meta,
                }
            )
        return rows

    def load_all_as_archive(self, *, limit: int | None = None) -> str:
        # Archive assembly for context replay only needs raw ACL-X frames.
        # Skip decode/metadata extraction on the hot path.
        return "\n".join(path.read_text(encoding="utf-8") for path in self._snapshot_paths(limit=limit))

    def load_phase(self, idx: int) -> dict[str, Any]:
        for row in self.load_all():
            if int(row.get("phase_idx", -1)) == idx:
                return row
        raise FileNotFoundError(f"snapshot phase {idx} not found")

    def validate_all(self) -> dict[str, Any]:
        valid = 0
        invalid = 0
        errors = []
        for path in self._snapshot_paths():
            try:
                self.adapter.codec.decode(path.read_text(encoding="utf-8"))
            except Exception as exc:
                invalid += 1
                errors.append({"path": str(path), "error": str(exc)})
            else:
                valid += 1
        return {"valid": valid, "invalid": invalid, "errors": errors}

    def _snapshot_paths(self, *, limit: int | None = None) -> list[Path]:
        paths = sorted(self.snapshot_dir.glob("*.aclx"))
        if limit is None or limit <= 0 or len(paths) <= limit:
            return paths
        return paths[-limit:]


def _extract_meta(handoff: dict[str, Any]) -> dict[str, Any]:
    evidence = handoff.get("e") or handoff.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    for item in evidence:
        try:
            data = json.loads(item)
        except Exception:
            continue
        if isinstance(data, dict) and "phase_idx" in data:
            return data
    return {}


def _slugify(value: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in value]
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "phase"
