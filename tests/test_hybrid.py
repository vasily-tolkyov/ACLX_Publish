from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aclx.hybrid import (
    ACLXHybridPromptBuilder,
    HybridTaskSpec,
    classify_hybrid_route,
    infer_hybrid_profile,
    infer_hybrid_task_shape,
    infer_hybrid_tier,
    load_hybrid_router_map,
    reset_hybrid_router_map_cache,
)
from aclx.contract import RuntimeNeeds, TaskContract
from aclx.contract_normalizer import normalize_task_to_contract
from aclx.metrics import model_token_count
from aclx.supervisor import ACLXSupervisor

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_STR = str(REPO_ROOT)
SUPERVISOR_PATH = str(REPO_ROOT / "src" / "aclx" / "supervisor.py")
HYBRID_PATH = str(REPO_ROOT / "src" / "aclx" / "hybrid.py")
RUNTIME_SHARED_STATE = str(REPO_ROOT / "runtime" / "shared_state.aclx")
RUNTIME_SHARED_STATE_POSIX = RUNTIME_SHARED_STATE.replace("\\", "/")


class HybridPromptTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_hybrid_router_map_cache()

    def test_profile_inference_prefers_benchmark_keywords(self) -> None:
        self.assertEqual(infer_hybrid_profile("Benchmark token latency for child agents."), "benchmark")

    def test_hybrid_prompt_is_compact(self) -> None:
        builder = ACLXHybridPromptBuilder()
        payload = builder.build_prompt(
            HybridTaskSpec(
                task="Review the ACL-X supervisor for prompt waste and timeout risk.",
                profile="review",
                lane="prompt-review",
                cwd=REPO_ROOT_STR,
                scope_in=[SUPERVISOR_PATH],
                scope_out=["no edits"],
                stop_conditions=["missing evidence"],
            )
        )
        self.assertEqual(payload.prompt, "Review the ACL-X supervisor for prompt waste and timeout risk.")
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.aclx_bundle, "")

    def test_hybrid_prompt_embeds_bundle_for_real_handoff(self) -> None:
        builder = ACLXHybridPromptBuilder()
        payload = builder.build_prompt(
            HybridTaskSpec(
                task="Create a compact ACL-X handoff.",
                profile="implement",
                lane="handoff",
                tier="t1",
                current_state=["mode=handoff"],
                next_actions=["pass the bundle"],
                shared_state=True,
                real_handoff_started=True,
            )
        )
        self.assertIn("h|c|c0|1", payload.aclx_bundle)
        self.assertIn(payload.aclx_bundle, payload.prompt)
        self.assertNotIn("ACL-X bundle follows.", payload.prompt)
        self.assertNotIn("ACL-X bundle:", payload.prompt)
        self.assertNotIn("cwd=", payload.aclx_bundle)
        self.assertIn("nx=pass_the_bundle", payload.aclx_bundle)
        self.assertNotIn("d=", payload.aclx_bundle)
        self.assertNotIn("so=aclx.hybrid", payload.aclx_bundle)

    def test_hybrid_prompt_shorter_than_full_supervisor(self) -> None:
        supervisor = ACLXSupervisor()
        full_payload = supervisor.build_payload(
            "Review the ACL-X supervisor for prompt waste and timeout risk.",
            cwd=REPO_ROOT_STR,
            style="full",
            profile="review",
        )
        hybrid_payload = supervisor.build_payload(
            "Review the ACL-X supervisor for prompt waste and timeout risk.",
            cwd=REPO_ROOT_STR,
            style="adaptive",
            profile="review",
        )
        self.assertLess(model_token_count(hybrid_payload.codex_prompt), model_token_count(full_payload.codex_prompt))
        self.assertEqual(hybrid_payload.tier, "t0")

    def test_tier_inference_prefers_nl_lean_for_single_surface_tasks(self) -> None:
        self.assertEqual(infer_hybrid_tier("Port one legacy skill into Codex without looped handoffs.", profile="implement"), "t0")

    def test_route_classifier_keeps_meta_acl_x_work_in_t0(self) -> None:
        route = classify_hybrid_route(
            "Port the OpenClaw verification-triad-router skill into Codex with default hybrid semantics.",
            profile="implement",
        )
        self.assertEqual(route.task_shape, "single_surface")
        self.assertEqual(route.tier, "t0")
        self.assertIn("meta-only", route.signals)

    def test_tier_inference_uses_runtime_task_shape_before_text(self) -> None:
        self.assertEqual(
            infer_hybrid_tier(
                "Discuss handoffs and ACL-X tradeoffs without actually delegating.",
                profile="review",
                task_shape="single_surface",
            ),
            "t0",
        )

    def test_task_shape_inference_uses_hard_runtime_thresholds(self) -> None:
        self.assertEqual(
            infer_hybrid_task_shape(
                "Coordinate shared machine state across phases.",
                profile="implement",
                expected_handoffs=2,
                child_agents=2,
            ),
            "multi_step",
        )

    def test_route_classifier_detects_runtime_loop_from_text(self) -> None:
        route = classify_hybrid_route(
            "Run the verification loop, checkpoint and resume until the review is clean.",
            profile="review",
        )
        self.assertEqual(route.task_shape, "loop")
        self.assertEqual(route.tier, "t3")
        self.assertIn("text-loop", route.signals)

    def test_route_classifier_detects_runtime_single_handoff_from_text(self) -> None:
        route = classify_hybrid_route(
            "Delegate once to one reviewer pass and return the merged result.",
            profile="review",
        )
        self.assertEqual(route.task_shape, "delegated_once")
        self.assertEqual(route.tier, "t1")
        self.assertIn("text-single-handoff", route.signals)

    def test_tier_inference_promotes_loop_heavy_verification_work(self) -> None:
        self.assertEqual(
            infer_hybrid_tier("Run a verification loop with repeated resume handles until clean.", profile="review"),
            "t3",
        )

    def test_shared_state_routes_to_t2_session_mode(self) -> None:
        route = classify_hybrid_route(
            "Carry reusable machine state across the next phase.",
            profile="implement",
            shared_state=True,
            expected_handoffs=1,
        )
        self.assertEqual(route.tier, "t2")
        self.assertEqual(route.bridge_mode, "session")

    def test_single_output_tasks_do_not_imply_shared_state(self) -> None:
        contract = normalize_task_to_contract(
            "Write reports/summary.md.",
            required_artifacts=["reports/summary.md"],
        )
        self.assertFalse(contract.runtime_needs.shared_state)
        self.assertEqual(infer_hybrid_tier("Write reports/summary.md.", contract=contract, profile="implement"), "t0")

    def test_compare_and_write_task_stays_out_of_t2_without_runtime_state(self) -> None:
        contract = normalize_task_to_contract(
            "Compare a.json and b.json, then write reports/out.json.",
            required_artifacts=["reports/out.json"],
            inputs=["a.json", "b.json"],
        )
        self.assertFalse(contract.runtime_needs.shared_state)
        self.assertEqual(
            infer_hybrid_tier(
                "Compare a.json and b.json, then write reports/out.json.",
                contract=contract,
                profile="research",
            ),
            "t0",
        )

    def test_route_classification_does_not_mutate_contract(self) -> None:
        contract = TaskContract(
            goal="Review one file.",
            operation="review",
            runtime_needs=RuntimeNeeds(),
        )
        before = contract.contract_hash()
        route = classify_hybrid_route(
            "Delegate once to one reviewer pass and return the merged result.",
            contract=contract,
            expected_handoffs=1,
            child_agents=1,
        )
        self.assertEqual(route.tier, "t1")
        self.assertEqual(contract.contract_hash(), before)
        self.assertEqual(contract.runtime_needs.expected_handoffs, 0)
        self.assertFalse(contract.runtime_needs.shared_state)

    def test_resume_prompt_is_shorter_than_initial_prompt(self) -> None:
        builder = ACLXHybridPromptBuilder()
        resume = builder.build_resume_prompt(
            task_code="T1",
            profile="review",
            lane="prompt-review",
            round_label="r2",
            snapshot_code="S1",
            issue_codes=["F1"],
            next_actions=["apply reviewed finding", "return concise task result"],
            delta_items=["F1 verify duplication evidence"],
            required_artifacts=["runtime/checkpoints/checkpoint_01.aclx"],
            acceptance_contract=["preserve the verified task contract"],
            stop_conditions=["missing evidence"],
        )
        self.assertTrue(resume.prompt.startswith("Revise T1 S1.") or resume.prompt.startswith("Reply T1 S1.") or resume.prompt.startswith("Resume T1 S1."))
        self.assertNotIn("p|t.", resume.aclx_bundle)
        self.assertIn("Preserve: preserve the verified task contract", resume.prompt)
        self.assertIn("Artifacts: runtime/checkpoints/checkpoint_01.aclx", resume.prompt)
        self.assertLessEqual(model_token_count(resume.prompt), 90)

    def test_t2_prompt_contains_machine_contract_and_preserves_outputs_constraints(self) -> None:
        builder = ACLXHybridPromptBuilder()
        payload = builder.build_prompt(
            HybridTaskSpec(
                task="Repair the shared state workflow and keep the review artifact intact.",
                profile="implement",
                lane="shared-state",
                tier="t2",
                cwd=REPO_ROOT_STR,
                outputs=[RUNTIME_SHARED_STATE],
                constraints=["review notes keep Risk and Evidence sections"],
                next_actions=["write shared state", "run tests"],
                stop_conditions=["missing machine artifact"],
                scope_in=[HYBRID_PATH],
                shared_state=True,
                real_handoff_started=True,
            )
        )
        self.assertEqual(payload.tier, "t2")
        self.assertEqual(payload.bridge_mode, "session")
        self.assertIn("Machine contract:", payload.prompt)
        self.assertIn(f"Must write: {RUNTIME_SHARED_STATE}", payload.prompt)
        self.assertIn("Done when: review notes keep Risk and Evidence sections", payload.prompt)
        self.assertNotIn("cwd=", payload.aclx_bundle)
        self.assertNotIn("t=nl", payload.aclx_bundle)
        self.assertNotIn("p=implement", payload.aclx_bundle)
        self.assertNotIn("nx=", payload.aclx_bundle)
        self.assertIn("in=src/aclx/hybrid.py", payload.aclx_bundle)
        self.assertNotIn(f"out={RUNTIME_SHARED_STATE_POSIX}", payload.aclx_bundle)
        self.assertNotIn("d=", payload.aclx_bundle)

    def test_t3_resume_prompt_includes_preserve_artifacts_and_handle(self) -> None:
        builder = ACLXHybridPromptBuilder()
        payload = builder.build_resume_prompt(
            task_code="T3",
            profile="review",
            lane="loop-fix",
            round_label="r3",
            snapshot_code="S2",
            issue_codes=["F2"],
            next_actions=["revise skill"],
            delta_items=["D2"],
            required_artifacts=["runtime/checkpoints/checkpoint_01.aclx", "target_skill/SKILL.md"],
            acceptance_contract=["preserve generator critic refiner roles", "keep strict mode wording"],
            stop_conditions=["scope drift"],
        )
        self.assertTrue(payload.prompt.startswith("Revise T3 S2.") or payload.prompt.startswith("Resume T3 S2."))
        self.assertIn("Preserve: preserve generator critic refiner roles; keep strict mode wording", payload.prompt)
        self.assertIn("Artifacts: runtime/checkpoints/checkpoint_01.aclx; target_skill/SKILL.md", payload.prompt)
        self.assertIn("h|c|c0|1", payload.prompt)

    def test_prompt_builder_uses_contract_as_semantic_source(self) -> None:
        contract = TaskContract(
            goal="Repair shared state flow.",
            operation="implement",
            output_artifacts=["runtime/shared_state.aclx"],
            acceptance_rules=["review notes keep Risk and Evidence sections"],
            stop_conditions=["missing shared artifact"],
            next_actions=["write shared state", "run tests"],
            runtime_needs=RuntimeNeeds(shared_state=True),
        )
        payload = ACLXHybridPromptBuilder().build_prompt(
            HybridTaskSpec(
                task="Repair the shared state workflow and keep the review artifact intact.",
                tier="t2",
                contract=contract,
                current_state=["phase=repair"],
                shared_state=True,
                real_handoff_started=True,
            )
        )
        self.assertIn("Must write: runtime/shared_state.aclx", payload.prompt)
        self.assertIn("Done when: review notes keep Risk and Evidence sections", payload.prompt)
        self.assertNotIn("cwd=", payload.aclx_bundle)
        self.assertNotIn("t=nl", payload.aclx_bundle)
        self.assertNotIn("p=implement", payload.aclx_bundle)
        self.assertNotIn("nx=", payload.aclx_bundle)
        self.assertIn("out=runtime/shared_state.aclx", payload.aclx_bundle)
        self.assertNotIn("d=", payload.aclx_bundle)

    def test_nl_ratio_controls_support_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            compact_path = Path(tmp) / "hybrid_router_map_compact.yaml"
            compact_path.write_text(
                "tiers:\n"
                "  t1:\n"
                "    use_aclx: true\n"
                "    max_items: 1\n"
                "    max_state_items: 1\n"
                "    max_evidence_items: 0\n"
                "    max_risk_items: 0\n"
                "    max_next_actions: 1\n"
                "    include_completed: false\n"
                "    nl_ratio: 0.0\n"
                "    aclx_ratio: 1.0\n",
                encoding="utf-8",
            )
            compact = ACLXHybridPromptBuilder(config_path=compact_path).build_prompt(
                HybridTaskSpec(
                    task="Resume from the shared bundle.",
                    tier="t1",
                    current_state=["resume"],
                    next_actions=["apply fix"],
                    shared_state=True,
                    real_handoff_started=True,
                )
            )
            descriptive_path = Path(tmp) / "hybrid_router_map_descriptive.yaml"
            descriptive_path.write_text(
                "tiers:\n"
                "  t1:\n"
                "    use_aclx: true\n"
                "    max_items: 1\n"
                "    max_state_items: 1\n"
                "    max_evidence_items: 0\n"
                "    max_risk_items: 0\n"
                "    max_next_actions: 1\n"
                "    include_completed: false\n"
                "    nl_ratio: 1.0\n"
                "    aclx_ratio: 0.08\n"
                "    include_next_hint: true\n"
                "    support_label: \"ACL-X bundle:\"\n",
                encoding="utf-8",
            )
            descriptive = ACLXHybridPromptBuilder(config_path=descriptive_path).build_prompt(
                HybridTaskSpec(
                    task="Resume from the shared bundle.",
                    tier="t1",
                    current_state=["resume"],
                    next_actions=["apply fix"],
                    scope_out=["avoid duplicate replay"],
                    shared_state=True,
                    real_handoff_started=True,
                )
            )
        self.assertIn(compact.aclx_bundle, compact.prompt)
        self.assertNotIn("ACL-X bundle:", compact.prompt)
        self.assertIn("ACL-X bundle:", descriptive.prompt)
        self.assertIn("Next: apply fix", descriptive.prompt)

    def test_t1_prompt_uses_single_handoff_contract_lines(self) -> None:
        payload = ACLXHybridPromptBuilder().build_prompt(
            HybridTaskSpec(
                task="Inspect the target and delegate exactly once.",
                tier="t1",
                outputs=["reports/review.md"],
                constraints=[
                    "reports/review.md keeps Decision and Evidence headings",
                    "reports/review.md names src/review_target.py",
                    "reports/review.md explains why empty input breaks cleaned[0]",
                ],
                next_actions=["delegate once", "write review report"],
                stop_conditions=["missing review report"],
                shared_state=True,
                real_handoff_started=True,
            )
        )
        self.assertIn("Single handoff contract:", payload.prompt)
        self.assertIn("One delegated pass only. Keep setup minimal.", payload.prompt)
        self.assertIn("Skip router/config/help/package internals unless the task explicitly needs capability or package facts.", payload.prompt)
        self.assertIn("Must write: reports/review.md", payload.prompt)
        self.assertIn("Done when: reports/review.md keeps Decision and Evidence headings", payload.prompt)
        self.assertIn("Next: delegate once; write review report", payload.prompt)
        self.assertIn(
            "If delegation is blocked by policy or environment, continue locally from inspected evidence.",
            payload.prompt,
        )
        self.assertIn("out=reports/review.md", payload.aclx_bundle)
        self.assertIn("d=reports/review.md_keeps_Decision_and_Evidence_headings", payload.aclx_bundle)
        self.assertIn("stop=missing_review_report", payload.aclx_bundle)

    def test_split_tier_files_load_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tier_dir = root / "tiers"
            tier_dir.mkdir(parents=True, exist_ok=True)
            base_path = root / "hybrid_router_map.yaml"
            base_path.write_text(
                "rules:\n"
                "  H9: \"Tier-local override test.\"\n"
                "profiles:\n"
                "  default: [\"H9\"]\n"
                "tier_files:\n"
                "  t1: tiers/t1.yaml\n"
                "  t2: tiers/t2.yaml\n",
                encoding="utf-8",
            )
            (tier_dir / "t1.yaml").write_text(
                "tiers:\n"
                "  t1:\n"
                "    support_label: \"T1 only\"\n"
                "    nl_ratio: 0.05\n",
                encoding="utf-8",
            )
            (tier_dir / "t2.yaml").write_text(
                "tiers:\n"
                "  t2:\n"
                "    support_label: \"T2 only\"\n"
                "    max_items: 9\n",
                encoding="utf-8",
            )

            loaded = load_hybrid_router_map(str(base_path))

        self.assertEqual(loaded["profiles"]["default"], ["H9"])
        self.assertEqual(loaded["tiers"]["t1"]["support_label"], "T1 only")
        self.assertEqual(loaded["tiers"]["t1"]["nl_ratio"], 0.05)
        self.assertEqual(loaded["tiers"]["t2"]["support_label"], "T2 only")
        self.assertEqual(loaded["tiers"]["t2"]["max_items"], 9)
        self.assertEqual(loaded["tiers"]["t3"]["label"], "loop-heavy")


if __name__ == "__main__":
    unittest.main()
