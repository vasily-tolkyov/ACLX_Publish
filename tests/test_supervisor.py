from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aclx.contract import RuntimeNeeds, TaskContract
from aclx.supervisor import ACLXSupervisor, T0_MINIMAL_AGENTS, _compact_runtime_task, _compact_t1_task


class SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.supervisor = ACLXSupervisor()

    def test_t0_minimal_agents_matches_restored_t0_contract(self) -> None:
        self.assertEqual(
            T0_MINIMAL_AGENTS,
            "# T0\n"
            "One-shot NL only. No ACL-X bundles, runtime files, skills, or handoffs. "
            "Keep exact shape or literal facts only when the task explicitly requires them.\n",
        )

    def test_build_payload_contains_compact_hybrid_contract_by_default(self) -> None:
        payload = self.supervisor.build_payload("Summarize the current task briefly.", cwd=r"D:\codex\acl_x")
        self.assertEqual(payload.aclx_bundle, "")
        self.assertEqual(payload.codex_prompt, "Summarize the current task briefly.")
        self.assertEqual(payload.delegation_json, "{}")
        self.assertEqual(json.loads(payload.delegation_json), {})
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.reasoning_effort, "low")

    def test_adaptive_payload_keeps_meta_skill_port_in_t0(self) -> None:
        payload = self.supervisor.build_payload(
            "Port the verification-triad-router skill into Codex with default hybrid semantics.",
            cwd=r"D:\codex\acl_x",
        )
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.aclx_bundle, "")
        self.assertEqual(payload.codex_prompt, "Port the verification-triad-router skill into Codex with default hybrid semantics.")
        self.assertEqual(payload.reasoning_effort, "low")

    def test_single_output_task_does_not_promote_to_session_mode(self) -> None:
        payload = self.supervisor.build_payload(
            "Write `reports/summary.md`.",
            cwd=r"D:\codex\acl_x",
            outputs=["reports/summary.md"],
            constraints=["reports/summary.md exists"],
        )
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.bridge_mode, "none")
        self.assertEqual(payload.codex_prompt, "Write `reports/summary.md`.")

    def test_compare_and_write_single_output_task_stays_in_t0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True)
            (root / "data" / "a.json").write_text('{"value":1}\n', encoding="utf-8")
            (root / "data" / "b.json").write_text('{"value":2}\n', encoding="utf-8")
            payload = self.supervisor.build_payload(
                "Compare `data/a.json` and `data/b.json`, then write `reports/out.json`.",
                cwd=str(root),
                outputs=["reports/out.json"],
                inputs=["data/a.json", "data/b.json"],
                constraints=["reports/out.json preserves compared values"],
            )
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.bridge_mode, "none")
        self.assertEqual(payload.codex_prompt, "Compare `data/a.json` and `data/b.json`, then write `reports/out.json`.")

    def test_t0_strong_exact_output_task_skips_redundant_guard_and_omits_reasoning_override(self) -> None:
        task = (
            "Read `docs/release_notes.txt`.\n"
            "Return exactly 3 non-empty lines:\n"
            "Tier: t0\n"
            "Decision: <one sentence>\n"
            "Evidence: docs/release_notes.txt; mention strategy lock and adaptive runtime.\n"
            "Do not edit files."
        )
        payload = self.supervisor.build_payload(task, cwd=r"D:\codex\acl_x")
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.reasoning_effort, "")
        self.assertEqual(payload.codex_prompt, task)

    def test_t0_weaker_exact_output_task_keeps_short_guard_and_low_reasoning(self) -> None:
        task = (
            "Read `docs/release_notes.txt`.\n"
            "Return exactly 2 non-empty lines.\n"
            "Mention strategy lock and adaptive runtime.\n"
            "Do not edit files."
        )
        payload = self.supervisor.build_payload(task, cwd=r"D:\codex\acl_x")
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.reasoning_effort, "low")
        self.assertEqual(
            payload.codex_prompt,
            "Keep output shape exact; keep literal facts verbatim.\n" + task,
        )

    def test_t0_structured_literal_task_without_exact_output_keeps_short_guard(self) -> None:
        task = (
            "Read `docs/release_notes.txt`.\n"
            "Tier: t0\n"
            "Decision: <one sentence>\n"
            "Evidence: docs/release_notes.txt; mention strategy lock and adaptive runtime.\n"
            "Do not edit files."
        )
        payload = self.supervisor.build_payload(task, cwd=r"D:\codex\acl_x")
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.reasoning_effort, "low")
        self.assertEqual(
            payload.codex_prompt,
            "Keep output shape exact; keep literal facts verbatim.\n" + task,
        )

    def test_adaptive_payload_promotes_explicit_runtime_loop_to_t3(self) -> None:
        payload = self.supervisor.build_payload(
            "Run the verification loop, checkpoint and resume until the review is clean.",
            cwd=r"D:\codex\acl_x",
            outputs=[r"runtime\checkpoints\checkpoint_01.aclx", r"target_skill\SKILL.md"],
            constraints=["preserve generator critic refiner roles", "keep strict mode wording"],
            stop_conditions=["scope drift"],
            next_actions=["revise skill", "persist checkpoint"],
        )
        self.assertEqual(payload.tier, "t3")
        self.assertEqual(payload.bridge_mode, "session")
        self.assertIn("h|c|c0|1", payload.aclx_bundle)
        self.assertIn("Loop invariants:", payload.codex_prompt)
        self.assertIn("Stop if: scope drift", payload.codex_prompt)
        self.assertIn("Checkpoint:", payload.codex_prompt)
        self.assertIn(payload.aclx_bundle, payload.codex_prompt)
        self.assertNotIn("visible_machine_state=aclx", payload.aclx_bundle)
        self.assertIn("out=runtime/checkpoints/checkpoint_01.aclx", payload.aclx_bundle)
        self.assertNotIn("t=nl", payload.aclx_bundle)
        self.assertNotIn("p=review", payload.aclx_bundle)
        self.assertNotIn("nx=", payload.aclx_bundle)
        self.assertEqual(payload.reasoning_effort, "medium")

    def test_adaptive_t3_payload_preserves_task_contract_when_task_md_is_named(self) -> None:
        task = (
            "Read target_skill/TASK.md first.\n"
            "Preserve the roles line exactly as generator, critic, refiner.\n"
            "Write target_skill/SKILL.md and runtime/checkpoints/checkpoint_01.aclx."
        )
        payload = self.supervisor.build_payload(
            task,
            cwd=r"D:\codex\acl_x",
            task_shape="loop",
            outputs=[r"runtime\checkpoints\checkpoint_01.aclx", r"target_skill\SKILL.md"],
            constraints=["preserve generator critic refiner roles", "keep strict mode wording"],
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
        self.assertEqual(payload.tier, "t3")
        self.assertIn("Read target_skill/TASK.md first.", payload.codex_prompt)
        self.assertIn(
            "Task contract: `TASK.md` is authoritative; read it once and keep explicit wording literal.",
            payload.codex_prompt,
        )
        self.assertIn("Stop if: scope drift", payload.codex_prompt)
        self.assertIn(
            "Direct pass: read TASK.md once, edit named targets, then reply with changed paths and verification only.",
            payload.codex_prompt,
        )
        self.assertIn("Loop guard: contract-complete T3.", payload.codex_prompt)
        self.assertIn("Read target_skill/TASK.md first.", payload.codex_prompt)
        self.assertNotIn("Do not open TASK.md", payload.codex_prompt)

    def test_adaptive_t3_doc_loop_inlines_task_contract_with_low_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_md = root / "TASK.md"
            (root / "docs").mkdir(parents=True)
            (root / "docs" / "release_signoff_handbook.md").write_text(
                "# draft\n",
                encoding="utf-8",
            )
            task_md.write_text(
                "Rewrite `docs/release_signoff_handbook.md` so it becomes a valid loop-heavy operating document and preserves these behavioral constraints:\n\n"
                "- role_drafter: one of drafter\n"
                "- role_checker: one of checker\n"
                "- role_approver: one of approver\n"
                "- keep heading `# release signoff handbook`\n"
                "- keep heading `## roles`\n"
                "- include `current checkpoint` in `reports/signoff_checkpoint.md`\n"
                "- include `blockers` in `reports/signoff_checkpoint.md`\n"
                "- include `next step` in `reports/signoff_checkpoint.md`\n"
                "- keep the output in Markdown\n\n"
                "Keep the final reply concise and list changed file paths.\n",
                encoding="utf-8",
            )
            task = (
                "You are in an isolated workspace. Only edit files under {root}.\n\n"
                f"Read {task_md}.\n"
                "Rewrite `docs/release_signoff_handbook.md` so it satisfies the required loop constraints.\n"
                "Write `reports/signoff_checkpoint.md` as the current checkpoint note for this pass.\n"
                "Keep the final reply concise and list changed file paths.\n"
            ).format(root=root)
            payload = self.supervisor.build_payload(
                task,
                cwd=str(root),
                task_shape="loop",
                outputs=[r"reports\signoff_checkpoint.md", r"docs\release_signoff_handbook.md"],
                constraints=[
                    "loop document keeps the required wording and headings",
                    "checkpoint note records current state and next step",
                ],
                stop_conditions=["scope drift", "missing checkpoint note"],
                next_actions=["rewrite document", "persist checkpoint note"],
            )
            self.assertEqual(payload.tier, "t3")
            self.assertEqual(payload.reasoning_effort, "low")
            self.assertIn("Source: docs/release_signoff_handbook.md", payload.codex_prompt)
            self.assertNotIn("Read first: TASK.md", payload.codex_prompt)
            self.assertIn(
                "Targets: update docs/release_signoff_handbook.md; create reports/signoff_checkpoint.md",
                payload.codex_prompt,
            )
            self.assertIn("Compiled contract is authoritative", payload.codex_prompt)
            self.assertIn("reopen TASK.md only if blocked or Validate fails", payload.codex_prompt)
            self.assertIn(
                "Validate: check wording: docs/release_signoff_handbook.md; check headings: reports/signoff_checkpoint.md",
                payload.codex_prompt,
            )
            self.assertNotIn("Validate: check wording; inspect docs", payload.codex_prompt)
            self.assertNotIn("Template:", payload.codex_prompt)
            self.assertIn("Literal anchors (exact casing):", payload.codex_prompt)
            self.assertIn(
                "Literal anchors (exact casing): drafter",
                payload.codex_prompt,
            )
            self.assertIn("Roles: drafter; checker; approver", payload.codex_prompt)
            self.assertIn("Shape:", payload.codex_prompt)
            self.assertIn("doc headings [# release signoff handbook | ## roles]", payload.codex_prompt)
            self.assertIn(
                "checkpoint headings [## current checkpoint | ## blockers | ## next step]",
                payload.codex_prompt,
            )
            self.assertIn("no extra sections/examples", payload.codex_prompt)
            self.assertIn("Operate once: use Source, Targets, and Validate only;", payload.codex_prompt)
            self.assertIn("reply once, stop", payload.codex_prompt)
            self.assertIn("do not read pending create targets first", payload.codex_prompt)
            self.assertIn("create missing checkpoint targets directly", payload.codex_prompt)
            self.assertIn("carrier-only machine state", payload.codex_prompt)
            self.assertIn("directory/checkpoint probes", payload.codex_prompt)
            self.assertIn("Include each listed literal anchor exactly as written with matching casing at least once", payload.codex_prompt)
            self.assertIn("do not inflect, paraphrase, or synonym-swap literal anchors", payload.codex_prompt)
            self.assertIn("keep the smallest valid text only", payload.codex_prompt)
            self.assertIn("Validate with direct pattern checks (`rg -n` or `Select-String`) only.", payload.codex_prompt)
            self.assertIn("No plan chatter", payload.codex_prompt)
            self.assertIn("post-edit rereads", payload.codex_prompt)
            self.assertIn("Final reply: `Changed paths` and `Verification` only;", payload.codex_prompt)
            self.assertIn("relative paths, one short line per check, no extra prose", payload.codex_prompt)
            self.assertNotIn(
                "Validation path: prefer direct pattern checks on named targets (for example `rg -n`); avoid full-file rereads unless a required fact is missing.",
                payload.codex_prompt,
            )
            self.assertNotIn(
                "Seal: the ACL-X bundle below is carrier-only. No skill docs, AGENTS, runtime docs/files, hidden runtime state, router calls, unnamed paths, directory probes, or checkpoint existence probes. Do not reread TASK.md or edited targets unless a required fact is missing or Validate fails. No plan updates.",
                payload.codex_prompt,
            )
            self.assertIn("Loop guard: sealed compiled T3 doc loop; use named surfaces only.", payload.codex_prompt)
            self.assertNotIn("Task contract lines:", payload.codex_prompt)
            self.assertNotIn(f"Read {task_md}.", payload.codex_prompt)

    def test_adaptive_t3_complex_doc_loop_uses_low_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_md = root / "TASK.md"
            task_md.write_text(
                "Rewrite `docs/resume_handoff_guide.md` so it becomes a valid loop-heavy operating document and preserves these behavioral constraints:\n\n"
                "- role_request_owner: one of request owner\n"
                "- role_resumer: one of resumer\n"
                "- role_reviewer: one of reviewer\n"
                "- resume_latest: one of resume from the latest checkpoint, resume from latest checkpoint\n"
                "- unresolved_first: one of unresolved items first, open items first\n"
                "- last_verified_step: one of last verified step\n"
                "- next_pending_step: one of next pending step\n"
                "- no_restart: one of do not restart from scratch, continue from the existing checkpoint\n"
                "- preserve_prior_evidence: one of preserve prior evidence, do not rewrite prior evidence\n"
                "- keep heading `# resume handoff guide`\n"
                "- keep heading `## roles`\n"
                "- include `current checkpoint` in `reports/resume_checkpoint.md`\n",
                encoding="utf-8",
            )
            task = (
                "You are in an isolated workspace. Only edit files under {root}.\n\n"
                f"Read {task_md}.\n"
                "Rewrite `docs/resume_handoff_guide.md` so it satisfies the required loop constraints.\n"
                "Write `reports/resume_checkpoint.md` as the current checkpoint note for this pass.\n"
                "Keep the final reply concise and list changed file paths.\n"
            ).format(root=root)
            payload = self.supervisor.build_payload(
                task,
                cwd=str(root),
                task_shape="loop",
                outputs=[r"reports\resume_checkpoint.md", r"docs\resume_handoff_guide.md"],
                constraints=[
                    "loop document keeps the required wording and headings",
                    "checkpoint note records current state and next step",
                ],
                stop_conditions=["scope drift", "missing checkpoint note"],
                next_actions=["rewrite document", "persist checkpoint note"],
            )
            self.assertEqual(payload.tier, "t3")
            self.assertEqual(payload.reasoning_effort, "low")

    def test_full_style_preserves_debug_heavy_prompt(self) -> None:
        payload = self.supervisor.build_payload("Create a compact ACL-X handoff.", cwd=r"D:\codex\acl_x", style="full")
        self.assertIn("$aclx-runtime", payload.codex_prompt)
        self.assertIn("$acl-x-protocol", payload.codex_prompt)
        self.assertIn("Avoid unnecessary shell commands.", payload.codex_prompt)
        self.assertIn(payload.delegation_json, payload.codex_prompt)

    def test_hybrid_style_is_an_adaptive_alias(self) -> None:
        adaptive = self.supervisor.build_payload(
            "Coordinate reusable shared state across the next phase.",
            cwd=r"D:\codex\acl_x",
            outputs=[r"runtime\shared_state.aclx"],
            constraints=["write the shared state before review"],
            next_actions=["write shared state", "review output"],
            shared_state=True,
        )
        hybrid = self.supervisor.build_payload(
            "Coordinate reusable shared state across the next phase.",
            cwd=r"D:\codex\acl_x",
            style="hybrid",
            outputs=[r"runtime\shared_state.aclx"],
            constraints=["write the shared state before review"],
            next_actions=["write shared state", "review output"],
            shared_state=True,
        )
        self.assertEqual(hybrid.style, "adaptive")
        self.assertEqual(hybrid.tier, adaptive.tier)
        self.assertEqual(hybrid.bridge_mode, adaptive.bridge_mode)
        self.assertEqual(hybrid.codex_prompt, adaptive.codex_prompt)

    def test_adaptive_t2_payload_uses_session_wrapped_prompt(self) -> None:
        payload = self.supervisor.build_payload(
            "Coordinate reusable shared state across the next phase.",
            cwd=r"D:\codex\acl_x",
            outputs=[r"runtime\shared_state.aclx", r"reports\review_notes.md"],
            constraints=["review notes keep Risk and Evidence sections"],
            next_actions=["write shared state", "run tests"],
            stop_conditions=["missing shared artifact"],
            shared_state=True,
        )
        self.assertEqual(payload.tier, "t2")
        self.assertEqual(payload.bridge_mode, "session")
        self.assertIn("Machine contract:", payload.codex_prompt)
        self.assertIn("Must write:", payload.codex_prompt)
        self.assertIn("Write requirements:", payload.codex_prompt)
        self.assertIn("Done when:", payload.codex_prompt)
        self.assertIn("Artifact rule:", payload.codex_prompt)
        self.assertIn(
            "Execute once: before the first validator run, complete one edit batch for source changes and every `Must write` target, creating any missing required artifacts directly from the named spec in that same batch. Do not split source fixes and artifact writes across multiple edit passes. Apply `Artifact defaults` in that first write. Then run only Validate (`check files` = existence only) and reply with `Changed paths` and `Executed validator result` only; use plain relative paths and one short line per item, with no links, bullets, or extra prose. Re-edit only if Validate fails. No progress messages or rereads of written artifacts unless Validate fails.",
            payload.codex_prompt,
        )
        self.assertIn(
            "Runtime guard: contract-complete T2. Use this contract directly; skip skill/runtime docs, directory probes, and progress chatter unless a required fact is missing.",
            payload.codex_prompt,
        )
        self.assertIn(payload.aclx_bundle, payload.codex_prompt)
        self.assertEqual(payload.reasoning_effort, "low")

    def test_supervisor_uses_resolved_contract_without_rebuilding_semantics_locally(self) -> None:
        contract = TaskContract(
            goal="Coordinate reusable shared state across the next phase.",
            operation="implement",
            output_artifacts=["runtime/shared_state.aclx", "reports/review_notes.md"],
            acceptance_rules=["review notes keep Risk and Evidence sections"],
            stop_conditions=["missing shared artifact"],
            next_actions=["write shared state", "run tests"],
            runtime_needs=RuntimeNeeds(expected_handoffs=2, expected_rounds=2, child_agents=2, shared_state=True),
        )
        payload = self.supervisor.build_payload(
            "Coordinate reusable shared state across the next phase.",
            cwd=r"D:\codex\acl_x",
            contract=contract,
        )
        self.assertEqual(payload.tier, "t2")
        self.assertIn("Must write: runtime/shared_state.aclx; reports/review_notes.md", payload.codex_prompt)
        self.assertIn("Write requirements: review notes keep Risk and Evidence sections", payload.codex_prompt)
        self.assertIn("Done when: required artifact files exist", payload.codex_prompt)

    def test_adaptive_t2_payload_preserves_multiline_contract_lines(self) -> None:
        task = (
            "You are in an isolated workspace. Only edit files under D:\\tmp\\workspace.\n\n"
            "Read target/TASK.md first.\n"
            "Fix `src/stage_plan.py` so `python -m unittest discover -s tests -q` passes.\n"
            "Write `runtime/shared_state.aclx` as an ACL-X C-layer machine-state artifact for the next phase.\n"
            "Write `reports/review_notes.md` with headings `Risk` and `Evidence`.\n"
            "Keep the final reply concise and list changed file paths.\n"
        )
        payload = self.supervisor.build_payload(
            task,
            cwd=r"D:\codex\acl_x",
            task_shape="shared_state",
            expected_handoffs=2,
            expected_rounds=2,
            child_agents=2,
            shared_state=True,
            outputs=[r"runtime\shared_state.aclx", r"reports\review_notes.md"],
            constraints=[
                "python -m unittest discover -s tests -q passes",
                "runtime/shared_state.aclx uses ACL-X C-layer text",
                "reports/review_notes.md keeps Risk and Evidence headings",
            ],
            next_actions=["write shared state", "run tests"],
            stop_conditions=["missing shared artifact", "tests failing"],
        )
        self.assertEqual(payload.tier, "t2")
        self.assertIn("Fix `src/stage_plan.py` so `python -m unittest discover -s tests -q` passes.", payload.codex_prompt)
        self.assertNotIn("Read target/TASK.md first.", payload.codex_prompt)
        self.assertIn("Validate: run tests: python -m unittest discover -s tests -q", payload.codex_prompt)
        self.assertNotIn("Keep the final reply concise and list changed file paths.", payload.codex_prompt)

    def test_adaptive_t1_payload_uses_low_reasoning_and_single_handoff_contract(self) -> None:
        payload = self.supervisor.build_payload(
            "Inspect `src/review_target.py`, delegate exactly once, and write `reports/review.md`.",
            cwd=r"D:\codex\acl_x",
            profile="review",
            task_shape="delegated_once",
            expected_handoffs=1,
            expected_rounds=1,
            child_agents=1,
            shared_state=True,
            outputs=["reports/review.md"],
            constraints=[
                "reports/review.md keeps Decision and Evidence headings",
                "reports/review.md names src/review_target.py",
                "reports/review.md explains why empty input breaks cleaned[0]",
            ],
            stop_conditions=["missing review report"],
            next_actions=["delegate once", "write review report"],
        )
        self.assertEqual(payload.tier, "t1")
        self.assertEqual(payload.bridge_mode, "bundle")
        self.assertEqual(payload.reasoning_effort, "low")
        self.assertNotIn("delegate exactly once, and write `reports/review.md`", payload.codex_prompt)
        self.assertIn("Single handoff contract:", payload.codex_prompt)
        self.assertIn("Must write: reports/review.md", payload.codex_prompt)
        self.assertIn("Done when: reports/review.md keeps Decision and Evidence headings", payload.codex_prompt)
        self.assertNotIn("reports/review.md names src/review_target.py", payload.codex_prompt)
        self.assertNotIn(
            "Done when: reports/review.md keeps Decision and Evidence headings; reports/review.md names src/review_target.py; delegate exactly once",
            payload.codex_prompt,
        )
        self.assertIn("Next: write review report", payload.codex_prompt)
        self.assertNotIn("Next: delegate once; write review report", payload.codex_prompt)
        self.assertIn(
            "One reviewer pass only. Use it only if direct inspection still leaves a material ambiguity or missing fact for the required result, and that reviewer can inspect the same named inputs directly in the current workspace without extra setup or policy changes.",
            payload.codex_prompt,
        )
        self.assertIn(
            "Do not use the reviewer pass to reconfirm a conclusion already clear from direct inspection.",
            payload.codex_prompt,
        )
        self.assertIn(
            "Do not read skill/router docs or probe commands to discover delegation.",
            payload.codex_prompt,
        )
        self.assertNotIn(
            "One delegated pass only. Use it only if an exposed reviewer can inspect the same named inputs directly in the current workspace with its own tools.",
            payload.codex_prompt,
        )
        self.assertIn("If the required conclusion is already clear from direct inspection", payload.codex_prompt)
        self.assertIn("or no such reviewer is immediately readable", payload.codex_prompt)
        self.assertIn("use named inputs as working evidence", payload.codex_prompt)
        self.assertIn("create required outputs directly", payload.codex_prompt)
        self.assertIn("skip output-path probes", payload.codex_prompt)
        self.assertIn("artifact rereads", payload.codex_prompt)
        self.assertIn("extra line-number extraction", payload.codex_prompt)
        self.assertIn("workspace listings", payload.codex_prompt)
        self.assertIn("code excerpts unless explicitly required or a fact remains ambiguous", payload.codex_prompt)
        self.assertNotIn("p=review", payload.aclx_bundle)
        self.assertIn("out=reports/review.md", payload.aclx_bundle)
        self.assertNotIn("named report directly", payload.codex_prompt)

    def test_adaptive_t1_payload_keeps_generic_fallback_for_non_review_artifact(self) -> None:
        payload = self.supervisor.build_payload(
            "Inspect `src/handoff_target.py`, delegate exactly once, and write `artifacts/handoff.json`.",
            cwd=r"D:\codex\acl_x",
            profile="default",
            task_shape="delegated_once",
            expected_handoffs=1,
            expected_rounds=1,
            child_agents=1,
            shared_state=True,
            outputs=["artifacts/handoff.json"],
            constraints=[
                "artifacts/handoff.json contains summary and risk keys",
                "artifacts/handoff.json names src/handoff_target.py",
            ],
            stop_conditions=["missing handoff artifact"],
            next_actions=["delegate once", "write handoff artifact"],
        )
        self.assertEqual(payload.tier, "t1")
        self.assertEqual(payload.bridge_mode, "bundle")
        self.assertEqual(payload.reasoning_effort, "low")
        self.assertNotIn("delegate exactly once, and write `artifacts/handoff.json`", payload.codex_prompt)
        self.assertIn("Must write: artifacts/handoff.json", payload.codex_prompt)
        self.assertIn("Next: write handoff artifact", payload.codex_prompt)
        self.assertNotIn("Next: delegate once; write handoff artifact", payload.codex_prompt)
        self.assertIn(
            "One reviewer pass only. Use it only if direct inspection still leaves a material ambiguity or missing fact for the required result, and that reviewer can inspect the same named inputs directly in the current workspace without extra setup or policy changes.",
            payload.codex_prompt,
        )
        self.assertIn(
            "Do not use the reviewer pass to reconfirm a conclusion already clear from direct inspection.",
            payload.codex_prompt,
        )
        self.assertIn(
            "Do not read skill/router docs or probe commands to discover delegation.",
            payload.codex_prompt,
        )
        self.assertNotIn(
            "One delegated pass only. Use it only if an exposed reviewer can inspect the same named inputs directly in the current workspace with its own tools.",
            payload.codex_prompt,
        )
        self.assertNotIn(
            "Done when: artifacts/handoff.json contains summary and risk keys; artifacts/handoff.json names src/handoff_target.py; delegate exactly once",
            payload.codex_prompt,
        )
        self.assertIn("If the required conclusion is already clear from direct inspection", payload.codex_prompt)
        self.assertIn("or no such reviewer is immediately readable", payload.codex_prompt)
        self.assertIn("use named inputs as working evidence", payload.codex_prompt)
        self.assertIn("create required outputs directly", payload.codex_prompt)
        self.assertIn("skip output-path probes", payload.codex_prompt)
        self.assertIn("artifact rereads", payload.codex_prompt)
        self.assertIn("extra line-number extraction", payload.codex_prompt)
        self.assertIn("workspace listings", payload.codex_prompt)
        self.assertIn("code excerpts unless explicitly required or a fact remains ambiguous", payload.codex_prompt)
        self.assertNotIn("p=default", payload.aclx_bundle)
        self.assertIn("out=artifacts/handoff.json", payload.aclx_bundle)

    def test_adaptive_t1_payload_keeps_visible_next_when_next_step_is_not_redundant_write(self) -> None:
        payload = self.supervisor.build_payload(
            "Inspect `src/review_target.py`, delegate exactly once, and write `reports/review.md`.",
            cwd=r"D:\codex\acl_x",
            profile="review",
            task_shape="delegated_once",
            expected_handoffs=1,
            expected_rounds=1,
            child_agents=1,
            shared_state=True,
            outputs=["reports/review.md"],
            constraints=["reports/review.md keeps Decision and Evidence headings"],
            next_actions=["delegate once", "run validator"],
        )
        self.assertEqual(payload.tier, "t1")
        self.assertIn("Must write: reports/review.md", payload.codex_prompt)
        self.assertIn("Next: run validator", payload.codex_prompt)
        self.assertIn("nx=run_validator", payload.aclx_bundle)

    def test_compact_t1_task_merges_inspect_and_bug_line(self) -> None:
        task = (
            "Inspect `src/attendance_target.py`.\n"
            "Identify the highest-risk bug with a concrete file path and explain why a zero-room input breaks the function.\n"
            "Keep the final reply concise.\n"
        )
        compact = _compact_t1_task(
            task,
            outputs=["reports/review.md"],
            constraints=["reports/review.md keeps Decision and Evidence headings"],
        )
        self.assertEqual(
            compact,
            "Inspect `src/attendance_target.py` and identify the highest-risk bug with a concrete file path and explain why a zero-room input breaks the function.",
        )

    def test_missing_t2_or_t3_contract_data_falls_back_to_nl(self) -> None:
        payload = self.supervisor.build_payload(
            "Run the verification loop, checkpoint and resume until the review is clean.",
            cwd=r"D:\codex\acl_x",
        )
        self.assertEqual(payload.tier, "t0")
        self.assertEqual(payload.bridge_mode, "none")
        self.assertEqual(payload.codex_prompt, "Run the verification loop, checkpoint and resume until the review is clean.")
        self.assertEqual(json.loads(payload.delegation_json), {})
        self.assertEqual(payload.reasoning_effort, "low")

    def test_compact_runtime_task_preserves_whole_contract_lines(self) -> None:
        task = (
            "You are in an isolated workspace. Only edit files under D:\\tmp\\workspace.\n\n"
            "Read D:\\tmp\\workspace\\TASK.md first.\n"
            "Fix `src/stage_plan.py` so `python -m unittest discover -s tests -q` passes.\n"
            "Keep the exact phrase `Risk` and `Evidence` in the review file.\n"
            "Write `runtime/shared_state.aclx` as an ACL-X C-layer machine-state artifact for the next phase.\n"
            "Keep the final reply concise and list changed file paths.\n"
        )
        compact = _compact_runtime_task(
            task,
            outputs=["runtime/shared_state.aclx", "reports/review_notes.md"],
            constraints=["python -m unittest discover -s tests -q passes"],
            tier="t2",
            preserve_task_contract=True,
            task_contract_max_lines=3,
            task_contract_max_chars=220,
            whole_line_only=True,
        )
        self.assertEqual(
            compact,
            "Fix `src/stage_plan.py` so `python -m unittest discover -s tests -q` passes.\n"
            "Keep the exact phrase `Risk` and `Evidence` in the review file.",
        )
        self.assertNotIn("...", compact)
        self.assertNotIn("Write `runtime/shared_state.aclx`", compact)

    def test_compact_runtime_task_falls_back_to_original_text_when_contract_is_empty(self) -> None:
        task = (
            "You are in an isolated workspace. Only edit files under D:\\tmp\\workspace.\n"
            "Write `runtime/shared_state.aclx`.\n"
            "Keep the final reply concise and list changed file paths.\n"
        )
        compact = _compact_runtime_task(
            task,
            outputs=["runtime/shared_state.aclx"],
            constraints=[],
            tier="t2",
            preserve_task_contract=True,
            task_contract_max_lines=3,
            task_contract_max_chars=220,
            whole_line_only=True,
        )
        self.assertEqual(compact, task.strip())


if __name__ == "__main__":
    unittest.main()
