from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "formal" / "run_hybrid_pre_release_heavy.py"
SPEC = importlib.util.spec_from_file_location("formal_heavy_matrix", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FormalHeavyMatrixTests(unittest.TestCase):
    def test_build_tasks_include_validation_dimensions(self) -> None:
        tasks = MODULE.build_tasks()
        self.assertTrue(tasks)
        for task in tasks:
            self.assertTrue(task.contract_family)
            self.assertTrue(task.adapter_family)
            self.assertTrue(task.validator_type)
        t3_tasks = [task for task in tasks if task.tier == "t3"]
        self.assertTrue(all(task.resumability_expected for task in t3_tasks))

    def test_build_prompt_collects_contract_and_adapter_metadata(self) -> None:
        task = next(task for task in MODULE.build_tasks() if task.tier == "t3")
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            MODULE.write_workspace(workspace, task.workspace_files)
            run_input = MODULE.build_prompt(task, workspace, "hybrid")
            self.assertEqual(run_input.tier, task.tier)
            self.assertTrue(run_input.contract_hash)
            self.assertIn("docs", run_input.adapter_id)
            self.assertGreater(run_input.exactness_rule_count, 0)
            self.assertTrue(run_input.resumable)
            self.assertTrue(run_input.checkpointable)

    def test_build_tasks_include_generic_filesystem_coverage(self) -> None:
        tasks = MODULE.build_tasks()
        generic_tasks = [task for task in tasks if task.adapter_family == "generic-fs"]
        self.assertTrue(generic_tasks)
        self.assertTrue(any(task.contract_family.startswith("generic_") for task in generic_tasks))
        task = generic_tasks[0]
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            MODULE.write_workspace(workspace, task.workspace_files)
            run_input = MODULE.build_prompt(task, workspace, "hybrid")
            self.assertIn("generic-fs", run_input.adapter_id)

    def test_build_summary_exposes_family_breakdowns_and_coverage(self) -> None:
        tasks = MODULE.build_tasks()[:3]
        results = []
        for task in tasks:
            for arm, tokens, quality in (("baseline", 1000, 80), ("hybrid", 700, 82)):
                results.append(
                    MODULE.RunResult(
                        task_name=task.name,
                        tier=task.tier,
                        group=task.group,
                        title=task.title,
                        description=task.description,
                        arm=arm,
                        exit_code=0,
                        elapsed_seconds=1.0 if arm == "baseline" else 0.8,
                        reported_total_tokens=tokens,
                        estimated_prompt_tokens=tokens // 2,
                        estimated_output_tokens=tokens // 2,
                        estimated_total_tokens=tokens,
                        quality_score=quality,
                        quality_grade=MODULE.quality_grade(quality),
                        quality_notes=["ok"],
                        session_id=None,
                        artifact_format="markdown",
                        routed_tier=task.tier,
                        reasoning_effort="low" if arm == "hybrid" else None,
                        run_dir="tmp",
                        contract_family=task.contract_family,
                        adapter_family=task.adapter_family,
                        validator_type=task.validator_type,
                        resumability_expected=task.resumability_expected,
                        exactness_expected=task.exactness_expected,
                        contract_hash=f"hash-{task.name}",
                        adapter_id=f"generic-fs+{task.adapter_family}",
                        validator_kinds=[task.validator],
                        exactness_rule_count=1 if task.exactness_expected else 0,
                        resumable=task.resumability_expected,
                        checkpointable=task.resumability_expected,
                    )
                )
        summary = MODULE.build_summary(
            run_id="20260409_000000",
            gate_result=subprocess.CompletedProcess(args=["python"], returncode=0, stdout="", stderr=""),
            lock_mismatches=[],
            task_specs=tasks,
            results=results,
            run_root=Path(tempfile.gettempdir()),
            timeout_seconds=60,
        )
        self.assertIn("contract_families", summary)
        self.assertIn("adapter_families", summary)
        self.assertIn("validator_types", summary)
        self.assertIn("coverage", summary)
        self.assertIn("resumability", summary["coverage"])
        self.assertIn("exactness_preservation", summary["coverage"])
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.md"
            MODULE.write_markdown_report(summary, report_path)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("## Contract Family Aggregates", report)
            self.assertIn("## Adapter Family Aggregates", report)
            self.assertIn("## Validator Type Aggregates", report)
            self.assertIn("## Coverage", report)


if __name__ == "__main__":
    unittest.main()
