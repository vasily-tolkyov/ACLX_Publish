from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ctx.snapshot import SnapshotStore


class SnapshotStoreTests(unittest.TestCase):
    def test_write_load_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SnapshotStore(root)
            path = store.write("integration", 5, True, {"token_reduction": 0.4}, "evaluation")
            self.assertTrue(path.exists())
            row = store.load_phase(5)
            self.assertEqual(row["phase_name"], "integration")
            validation = store.validate_all()
            self.assertEqual(validation["invalid"], 0)


if __name__ == "__main__":
    unittest.main()
