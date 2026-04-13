from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aclx.strategy_lock import StrategyLockError, reset_strategy_lock_cache, verify_strategy_lock

REPO_ROOT = Path(__file__).resolve().parents[1]


class StrategyLockTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_strategy_lock_cache()

    def test_real_strategy_manifest_verifies(self) -> None:
        checked = verify_strategy_lock(project_root=REPO_ROOT)
        self.assertIn("configs/hybrid_router_map.yaml", checked)
        self.assertIn("configs/tier_strategies/t0.yaml", checked)
        self.assertIn("configs/tier_strategies/t1.yaml", checked)
        self.assertIn("configs/tier_strategies/t2.yaml", checked)
        self.assertIn("configs/tier_strategies/t3.yaml", checked)
        self.assertIn("configs/ctx.yaml", checked)
        self.assertIn("ctx/session.py", checked)
        self.assertIn("src/aclx/hybrid.py", checked)
        self.assertIn("src/aclx/supervisor.py", checked)

    def test_strategy_lock_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "alpha.txt").write_text("alpha\n", encoding="utf-8")
            (root / "nested").mkdir(parents=True)
            (root / "nested" / "beta.txt").write_text("beta\n", encoding="utf-8")
            (root / "configs" / "strategy_lock.json").write_text(
                json.dumps(
                    {
                        "lock_name": "test-lock",
                        "files": {
                            "alpha.txt": _sha256(root / "alpha.txt"),
                            "nested/beta.txt": _sha256(root / "nested" / "beta.txt"),
                        },
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            checked = verify_strategy_lock(project_root=root)
            self.assertEqual(checked["alpha.txt"], _sha256(root / "alpha.txt"))
            (root / "alpha.txt").write_text("tampered\n", encoding="utf-8")
            reset_strategy_lock_cache()
            with self.assertRaises(StrategyLockError):
                verify_strategy_lock(project_root=root)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
