from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "t23_real_ab_runner.py"
SPEC = importlib.util.spec_from_file_location("t23_real_ab_runner", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class T23RealABRunnerTests(unittest.TestCase):
    def test_fixtures_expose_required_contract_fields(self) -> None:
        for name, tier in (("t2_shared_state_task", "t2"), ("t3_loop_skill_task", "t3")):
            fixture = MODULE.load_fixture(name)
            self.assertEqual(fixture["tier"], tier)
            self.assertTrue(fixture["outputs"])
            self.assertTrue(fixture["constraints"])
            self.assertTrue(fixture["next_actions"])

    def test_hybrid_prompt_builder_wraps_t2_and_t3_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, marker in (
                ("t2_shared_state_task", "Machine contract:"),
                ("t3_loop_skill_task", "Loop invariants:"),
            ):
                fixture = MODULE.load_fixture(name)
                workspace = root / name
                shutil.copytree(Path(str(fixture["fixture_dir"])), workspace)
                run_input = MODULE.build_prompt(fixture, workspace, "hybrid")
                self.assertEqual(run_input.tier, fixture["tier"])
                self.assertIn(marker, run_input.prompt)
                self.assertIn("h|c|c0|1", run_input.prompt)


if __name__ == "__main__":
    unittest.main()
