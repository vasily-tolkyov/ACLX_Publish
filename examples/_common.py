from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src" / "aclx").exists():
            return parent
    raise RuntimeError("Could not find the repository root that contains src/aclx.")


def ensure_repo_src() -> Path:
    root = repo_root()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def dump_payload(name: str, payload: Any, *, workspace: Path | None = None, extra: dict[str, Any] | None = None) -> None:
    data: dict[str, Any] = {
        "example": name,
        "tier": getattr(payload, "tier", None),
        "bridge_mode": getattr(payload, "bridge_mode", None),
        "workspace": str(workspace) if workspace is not None else None,
        "prompt": getattr(payload, "codex_prompt", None) or getattr(payload, "prompt", None),
        "aclx_bundle": getattr(payload, "aclx_bundle", ""),
        "reasoning_effort": getattr(payload, "reasoning_effort", None),
    }
    if extra:
        data.update(extra)
    print(json.dumps(data, ensure_ascii=True, indent=2))
