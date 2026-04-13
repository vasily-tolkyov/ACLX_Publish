from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "formal" / "run_hybrid_general_task_heavy.py"
SPEC = importlib.util.spec_from_file_location("formal_general_task_heavy", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class GeneralTaskHeavyMatrixTests(unittest.TestCase):
    def test_build_tasks_use_generic_non_aclx_outputs(self) -> None:
        tasks = MODULE.build_tasks()
        self.assertEqual(len(tasks), 12)
        self.assertTrue(all("aclx" not in task.title.lower() for task in tasks))
        non_t0_outputs = [output for task in tasks for output in task.outputs if task.outputs]
        self.assertFalse(any(str(output).lower().endswith(".aclx") for output in non_t0_outputs))

    def test_t2_tasks_emit_generic_artifact_constraints(self) -> None:
        t2_tasks = [task for task in MODULE.build_tasks() if task.tier == "t2"]
        self.assertEqual(len(t2_tasks), 3)
        self.assertTrue(all(task.validator == "t2_generic" for task in t2_tasks))
        self.assertTrue(all("machine-readable handoff" in " ".join(task.constraints).lower() or "handoff keys" in " ".join(task.constraints).lower() for task in t2_tasks))

    def test_hybrid_prompt_builder_keeps_expected_tiers_for_generic_tasks(self) -> None:
        tasks = MODULE.build_tasks()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for expected_tier in ("t0", "t1", "t2", "t3"):
                task = next(item for item in tasks if item.tier == expected_tier)
                workspace = root / task.name
                MODULE.base.write_workspace(workspace, task.workspace_files)
                run_input = MODULE.base.build_prompt(task, workspace, "hybrid")
                self.assertEqual(run_input.tier, expected_tier)


if __name__ == "__main__":
    unittest.main()
