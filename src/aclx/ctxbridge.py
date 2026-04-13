from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = Path(__file__).resolve().parents[1]


def ensure_ctx_roots() -> None:
    for candidate in (str(REPO_ROOT), str(SRC_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


def load_ctx_module(name: str) -> ModuleType | None:
    ensure_ctx_roots()
    try:
        return importlib.import_module(f"ctx.{name}")
    except ModuleNotFoundError:
        return None


def has_ctx_runtime() -> bool:
    return load_ctx_module("session") is not None


__all__ = ["REPO_ROOT", "SRC_ROOT", "ensure_ctx_roots", "load_ctx_module", "has_ctx_runtime"]
