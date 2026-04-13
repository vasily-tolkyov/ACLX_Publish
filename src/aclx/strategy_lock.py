from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


LOCK_MANIFEST_RELATIVE_PATH = Path("configs") / "strategy_lock.json"


class StrategyLockError(RuntimeError):
    pass


def verify_strategy_lock(project_root: str | Path | None = None) -> dict[str, str]:
    root = Path(project_root) if project_root is not None else _repo_root()
    cache_key = str(root if root.is_absolute() else root.resolve())
    return _verify_strategy_lock_cached(cache_key)


def reset_strategy_lock_cache() -> None:
    _verify_strategy_lock_cached.cache_clear()


@lru_cache(maxsize=8)
def _verify_strategy_lock_cached(root_text: str) -> dict[str, str]:
    root = Path(root_text)
    manifest_path = root / LOCK_MANIFEST_RELATIVE_PATH
    if not manifest_path.exists():
        raise StrategyLockError(f"Strategy lock manifest missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyLockError(f"Strategy lock manifest is invalid JSON: {manifest_path}") from exc
    file_hashes = manifest.get("files")
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise StrategyLockError(f"Strategy lock manifest has no locked files: {manifest_path}")
    mismatches: list[str] = []
    checked: dict[str, str] = {}
    for relative_path, expected_hash in sorted(file_hashes.items()):
        rel_path = str(relative_path).replace("\\", "/")
        path = root / rel_path
        actual_hash = _file_sha256(path)
        checked[rel_path] = actual_hash
        if not actual_hash:
            mismatches.append(f"{rel_path} (missing)")
            continue
        if str(expected_hash).strip().lower() != actual_hash:
            mismatches.append(f"{rel_path} (expected {expected_hash}, got {actual_hash})")
    if mismatches:
        joined = "; ".join(mismatches)
        raise StrategyLockError(
            "ACL-X strategy is frozen and locked. Refusing to run with drift in: "
            f"{joined}. Update {manifest_path} only when intentionally re-baselining the strategy."
        )
    return checked


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()
