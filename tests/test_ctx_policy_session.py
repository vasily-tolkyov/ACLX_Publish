from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aclx.checkpoint_state import CheckpointState
from aclx.contract import TaskContract
from aclx.contract_normalizer import normalize_task_to_contract
from aclx.project_adapters import ResumeDelta, build_project_context
from ctx.policy import PolicySpec, DEFAULT_CONSTRAINTS, generate_policy_file
from ctx.snapshot import SnapshotStore
from ctx.session import (
    _build_unresolved_items,
    _checkpoint_request_mismatches,
    _collect_validator_results,
    _compact_literal_anchors,
    _compact_t3_doc_shape_hint,
    check_constraint,
    record_gate,
    run_codex_turn,
)


class PolicyAndSessionTests(unittest.TestCase):
    def test_policy_spec_blocks_unknown_action_for_known_target(self) -> None:
        spec = PolicySpec(list(DEFAULT_CONSTRAINTS))
        allowed, reason = spec.validate_action("mod=aclx/core.py", "write_ok")
        self.assertFalse(allowed)
        self.assertIn("allowed actions", reason)

    def test_run_codex_turn_defaults_to_t0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Wire ACL-X runtime by default.",
                tool_results=[{"type": "shell", "command": "pytest", "stdout": "ok", "returncode": 0}],
                project_root=root,
            )
            self.assertEqual(payload, "Wire ACL-X runtime by default.")
            self.assertFalse((root / ".aclx_runtime" / "checkpoints" / "integration.json").exists())
            self.assertFalse((root / ".aclx_runtime" / "policy_active.aclx").exists())

    def test_run_codex_turn_t3_creates_checkpoint_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Wire ACL-X runtime by default.",
                tool_results=[{"type": "shell", "command": "pytest", "stdout": "ok", "returncode": 0}],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
                acceptance_contract=["preserve generator critic refiner roles", "keep strict mode wording"],
                stop_conditions=["scope drift"],
                next_actions=["revise skill", "persist checkpoint"],
            )
            self.assertIn("Loop invariants:", payload)
            self.assertIn("Stop if: scope drift", payload)
            self.assertIn("Checkpoint:", payload)
            self.assertNotIn("Read: TASK.md", payload)
            self.assertNotIn("Do not open TASK.md", payload)
            self.assertIn("Literal wording:", payload)
            self.assertIn(
                "Task contract: task text is authoritative for named files and required wording.",
                payload,
            )
            self.assertIn(
                "Direct pass: use the contract, edit named targets and checkpoint files, then reply with changed paths and verification only.",
                payload,
            )
            self.assertIn("Loop guard: contract-complete T3.", payload)
            self.assertIn("Checkpoint rule:", payload)
            self.assertIn("do not reread or byte-compare it unless required", payload)
            self.assertTrue((root / ".aclx_runtime" / "checkpoints" / "integration.json").exists())
            self.assertTrue((root / ".aclx_runtime" / "policy_active.aclx").exists())
            checkpoint = json.loads((root / ".aclx_runtime" / "checkpoints" / "integration.json").read_text(encoding="utf-8"))
            self.assertEqual(
                checkpoint["required_artifacts"],
                ["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
            )
            self.assertEqual(
                checkpoint["acceptance_contract"],
                ["preserve generator critic refiner roles", "keep strict mode wording"],
            )
            self.assertEqual(checkpoint["stop_conditions"], ["scope drift"])
            self.assertEqual(checkpoint["next_actions"], ["revise skill", "persist checkpoint"])
            self.assertTrue(checkpoint["contract_hash"])
            self.assertEqual(checkpoint["adapter_id"], "generic-fs+docs")
            self.assertEqual(
                checkpoint["artifact_manifest"],
                ["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
            )
            self.assertEqual(
                checkpoint["resume_delta"]["pending_artifacts"],
                ["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
            )
            self.assertTrue(checkpoint["validator_plan"])
            self.assertEqual(checkpoint["contract"]["output_artifacts"], ["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"])

    def test_run_codex_turn_uses_runtime_bundle_for_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            runtime_bundle = "h|c|c0|1~f|$1|ac=E.ga;aa=A.up;ob=E.st;cx=resume.bundle~m|so=test;sc=resume;cy=.9~k|0d0fa71b"
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume from compact state.",
                tool_results=[],
                project_root=root,
                runtime_bundle=runtime_bundle,
                runtime_tier="t3",
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx"],
                acceptance_contract=["preserve generator critic refiner roles"],
                stop_conditions=["missing evidence"],
            )
            self.assertIn(runtime_bundle, payload)
            self.assertNotIn("[layer2]", payload)
            self.assertIn("Preserve: preserve generator critic refiner roles", payload)
            self.assertIn("Stop if: missing evidence", payload)
            self.assertIn("Artifacts: runtime/checkpoints/checkpoint_01.aclx", payload)
            self.assertNotIn("Read TASK.md", payload)
            self.assertFalse((root / ".aclx_runtime" / "checkpoints" / "resume.json").exists())
            self.assertFalse((root / ".aclx_runtime" / "policy_active.aclx").exists())

    def test_run_codex_turn_resume_reuses_checkpoint_bundle_when_missing_runtime_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            _ = run_codex_turn(
                active_phase="integration",
                task_description="Wire ACL-X runtime by default.",
                tool_results=[{"type": "shell", "command": "pytest", "stdout": "ok", "returncode": 0}],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx"],
                acceptance_contract=["preserve generator critic refiner roles"],
                stop_conditions=["scope drift"],
                next_actions=["persist checkpoint"],
            )
            checkpoint = json.loads((root / ".aclx_runtime" / "checkpoints" / "integration.json").read_text(encoding="utf-8"))
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume from checkpoint state.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertIn(checkpoint["runtime_bundle"], payload)
            self.assertIn("Preserve: preserve generator critic refiner roles", payload)
            self.assertIn("Stop if: scope drift", payload)
            self.assertIn("Artifacts: runtime/checkpoints/checkpoint_01.aclx", payload)
            self.assertFalse((root / ".aclx_runtime" / "checkpoints" / "resume.json").exists())

    def test_run_codex_turn_persists_and_reuses_validator_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            _ = run_codex_turn(
                active_phase="integration",
                task_description="Resume loop with checkpoint validation.",
                tool_results=[{"type": "shell", "command": "python -m unittest tests.test_loop -q", "stdout": "OK", "returncode": 0}],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
                acceptance_contract=["preserve generator critic refiner roles"],
                stop_conditions=["scope drift"],
                next_actions=["persist checkpoint"],
            )
            checkpoint = json.loads((root / ".aclx_runtime" / "checkpoints" / "integration.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["validator_results"], [])
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume loop with checkpoint validation.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertNotIn("Validated:", payload)

    def test_collect_validator_results_records_fail_without_marking_completion(self) -> None:
        self.assertEqual(
            _collect_validator_results(
                [
                    {
                        "type": "shell",
                        "command": "python -m unittest tests/test_sample.py",
                        "stdout": "FAILED",
                        "returncode": 1,
                    }
                ],
                ["run python -m unittest tests/test_sample.py"],
                None,
            ),
            [
                "fail:run python -m unittest tests/test_sample.py",
                "shell:python -m unittest tests/test_sample.py:rc=1",
            ],
        )

    def test_run_codex_turn_keeps_completed_validator_plans_out_of_resume_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "src" / "sample.py").write_text("def sample():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Fix `src/sample.py` and keep validation stable.",
                tool_results=[{"type": "shell", "command": "python -m unittest tests/test_sample.py", "stdout": "OK", "returncode": 0}],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["reports/checkpoint.md"],
                acceptance_contract=["reports/checkpoint.md records current state"],
                stop_conditions=["scope drift"],
                next_actions=["persist checkpoint"],
            )
            self.assertIn("Validate:", payload)
            self.assertIn("run tests: tests/test_sample.py", payload)
            self.assertNotIn("inspect: src/sample.py", payload)
            checkpoint = json.loads((root / ".aclx_runtime" / "checkpoints" / "integration.json").read_text(encoding="utf-8"))
            self.assertIn("ok:run python -m unittest tests/test_sample.py", checkpoint["validator_results"])
            self.assertNotIn("shell:python -m unittest tests/test_sample.py:rc=0", checkpoint["validator_results"])
            resume_payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume from checkpoint state.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertNotIn("Validated:", resume_payload)
            self.assertNotIn("Validate next: run python -m unittest tests/test_sample.py", resume_payload)
            self.assertNotIn("Validate: run python -m unittest tests/test_sample.py", resume_payload)

    def test_run_codex_turn_marks_file_based_validator_plans_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "reports").mkdir(parents=True)
            (root / "reports" / "summary.json").write_text('{"value": 1}\n', encoding="utf-8")
            _ = run_codex_turn(
                active_phase="integration",
                task_description="Write `reports/summary.json`.",
                tool_results=[{"path": "reports/summary.json", "content": '{"value": 1}\n'}],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["reports/summary.json"],
                acceptance_contract=["reports/summary.json preserves compared values"],
                next_actions=["persist checkpoint"],
            )
            checkpoint = json.loads((root / ".aclx_runtime" / "checkpoints" / "integration.json").read_text(encoding="utf-8"))
            self.assertIn(
                "ok:inspect structured content requirements in reports/summary.json",
                checkpoint["validator_results"],
            )
            self.assertNotIn("file:reports/summary.json", checkpoint["validator_results"])
            self.assertEqual(
                _collect_validator_results(
                    [{"path": "reports/summary.json", "content": '{"value": 1}\n'}],
                    ["inspect structured content requirements in reports/summary.json"],
                    None,
                ),
                [
                    "ok:inspect structured content requirements in reports/summary.json",
                    "file:reports/summary.json",
                ],
            )

    def test_run_codex_turn_resume_fallback_drops_stale_bundle_and_surfaces_adapter_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            checkpoint_root = root / ".aclx_runtime" / "checkpoints"
            checkpoint_root.mkdir(parents=True, exist_ok=True)
            stale_bundle = "h|c|c0|1~p|t.OLD~p|s.STALE~k|stale1234"
            (checkpoint_root / "integration.json").write_text(
                json.dumps(
                    {
                        "active_phase": "integration",
                        "task_description": "Rewrite `docs/guide.md`.",
                        "runtime_bundle": stale_bundle,
                        "required_artifacts": ["docs/guide.md"],
                        "acceptance_contract": ["keep heading `# guide`"],
                        "next_actions": ["rewrite document"],
                        "runtime_tier": "t3",
                        "adapter_id": "wrong-adapter",
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume from checkpoint state.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertNotIn(stale_bundle, payload)
            self.assertIn("Checkpoint mismatches: adapter_id", payload)

    def test_run_codex_turn_resume_surfaces_runtime_tier_mismatch_without_reusing_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            checkpoint_root = root / ".aclx_runtime" / "checkpoints"
            checkpoint_root.mkdir(parents=True, exist_ok=True)
            stale_bundle = "h|c|c0|1~p|t.T2~p|s.OLD~k|tierdead"
            (checkpoint_root / "integration.json").write_text(
                json.dumps(
                    {
                        "active_phase": "integration",
                        "task_description": "Write `runtime/shared_state.aclx`.",
                        "runtime_bundle": stale_bundle,
                        "required_artifacts": ["runtime/shared_state.aclx"],
                        "runtime_tier": "t2",
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume from checkpoint state.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertNotIn(stale_bundle, payload)
            self.assertIn("Checkpoint mismatches: runtime_tier", payload)

    def test_compact_literal_anchors_prioritize_behavior_over_role_names(self) -> None:
        self.assertEqual(
            _compact_literal_anchors(
                [
                    "- role_requester: one of requester",
                    "- role_approver: one of approver",
                    "- evidence_first: one of evidence before approval, evidence-first",
                    "- open_exceptions: one of open exceptions first, unresolved exceptions first",
                    "- bounded_scope: one of stay within the named spend scope, do not expand scope",
                ],
                keep=8,
            ),
            [
                "evidence before approval",
                "open exceptions first",
                "stay within the named spend scope",
            ],
        )

    def test_compact_literal_anchors_keep_single_role_anchor_when_no_behavior_exists(self) -> None:
        self.assertEqual(
            _compact_literal_anchors(
                [
                    "- role_drafter: one of drafter",
                    "- role_checker: one of checker",
                    "- role_approver: one of approver",
                ],
                keep=8,
            ),
            ["drafter"],
        )

    def test_compact_t3_doc_shape_hint_derives_minimal_validator_template(self) -> None:
        hint = _compact_t3_doc_shape_hint(
            [
                "- role_requester: one of requester",
                "- role_approver: one of approver",
                "- role_recorder: one of recorder",
                "- evidence_first: one of evidence before approval, evidence-first",
                "- open_exceptions: one of open exceptions first, unresolved exceptions first",
                "- bounded_scope: one of stay within the named spend scope, do not expand scope",
                "- no_silent_approval: one of no silent approval, approval is explicit",
                "- keep heading `# procurement exception playbook`",
                "- keep heading `## roles`",
                "- keep heading `## review loop`",
                "- keep heading `## guardrails`",
                "- include `current state` in `reports/procurement_exception_checkpoint.md`",
                "- include `open exceptions` in `reports/procurement_exception_checkpoint.md`",
                "- include `next pass` in `reports/procurement_exception_checkpoint.md`",
            ],
            required_artifacts=[
                "reports/procurement_exception_checkpoint.md",
                "docs/procurement_exception_playbook.md",
            ],
        )
        self.assertIn(
            "doc headings [# procurement exception playbook | ## roles | ## review loop | ## guardrails]",
            hint,
        )
        self.assertIn(
            "checkpoint headings [## current state | ## open exceptions | ## next pass]",
            hint,
        )
        self.assertIn("no extra sections/examples", hint)

    def test_compact_t3_doc_shape_hint_returns_empty_without_doc_outputs(self) -> None:
        self.assertEqual(
            _compact_t3_doc_shape_hint(
                ["- role_requester: one of requester"],
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx"],
            ),
            "",
        )

    def test_checkpoint_state_absorbs_legacy_remaining_delta_into_typed_resume_delta(self) -> None:
        checkpoint = CheckpointState.from_dict(
            {
                "remaining_delta": [
                    "missing_outputs=reports/summary.json",
                    "pending_tests=run python -m unittest tests/test_sample.py",
                    "review_targets=docs/guide.md",
                    "checkpoint_unresolved=keep heading `# guide`",
                ]
            }
        )
        self.assertEqual(checkpoint.resume_delta.pending_artifacts, ["reports/summary.json"])
        self.assertEqual(
            checkpoint.resume_delta.pending_validations,
            ["run python -m unittest tests/test_sample.py"],
        )
        self.assertEqual(checkpoint.resume_delta.read_targets, ["docs/guide.md"])
        self.assertEqual(checkpoint.resume_delta.carryover_items, ["keep heading `# guide`"])

    def test_build_unresolved_items_rebuilds_from_current_state_only(self) -> None:
        rebuilt = _build_unresolved_items(
            stop_conditions=[],
            resume_delta=ResumeDelta(),
            checkpoint_mismatches=[],
        )
        self.assertEqual(rebuilt, [])

    def test_resume_clears_resolved_pending_items_from_prompt_and_next_checkpoint_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            task_description = "Write `reports/summary.json`."
            required_artifacts = ["reports/summary.json"]
            acceptance_contract = ["reports/summary.json preserves compared values"]
            next_actions = ["persist checkpoint"]
            stop_conditions = ["scope drift"]
            _ = run_codex_turn(
                active_phase="integration",
                task_description=task_description,
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=required_artifacts,
                acceptance_contract=acceptance_contract,
                stop_conditions=stop_conditions,
                next_actions=next_actions,
            )
            checkpoint_path = root / ".aclx_runtime" / "checkpoints" / "integration.json"
            first_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertIn("artifacts pending: reports/summary.json", first_checkpoint["unresolved_items"])
            self.assertEqual(first_checkpoint["resume_delta"]["pending_artifacts"], ["reports/summary.json"])

            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "reports" / "summary.json").write_text('{"value": 1}\n', encoding="utf-8")
            contract = normalize_task_to_contract(
                task_description,
                project_root=root,
                required_artifacts=required_artifacts,
                acceptance_contract=acceptance_contract,
            )
            current_context = build_project_context(root, contract)
            stale_checkpoint = dict(first_checkpoint)
            stale_checkpoint["validator_results"] = [f"ok:{plan}" for plan in current_context.validator_plan]
            stale_checkpoint["unresolved_items"] = list(first_checkpoint["unresolved_items"])
            stale_checkpoint["resume_delta"] = dict(first_checkpoint["resume_delta"])
            checkpoint_path.write_text(
                json.dumps(stale_checkpoint, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            next_context = build_project_context(root, contract, checkpoint=stale_checkpoint)
            next_unresolved = _build_unresolved_items(
                stop_conditions=stop_conditions,
                resume_delta=next_context.resume_delta,
                checkpoint_mismatches=[],
            )
            self.assertEqual(next_context.resume_delta.pending_artifacts, [])
            self.assertEqual(next_context.resume_delta.pending_validations, [])
            self.assertNotIn("artifacts pending: reports/summary.json", next_unresolved)
            self.assertNotIn("validations pending:", "\n".join(next_unresolved))

            resume_payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume from checkpoint state.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertNotIn("Artifacts pending: reports/summary.json", resume_payload)
            self.assertNotIn("Validate next:", resume_payload)

    def test_checkpoint_request_mismatches_distinguish_reason_codes(self) -> None:
        contract = TaskContract(goal="Rewrite guide.", operation="rewrite")
        checkpoint = CheckpointState(
            active_phase="integration",
            task_description="Rewrite guide.",
            runtime_bundle="h|c|c0|1~k|deadbeef",
            runtime_tier="t2",
            contract=contract,
            contract_hash=contract.contract_hash(),
            adapter_id="generic-fs",
        )
        self.assertEqual(
            _checkpoint_request_mismatches(
                checkpoint,
                contract=contract,
                adapter_id="generic-fs",
                runtime_tier="t3",
            ),
            ["runtime_tier"],
        )
        self.assertEqual(
            _checkpoint_request_mismatches(
                checkpoint,
                contract=TaskContract(goal="Different.", operation="rewrite"),
                adapter_id="generic-fs",
                runtime_tier="t2",
            ),
            ["contract_hash"],
        )
        self.assertEqual(
            _checkpoint_request_mismatches(
                checkpoint,
                contract=contract,
                adapter_id="generic-fs+docs",
                runtime_tier="t2",
            ),
            ["adapter_id"],
        )

    def test_run_codex_turn_resume_detects_checkpoint_contract_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            _ = run_codex_turn(
                active_phase="integration",
                task_description="Write `runtime/checkpoints/checkpoint_01.aclx` and `target_skill/SKILL.md`.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
                acceptance_contract=["preserve generator critic refiner roles"],
                stop_conditions=["scope drift"],
                next_actions=["persist checkpoint"],
            )
            with self.assertRaises(RuntimeError) as context:
                run_codex_turn(
                    active_phase="resume",
                    task_description="Write `runtime/checkpoints/checkpoint_02.aclx`.",
                    tool_results=[],
                    project_root=root,
                    runtime_tier="t3",
                    required_artifacts=["runtime/checkpoints/checkpoint_02.aclx"],
                    acceptance_contract=["persist checkpoint only"],
                    stop_conditions=["scope drift"],
                )
            self.assertIn("Checkpoint contract mismatch", str(context.exception))

    def test_run_codex_turn_resume_reuses_legacy_checkpoint_bundle_when_hidden_paths_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "ctx").mkdir(parents=True)
            (root / "ctx" / "policy_active.aclx").write_text("allow: write_ok\n", encoding="utf-8")
            legacy_bundle = (
                "h|c|c0|1~e|$1|ac=E.ga;aa=A.up;ob=E.st;cx=legacy.resume~"
                "m|so=test;sc=resume;cy=.9~k|legacy123"
            )
            (root / "checkpoints").mkdir(parents=True)
            (root / "checkpoints" / "integration.json").write_text(
                json.dumps(
                    {
                        "active_phase": "integration",
                        "task_description": "Resume from legacy checkpoint state.",
                        "runtime_bundle": legacy_bundle,
                        "required_artifacts": ["runtime/checkpoints/checkpoint_01.aclx"],
                        "acceptance_contract": ["preserve generator critic refiner roles"],
                        "stop_conditions": ["scope drift"],
                        "next_actions": ["persist checkpoint"],
                        "runtime_tier": "t3",
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="resume",
                task_description="",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertIn(legacy_bundle, payload)
            self.assertIn("Preserve: preserve generator critic refiner roles", payload)
            self.assertIn("Artifacts: runtime/checkpoints/checkpoint_01.aclx", payload)
            self.assertIn("Resume from legacy checkpoint state.", payload)
            self.assertFalse((root / ".aclx_runtime" / "checkpoints" / "resume.json").exists())

    def test_run_codex_turn_t0_skips_header_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="One-shot summary task.",
                tool_results=[],
                project_root=root,
                runtime_tier="t0",
            )
            self.assertNotIn("Runtime ACL-X bundle follows.", payload)
            self.assertFalse((root / ".aclx_runtime" / "checkpoints" / "integration.json").exists())

    def test_run_codex_turn_t2_skips_checkpoint_when_not_looping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Reuse one compact machine-only bundle.",
                tool_results=[],
                project_root=root,
                runtime_tier="t2",
                required_artifacts=["runtime/shared_state.aclx", "reports/review_notes.md"],
                acceptance_contract=["review notes keep Risk and Evidence sections"],
                stop_conditions=["missing shared artifact"],
                next_actions=["write shared state", "run tests"],
            )
            self.assertIn("Machine contract:", payload)
            self.assertNotIn("Read: TASK.md", payload)
            self.assertIn("Must write: runtime/shared_state.aclx; reports/review_notes.md", payload)
            self.assertIn("Write requirements: review notes keep Risk and Evidence sections", payload)
            self.assertIn("Done when: required artifact files exist", payload)
            self.assertNotIn("Artifacts:", payload)
            self.assertIn("Artifact rule:", payload)
            self.assertIn(
                "Execute once: read named files, patch, create required artifacts from the named spec, run only Validate (`check files` = existence only), then reply with `Changed paths` and `Executed validator result` only. No progress messages or rereads of written artifacts.",
                payload,
            )
            self.assertIn(
                "Runtime guard: contract-complete T2. Use this contract directly; skip skill/runtime docs, directory probes, and progress chatter unless a required fact is missing.",
                payload,
            )
            self.assertIn(
                "Runtime ACL-X bundle follows.",
                payload,
            )
            self.assertTrue((root / ".aclx_runtime" / "policy_active.aclx").exists())
            self.assertFalse((root / ".aclx_runtime" / "checkpoints" / "integration.json").exists())

    def test_run_codex_turn_t2_read_first_keeps_file_hints_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "src" / "sample.py").write_text("def sample():\n    return 1\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Fix `src/sample.py` so `python -m unittest discover -s tests -q` passes.",
                tool_results=[],
                project_root=root,
                runtime_tier="t2",
                required_artifacts=["runtime/shared_state.aclx", "reports/review_notes.md"],
                acceptance_contract=["review notes keep Risk and Evidence sections"],
                stop_conditions=["missing shared artifact"],
                next_actions=["write shared state", "run tests"],
            )
            self.assertIn("Read first: tests/test_sample.py; src/sample.py", payload)
            self.assertIn(
                "Validate: run tests: tests/test_sample.py; check files: runtime/shared_state.aclx; reports/review_notes.md",
                payload,
            )
            self.assertIn("Write requirements: review notes keep Risk and Evidence sections", payload)
            self.assertIn("Done when: required artifact files exist", payload)
            self.assertIn(
                "Execute once: read named files, patch, create required artifacts from the named spec, run only Validate (`check files` = existence only), then reply with `Changed paths` and `Executed validator result` only. No progress messages or rereads of written artifacts.",
                payload,
            )
            self.assertNotIn("check acceptance", payload)
            self.assertNotIn(str(root), payload)
            self.assertNotIn("Read first: src;", payload)
            self.assertNotIn("Read first: tests;", payload)

    def test_run_codex_turn_t2_prefers_check_files_over_docs_wording_when_tests_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "src" / "sample.py").write_text(
                "def sample(values: list[str]) -> list[str]:\n    return values[1:]\n",
                encoding="utf-8",
            )
            (root / "tests" / "test_sample.py").write_text(
                "import unittest\n\n"
                "from src.sample import sample\n\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_keeps_first_value(self) -> None:\n"
                "        self.assertEqual(sample(['a', 'b']), ['a', 'b'])\n",
                encoding="utf-8",
            )
            (root / "TASK.md").write_text(
                "Fix `src/sample.py`.\n"
                "- write `reports/repair_notes.md`\n"
                "- keep headings `Risk` and `Evidence` in `reports/repair_notes.md`\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Read TASK.md. Fix `src/sample.py` so `python -m unittest discover -s tests -q` passes.",
                tool_results=[],
                project_root=root,
                runtime_tier="t2",
                required_artifacts=["artifacts/shared_state.json", "reports/repair_notes.md"],
                acceptance_contract=[
                    "python -m unittest discover -s tests -q passes",
                    "artifacts/shared_state.json keeps the required handoff keys",
                    "reports/repair_notes.md keeps Risk and Evidence headings",
                ],
                stop_conditions=["missing shared artifact"],
                next_actions=["write shared state", "run tests"],
            )
            self.assertIn("Read first: TASK.md; tests/test_sample.py", payload)
            self.assertIn(
                "Validate: run tests: python -m unittest discover -s tests -q; check files: artifacts/shared_state.json; reports/repair_notes.md",
                payload,
            )
            self.assertIn(
                "Artifact spec: reports/repair_notes.md -> headings Risk, Evidence",
                payload,
            )
            self.assertIn(
                "Write requirements: artifacts/shared_state.json keeps the required handoff keys",
                payload,
            )
            self.assertIn(
                "Done when: python -m unittest discover -s tests -q passes; required artifact files exist",
                payload,
            )
            self.assertIn(
                "Execute once: read named files, patch, create required artifacts from the named spec, run only Validate (`check files` = existence only), then reply with `Changed paths` and `Executed validator result` only. No progress messages or rereads of written artifacts.",
                payload,
            )
            self.assertNotIn("check wording: reports/repair_notes.md", payload)
            self.assertNotIn("inspect docs: reports/repair_notes.md", payload)

    def test_run_codex_turn_t2_renders_concrete_artifact_specs_from_exactness_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "src" / "sample.py").write_text("def sample(values: list[str]) -> list[str]:\n    return values\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            payload = run_codex_turn(
                active_phase="integration",
                task_description=(
                    "Fix `src/sample.py` so `python -m unittest discover -s tests -q` passes.\n"
                    "- `artifacts/shared_state.json` must include keys: status, owner, validated_tests.\n"
                    "- Write `reports/repair_notes.md` with headings `Risk` and `Evidence`.\n"
                ),
                tool_results=[],
                project_root=root,
                runtime_tier="t2",
                required_artifacts=["artifacts/shared_state.json", "reports/repair_notes.md"],
                acceptance_contract=[
                    "python -m unittest discover -s tests -q passes",
                    "artifacts/shared_state.json keeps the required handoff keys",
                    "reports/repair_notes.md keeps Risk and Evidence headings",
                ],
                stop_conditions=["missing shared artifact"],
                next_actions=["write shared state", "run tests"],
            )
            self.assertIn(
                "Artifact spec: artifacts/shared_state.json -> keys status, owner, validated_tests; reports/repair_notes.md -> headings Risk, Evidence",
                payload,
            )
            self.assertNotIn(
                "Write requirements: artifacts/shared_state.json keeps the required handoff keys; reports/repair_notes.md keeps Risk and Evidence headings",
                payload,
            )
            self.assertIn(
                "Done when: python -m unittest discover -s tests -q passes; required artifact files exist",
                payload,
            )

    def test_run_codex_turn_t2_compacts_aclx_shared_state_requirement_into_artifact_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "TASK.md").write_text("Fix `src/sample.py`.\n", encoding="utf-8")
            (root / "src" / "sample.py").write_text("def sample(values: list[str]) -> list[str]:\n    return values[1:]\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text(
                "import unittest\n\n"
                "from src.sample import sample\n\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_keeps_first_value(self) -> None:\n"
                "        self.assertEqual(sample(['a', 'b']), ['a', 'b'])\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Read TASK.md. Fix `src/sample.py` so `python -m unittest discover -s tests -q` passes.",
                tool_results=[],
                project_root=root,
                runtime_tier="t2",
                required_artifacts=["runtime/shared_state.aclx", "reports/review_notes.md"],
                acceptance_contract=[
                    "python -m unittest discover -s tests -q passes",
                    "runtime/shared_state.aclx uses ACL-X C-layer text",
                    "reports/review_notes.md keeps Risk and Evidence headings",
                ],
                stop_conditions=["missing shared artifact"],
                next_actions=["write shared state", "run tests"],
            )
            self.assertIn(
                "Artifact spec: runtime/shared_state.aclx -> exact ACL-X bundle line; reports/review_notes.md -> headings Risk, Evidence",
                payload,
            )
            self.assertNotIn("Write requirements: runtime/shared_state.aclx uses ACL-X C-layer text", payload)
            self.assertIn(
                "Artifact rule: create parent dirs if needed, then copy the final ACL-X bundle line exactly into runtime/shared_state.aclx as one raw line unless the task explicitly requires a different state line; do not add quotes or escapes, and do not reread it unless required.",
                payload,
            )

    def test_build_project_context_t2_python_repair_drops_abstract_acceptance_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "src" / "sample.py").write_text("def sample(values: list[str]) -> list[str]:\n    return values\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            contract = normalize_task_to_contract(
                "Fix `src/sample.py` so `python -m unittest discover -s tests -q` passes.",
                project_root=root,
                required_artifacts=["artifacts/shared_state.json", "reports/repair_notes.md"],
                acceptance_contract=[
                    "python -m unittest discover -s tests -q passes",
                    "artifacts/shared_state.json keeps the required handoff keys",
                    "reports/repair_notes.md keeps Risk and Evidence headings",
                ],
                scope_in=["src/sample.py"],
                shared_state=True,
                expected_handoffs=2,
                expected_rounds=2,
                child_agents=2,
            )
            context = build_project_context(root, contract)
            self.assertIn("run python -m unittest tests/test_sample.py", context.validator_plan)
            self.assertIn(
                "verify artifacts exist: artifacts/shared_state.json; reports/repair_notes.md",
                context.validator_plan,
            )
            self.assertFalse(any("acceptance rules" in item for item in context.validator_plan))
            self.assertFalse(any(item.startswith("check docs wording:") for item in context.validator_plan))
            self.assertFalse(any(item.startswith("inspect docs outputs:") for item in context.validator_plan))

    def test_run_codex_turn_t2_review_keeps_task_md_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            (root / "src").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "src" / "sample.py").write_text("def sample(values: list[str]) -> list[str]:\n    return values\n", encoding="utf-8")
            (root / "tests" / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
            (root / "TASK.md").write_text("Review `src/sample.py` against `tests/test_sample.py`.\n", encoding="utf-8")
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Read TASK.md. Review `src/sample.py` against `tests/test_sample.py` and write `reports/review_notes.md`.",
                tool_results=[],
                project_root=root,
                runtime_tier="t2",
                required_artifacts=["runtime/shared_state.aclx", "reports/review_notes.md"],
                acceptance_contract=["review notes keep Risk and Evidence sections"],
                stop_conditions=["missing shared artifact"],
                next_actions=["write shared state", "run tests"],
            )
            self.assertIn("Read first: TASK.md; tests/test_sample.py", payload)
            self.assertNotIn("Read first: tests/test_sample.py; src/sample.py", payload)

    def test_run_codex_turn_t3_preserves_task_md_contract_when_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description=(
                    "Read target_skill/TASK.md first.\n"
                    "Preserve the roles line exactly as generator, critic, refiner.\n"
                    "Write target_skill/SKILL.md and runtime/checkpoints/checkpoint_01.aclx."
                ),
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
                acceptance_contract=["preserve generator critic refiner roles", "keep strict mode wording"],
                stop_conditions=["scope drift"],
                next_actions=["revise skill", "persist checkpoint"],
                contract=TaskContract(
                    goal="Revise target skill from TASK.md.",
                    operation="rewrite",
                    output_artifacts=["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
                    exactness_rules=["Preserve the roles line exactly as generator, critic, refiner."],
                    acceptance_rules=["preserve generator critic refiner roles", "keep strict mode wording"],
                    stop_conditions=["scope drift"],
                    next_actions=["revise skill", "persist checkpoint"],
                    metadata={"contract_sources": ["target_skill/TASK.md"]},
                ),
            )
            self.assertIn("Read target_skill/TASK.md first.", payload)
            self.assertIn(
                "Task contract: `TASK.md` is authoritative; read it once and keep explicit wording literal.",
                payload,
            )
            self.assertIn("Stop if: scope drift", payload)
            self.assertIn(
                "Direct pass: read TASK.md once, edit named targets, then reply with changed paths and verification only.",
                payload,
            )
            self.assertIn(
                "Validate: check wording: target_skill/SKILL.md; inspect docs: target_skill/SKILL.md",
                payload,
            )
            self.assertNotIn("check acceptance", payload)
            self.assertIn("Loop guard: contract-complete T3.", payload)
            self.assertIn("Read target_skill/TASK.md first.", payload)
            self.assertNotIn("Do not open TASK.md", payload)

    def test_run_codex_turn_t3_compacts_generic_doc_loop_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Rewrite `docs/release_signoff_handbook.md` so it satisfies the required loop constraints.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                acceptance_contract=[
                    "loop document keeps the required wording and headings",
                    "checkpoint note records current state and next step",
                ],
                stop_conditions=["scope drift", "missing checkpoint note"],
                next_actions=["rewrite document", "persist checkpoint note"],
                contract=TaskContract(
                    goal="Rewrite release signoff handbook from TASK.md.",
                    operation="rewrite",
                    output_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                    exactness_rules=[
                        "- role_drafter: one of drafter",
                        "- role_checker: one of checker",
                        "- include `current checkpoint` in `reports/signoff_checkpoint.md`",
                    ],
                    acceptance_rules=[
                        "loop document keeps the required wording and headings",
                        "checkpoint note records current state and next step",
                    ],
                    stop_conditions=["scope drift", "missing checkpoint note"],
                    next_actions=["rewrite document", "persist checkpoint note"],
                    metadata={"contract_sources": ["TASK.md"]},
                ),
            )
            self.assertIn(
                "Task contract: `TASK.md` is authoritative; read it once and keep explicit wording literal.",
                payload,
            )
            self.assertIn("Read first: TASK.md; docs/release_signoff_handbook.md", payload)
            self.assertNotIn("Template:", payload)
            self.assertIn("Literal anchors (exact casing):", payload)
            self.assertIn(
                "Literal anchors (exact casing): drafter",
                payload,
            )
            self.assertIn(
                "Validate: check wording: docs/release_signoff_handbook.md; inspect docs: reports/signoff_checkpoint.md",
                payload,
            )
            self.assertNotIn("Validate: check wording; inspect docs", payload)
            self.assertIn("Shape:", payload)
            self.assertIn("no extra sections/examples", payload)
            self.assertIn(
                "Rules: if a checkpoint target is missing, create it; keep one listed TASK.md phrase verbatim with matching casing for each anchor; keep the smallest valid text only; use Validate only on named targets with direct pattern checks (`rg -n` or `Select-String`); no plan updates, no progress chatter, and no post-edit rereads.",
                payload,
            )
            self.assertIn(
                "Final reply: `Changed paths` and `Verification` only.",
                payload,
            )
            self.assertNotIn("Operate once: use only Source, Targets, and Validate above;", payload)
            self.assertNotIn("plain relative paths only", payload)
            self.assertIn("Loop guard: compact T3 doc loop. Use the named contract only.", payload)

    def test_run_codex_turn_t3_uses_compiled_contract_when_doc_loop_contract_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            (root / "docs" / "release_signoff_handbook.md").write_text(
                "# draft\n",
                encoding="utf-8",
            )
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Rewrite `docs/release_signoff_handbook.md` so it satisfies the required loop constraints.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                acceptance_contract=[
                    "loop document keeps the required wording and headings",
                    "checkpoint note records current state and next step",
                ],
                stop_conditions=["scope drift", "missing checkpoint note"],
                next_actions=["rewrite document", "persist checkpoint note"],
                contract=TaskContract(
                    goal="Rewrite release signoff handbook from TASK.md.",
                    operation="rewrite",
                    output_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                    exactness_rules=[
                        "- role_drafter: one of drafter",
                        "- role_checker: one of checker",
                        "- role_approver: one of approver",
                        "- keep heading `# release signoff handbook`",
                        "- keep heading `## roles`",
                        "- include `current checkpoint` in `reports/signoff_checkpoint.md`",
                        "- include `blockers` in `reports/signoff_checkpoint.md`",
                        "- include `next step` in `reports/signoff_checkpoint.md`",
                    ],
                    acceptance_rules=[
                        "loop document keeps the required wording and headings",
                        "checkpoint note records current state and next step",
                    ],
                    stop_conditions=["scope drift", "missing checkpoint note"],
                    next_actions=["rewrite document", "persist checkpoint note"],
                    metadata={"contract_sources": ["TASK.md"]},
                ),
            )
            self.assertIn("Compiled contract is authoritative", payload)
            self.assertIn("reopen TASK.md only if blocked or Validate fails", payload)
            self.assertIn("Source: docs/release_signoff_handbook.md", payload)
            self.assertNotIn("Source: reports/signoff_checkpoint.md", payload)
            self.assertNotIn("Read first: TASK.md", payload)
            self.assertIn(
                "Targets: update docs/release_signoff_handbook.md; create reports/signoff_checkpoint.md",
                payload,
            )
            self.assertIn("Roles: drafter; checker; approver", payload)
            self.assertIn("Literal anchors (exact casing): drafter", payload)
            self.assertIn("Shape: doc headings [# release signoff handbook | ## roles]", payload)
            self.assertIn("checkpoint headings [## current checkpoint | ## blockers | ## next step]", payload)
            self.assertIn("Operate once: use Source, Targets, and Validate only;", payload)
            self.assertIn("reply once, stop", payload)
            self.assertIn("do not read pending create targets first", payload)
            self.assertIn("create missing checkpoint targets directly", payload)
            self.assertIn("carrier-only machine state", payload)
            self.assertIn("directory/checkpoint probes", payload)
            self.assertIn("Keep listed headings exact", payload)
            self.assertIn("Include each listed literal anchor exactly as written with matching casing at least once", payload)
            self.assertIn("do not inflect, paraphrase, or synonym-swap literal anchors", payload)
            self.assertIn("keep the smallest valid text only", payload)
            self.assertIn("Validate with direct pattern checks (`rg -n` or `Select-String`) only.", payload)
            self.assertIn("No plan chatter", payload)
            self.assertIn("post-edit rereads", payload)
            self.assertNotIn(
                "Seal: the ACL-X bundle below is carrier-only. No skill docs, AGENTS, runtime docs/files, hidden runtime state, router calls, unnamed paths, directory probes, or checkpoint existence probes. Do not reread TASK.md or edited targets unless a required fact is missing or Validate fails. No plan updates.",
                payload,
            )
            self.assertIn("Final reply: `Changed paths` and `Verification` only;", payload)
            self.assertIn("relative paths, one short line per check, no extra prose", payload)
            self.assertIn("Loop guard: sealed compiled T3 doc loop; use named surfaces only.", payload)

    def test_run_codex_turn_t3_compiled_doc_create_only_omits_missing_source_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="integration",
                task_description="Rewrite `docs/release_signoff_handbook.md` so it satisfies the required loop constraints.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                acceptance_contract=[
                    "loop document keeps the required wording and headings",
                    "checkpoint note records current state and next step",
                ],
                stop_conditions=["scope drift", "missing checkpoint note"],
                next_actions=["rewrite document", "persist checkpoint note"],
                contract=TaskContract(
                    goal="Rewrite release signoff handbook from TASK.md.",
                    operation="rewrite",
                    output_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                    exactness_rules=[
                        "- role_drafter: one of drafter",
                        "- role_checker: one of checker",
                        "- role_approver: one of approver",
                        "- keep heading `# release signoff handbook`",
                        "- keep heading `## roles`",
                        "- include `current checkpoint` in `reports/signoff_checkpoint.md`",
                        "- include `blockers` in `reports/signoff_checkpoint.md`",
                        "- include `next step` in `reports/signoff_checkpoint.md`",
                    ],
                    acceptance_rules=[
                        "loop document keeps the required wording and headings",
                        "checkpoint note records current state and next step",
                    ],
                    stop_conditions=["scope drift", "missing checkpoint note"],
                    next_actions=["rewrite document", "persist checkpoint note"],
                    metadata={"contract_sources": ["TASK.md"]},
                ),
            )
            self.assertNotIn("Source: docs/release_signoff_handbook.md", payload)
            self.assertIn(
                "Targets: create docs/release_signoff_handbook.md; create reports/signoff_checkpoint.md",
                payload,
            )
            self.assertIn("Compiled contract is authoritative", payload)
            self.assertIn("reopen TASK.md only if blocked or Validate fails", payload)
            self.assertIn("Operate once: use Source, Targets, and Validate only;", payload)
            self.assertIn("do not read pending create targets first", payload)
            self.assertIn("create missing checkpoint targets directly", payload)
            self.assertIn("Include each listed literal anchor exactly as written with matching casing at least once", payload)
            self.assertIn("do not inflect, paraphrase, or synonym-swap literal anchors", payload)
            self.assertIn("keep the smallest valid text only", payload)
            self.assertIn("No plan chatter", payload)
            self.assertIn("post-edit rereads", payload)
            self.assertIn("relative paths, one short line per check, no extra prose", payload)

    def test_run_codex_turn_t3_compiled_doc_resume_omits_task_checkpoint_and_pending_prereads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n"
                "tiers:\n"
                "  t3:\n"
                "    read_hint_keep: 3\n",
                encoding="utf-8",
            )
            _ = run_codex_turn(
                active_phase="integration",
                task_description="Rewrite `docs/release_signoff_handbook.md` so it satisfies the required loop constraints.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
                required_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                acceptance_contract=[
                    "loop document keeps the required wording and headings",
                    "checkpoint note records current state and next step",
                ],
                stop_conditions=["scope drift", "missing checkpoint note"],
                next_actions=["rewrite document", "persist checkpoint note"],
                contract=TaskContract(
                    goal="Rewrite release signoff handbook from TASK.md.",
                    operation="rewrite",
                    output_artifacts=["reports/signoff_checkpoint.md", "docs/release_signoff_handbook.md"],
                    exactness_rules=[
                        "- role_drafter: one of drafter",
                        "- role_checker: one of checker",
                        "- role_approver: one of approver",
                        "- keep heading `# release signoff handbook`",
                        "- keep heading `## roles`",
                        "- include `current checkpoint` in `reports/signoff_checkpoint.md`",
                        "- include `blockers` in `reports/signoff_checkpoint.md`",
                        "- include `next step` in `reports/signoff_checkpoint.md`",
                    ],
                    acceptance_rules=[
                        "loop document keeps the required wording and headings",
                        "checkpoint note records current state and next step",
                    ],
                    stop_conditions=["scope drift", "missing checkpoint note"],
                    next_actions=["rewrite document", "persist checkpoint note"],
                    metadata={"contract_sources": ["TASK.md"]},
                ),
            )
            checkpoint_path = root / ".aclx_runtime" / "checkpoints" / "integration.json"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "reports" / "signoff_checkpoint.md").write_text(
                "## current checkpoint\n",
                encoding="utf-8",
            )
            checkpoint["resume_delta"] = {
                "pending_artifacts": ["docs/release_signoff_handbook.md"],
                "pending_validations": [],
                "read_targets": [
                    "TASK.md",
                    "docs/release_signoff_handbook.md",
                    "reports/signoff_checkpoint.md",
                ],
                "carryover_items": [],
            }
            checkpoint_path.write_text(
                json.dumps(checkpoint, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume task.",
                tool_results=[],
                project_root=root,
                runtime_tier="t3",
            )
            self.assertNotIn("Read before resume:", payload)
            self.assertIn("Artifacts pending: docs/release_signoff_handbook.md", payload)
            self.assertIn("Resume once: use the named resume state and Validate only;", payload)
            self.assertNotIn("use only Source, Targets, and Validate above", payload)
            self.assertIn("reply once, stop", payload)
            self.assertIn("carrier-only machine state", payload)
            self.assertIn("directory/checkpoint probes", payload)
            self.assertIn("Include each listed literal anchor exactly as written with matching casing at least once", payload)
            self.assertIn("do not inflect, paraphrase, or synonym-swap literal anchors", payload)
            self.assertIn("keep the smallest valid text only", payload)
            self.assertIn("Validate with direct pattern checks (`rg -n` or `Select-String`) only.", payload)
            self.assertIn("No plan chatter", payload)
            self.assertIn("post-edit rereads", payload)
            self.assertIn("Final reply: `Changed paths` and `Verification` only;", payload)
            self.assertIn("relative paths, one short line per check, no extra prose", payload)
            self.assertNotIn(
                "Seal: the ACL-X bundle below is carrier-only. No skill docs, AGENTS, runtime docs/files, hidden runtime state, router calls, unnamed paths, directory probes, or checkpoint existence probes. Do not reread TASK.md or edited targets unless a required fact is missing or Validate fails. No plan updates.",
                payload,
            )
    def test_run_codex_turn_t1_passthroughs_runtime_bundle_without_extra_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir(parents=True)
            (root / "configs" / "ctx.yaml").write_text(
                "hard_token_limit: 1200\n"
                "snapshot_dir: .aclx_runtime/snapshots\n"
                "checkpoint_dir: .aclx_runtime/checkpoints\n"
                "policy_file: .aclx_runtime/policy_active.aclx\n",
                encoding="utf-8",
            )
            runtime_bundle = "h|c|c0|1~p|t.T1~p|s.S1~k|abcdef12"
            payload = run_codex_turn(
                active_phase="resume",
                task_description="Resume task.",
                tool_results=[{"type": "shell", "command": "pytest", "stdout": "ok", "returncode": 0}],
                project_root=root,
                runtime_bundle=runtime_bundle,
                runtime_tier="t1",
            )
            self.assertEqual(payload, runtime_bundle)
            self.assertFalse((root / ".aclx_runtime" / "policy_active.aclx").exists())

    def test_snapshot_archive_limit_keeps_recent_frames_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SnapshotStore(root, "snapshots")
            store.write("phase1", 1, True, {"n": 1}, "phase2")
            store.write("phase2", 2, True, {"n": 2}, "phase3")
            store.write("phase3", 3, True, {"n": 3}, "phase4")
            archive = store.load_all_as_archive(limit=2)
            self.assertIn("phase_idx=2", archive)
            self.assertIn("phase_idx=3", archive)
            self.assertNotIn("phase_idx=1", archive)

    def test_record_gate_and_check_constraint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = record_gate("integration", 1, True, {"token_reduction": 0.42}, "evaluation", project_root=root)
            self.assertTrue(path.exists())
            self.assertTrue(check_constraint("mod=ctx/runtime.py", "write_ok", project_root=root))
            self.assertFalse(check_constraint("mod=aclx/runtime_bridge.py", "write_ok", project_root=root))
            generate_policy_file(root)


if __name__ == "__main__":
    unittest.main()

