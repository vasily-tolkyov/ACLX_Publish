from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aclx.contract import RuntimeNeeds, TaskContract
from aclx.contract_normalizer import normalize_task_to_contract
from aclx.project_adapters import build_project_context


class ContractTests(unittest.TestCase):
    def test_task_contract_roundtrip_and_hash_is_stable(self) -> None:
        contract = TaskContract(
            goal="Rewrite the release guide.",
            operation="rewrite",
            output_artifacts=["docs/release_guide.md"],
            exactness_rules=["keep heading `# release guide`"],
            runtime_needs=RuntimeNeeds(checkpointable=True, resumable=True, loop_heavy=True),
        )
        restored = TaskContract.from_dict(contract.to_dict())
        self.assertEqual(restored.to_dict(), contract.to_dict())
        self.assertEqual(restored.contract_hash(), contract.contract_hash())

    def test_normalizer_prefers_explicit_runtime_structure_over_text(self) -> None:
        contract = normalize_task_to_contract(
            "Discuss checkpoint and resume tradeoffs without actually starting a loop.",
            expected_handoffs=0,
            expected_rounds=1,
            child_agents=0,
            shared_state=False,
        )
        self.assertFalse(contract.runtime_needs.loop_heavy)
        self.assertFalse(contract.runtime_needs.resumable)

    def test_project_context_uses_python_and_docs_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "docs").mkdir()
            (root / "TASK.md").write_text(
                "Rewrite `docs/release_guide.md`.\n"
                "- keep heading `# release guide`\n"
                "- include `next step` in `docs/release_guide.md`\n",
                encoding="utf-8",
            )
            (root / "src" / "feature.py").write_text("def feature():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "test_feature.py").write_text("import unittest\n", encoding="utf-8")
            contract = normalize_task_to_contract(
                "Read TASK.md.\nFix `src/feature.py`.\nWrite `docs/release_guide.md`.",
                required_artifacts=["docs/release_guide.md"],
                scope_in=["src/feature.py"],
            )
            context = build_project_context(root, contract)
            self.assertIn("generic-fs", context.adapter_id)
            self.assertIn("python", context.adapter_id)
            self.assertIn("docs", context.adapter_id)
            self.assertIn("src/feature.py", context.read_hints)
            self.assertIn("tests/test_feature.py", context.read_hints)
            self.assertIn("TASK.md", context.read_hints)
            self.assertTrue(any("unittest" in item for item in context.validator_plan))
            self.assertTrue(any("release_guide.md" in item for item in context.validator_plan))
            self.assertIn("- keep heading `# release guide`", context.contract.exactness_rules)

    def test_normalizer_absorbs_task_md_when_project_root_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TASK.md").write_text(
                "Rewrite `docs/guide.md`.\n"
                "- keep heading `# guide`\n"
                "- include `next step` in `docs/guide.md`\n",
                encoding="utf-8",
            )
            contract = normalize_task_to_contract(
                "Read TASK.md.\nRewrite `docs/guide.md`.",
                project_root=root,
                required_artifacts=["docs/guide.md"],
            )
            self.assertIn("TASK.md", contract.metadata["contract_sources"])
            self.assertIn("- keep heading `# guide`", contract.exactness_rules)
            self.assertIn("docs/guide.md", contract.source_refs)

    def test_generic_filesystem_adapter_supports_non_python_generic_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "reports").mkdir()
            (root / "data" / "before.json").write_text('{"mode":"t0","handoff":0}\n', encoding="utf-8")
            contract = normalize_task_to_contract(
                "Compare `data/before.json` and write `reports/summary.json`.",
                project_root=root,
                required_artifacts=["reports/summary.json"],
                inputs=["data/before.json"],
                acceptance_contract=["reports/summary.json preserves handoff counts"],
            )
            context = build_project_context(
                root,
                contract,
                checkpoint={
                    "validator_results": ["ok:check acceptance rules against edited artifacts"],
                    "unresolved_items": ["reports/summary.json preserves handoff counts"],
                    "resume_delta": {
                        "pending_artifacts": ["reports/summary.json"],
                    },
                },
            )
            self.assertEqual(context.adapter_id, "generic-fs")
            self.assertIn("data/before.json", context.read_hints)
            self.assertNotIn("reports/summary.json", context.read_hints)
            self.assertTrue(any("structured content" in item or "acceptance rules" in item for item in context.validator_plan))
            self.assertTrue(any("data/before.json -> reports/summary.json" in item for item in context.validator_plan))
            self.assertFalse(any("reports/summary.json; reports/summary.json" in item for item in context.validator_plan))
            self.assertIn("reports/summary.json", context.resume_delta.pending_artifacts)
            self.assertTrue(context.resume_delta.pending_validations)
            self.assertNotIn(
                "check acceptance rules against edited artifacts",
                context.resume_delta.pending_validations,
            )

    def test_failed_validator_plans_stay_pending_until_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "sample.py").write_text("def sample():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            contract = normalize_task_to_contract(
                "Fix `src/sample.py`.",
                project_root=root,
                scope_in=["src/sample.py"],
                required_artifacts=["reports/checkpoint.md"],
            )
            failed_context = build_project_context(
                root,
                contract,
                checkpoint={
                    "validator_results": ["fail:run python -m unittest tests/test_sample.py"],
                },
            )
            ok_context = build_project_context(
                root,
                contract,
                checkpoint={
                    "validator_results": ["ok:run python -m unittest tests/test_sample.py"],
                },
            )
            self.assertTrue(failed_context.resume_delta.pending_validations)
            self.assertIn(
                "run python -m unittest tests/test_sample.py",
                failed_context.resume_delta.pending_validations,
            )
            self.assertNotIn(
                "run python -m unittest tests/test_sample.py",
                ok_context.resume_delta.pending_validations,
            )

    def test_adapters_do_not_reinject_checkpoint_unresolved_text_into_resume_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reports").mkdir()
            (root / "reports" / "summary.json").write_text('{"value": 1}\n', encoding="utf-8")
            contract = normalize_task_to_contract(
                "Write `reports/summary.json`.",
                project_root=root,
                required_artifacts=["reports/summary.json"],
                acceptance_contract=["reports/summary.json preserves compared values"],
            )
            context = build_project_context(
                root,
                contract,
                checkpoint={
                    "validator_results": [
                        "ok:verify artifacts exist: reports/summary.json",
                        "ok:inspect structured content requirements in reports/summary.json",
                        "ok:check acceptance rules against edited artifacts",
                    ],
                    "resume_delta": {
                        "carryover_items": ["preserve compared values"],
                    },
                    "unresolved_items": ["artifacts pending: reports/summary.json"],
                },
            )
            self.assertEqual(context.resume_delta.pending_artifacts, [])
            self.assertEqual(context.resume_delta.carryover_items, ["preserve compared values"])


if __name__ == "__main__":
    unittest.main()
