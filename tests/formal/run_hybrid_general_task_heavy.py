from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_ROOT = Path(__file__).resolve().parent
RUNS_ROOT = FORMAL_ROOT / "runs"
BASE_RUNNER_PATH = FORMAL_ROOT / "run_hybrid_pre_release_heavy.py"


def _load_base_module():
    spec = importlib.util.spec_from_file_location("formal_hybrid_base", BASE_RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load base formal runner: {BASE_RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = _load_base_module()

TaskSpec = base.TaskSpec
RunResult = base.RunResult


def t2_general_task(
    *,
    name: str,
    group: int,
    title: str,
    description: str,
    source_path: str,
    source_body: str,
    test_path: str,
    test_body: str,
    context_path: str,
    context_keys: list[str],
    notes_path: str = "reports/repair_notes.md",
) -> TaskSpec:
    task_md = (
        f"Fix the workflow bug in `{source_path}`.\n\n"
        "Requirements:\n\n"
        "- `python -m unittest discover -s tests -q` must pass.\n"
        f"- Write `{context_path}` as the machine-readable handoff package for the next phase.\n"
        f"- `{context_path}` must include keys: {', '.join(context_keys)}.\n"
        f"- Write `{notes_path}` with headings `Risk` and `Evidence`.\n"
        "- Keep the final reply concise and list changed file paths.\n"
    )
    prompt = (
        "You are in an isolated workspace. Only edit files under {workspace}.\n\n"
        "Read {workspace}\\TASK.md.\n"
        f"Fix `{source_path}` so `python -m unittest discover -s tests -q` passes.\n"
        f"Write `{context_path}` as the machine-readable handoff package for the next phase.\n"
        f"Write `{notes_path}` with headings `Risk` and `Evidence`.\n"
        "Keep the final reply concise and list changed file paths.\n"
    )
    files = {
        "TASK.md": task_md,
        source_path: source_body,
        test_path: test_body,
    }
    return TaskSpec(
        name=name,
        tier="t2",
        group=group,
        title=title,
        description=description,
        profile="implement",
        prompt=prompt,
        workspace_files=files,
        validator="t2_generic",
        task_shape="shared_state",
        expected_handoffs=2,
        expected_rounds=2,
        child_agents=2,
        shared_state=True,
        outputs=[context_path, notes_path],
        constraints=[
            "python -m unittest discover -s tests -q passes",
            f"{context_path} keeps the required handoff keys",
            f"{notes_path} keeps Risk and Evidence headings",
        ],
        stop_conditions=["missing machine-readable handoff package", "tests failing"],
        next_actions=["write handoff package", "run tests"],
        contract_family="generic_shared_state_repair",
        adapter_family="python",
        validator_type="unit_tests_and_generic_artifacts",
        resumability_expected=False,
        exactness_expected=True,
        quality_spec={
            "context_path": context_path,
            "context_keys": context_keys,
            "notes_path": notes_path,
            "headings": ["Risk", "Evidence"],
        },
    )


def t3_general_task(
    *,
    name: str,
    group: int,
    title: str,
    description: str,
    document_path: str,
    document_stub: str,
    checkpoint_path: str,
    required_checks: dict[str, list[str]],
    required_headings: list[str],
    checkpoint_checks: list[str],
) -> TaskSpec:
    task = base.t3_task(
        name=name,
        group=group,
        title=title,
        description=description,
        document_path=document_path,
        document_stub=document_stub,
        checkpoint_path=checkpoint_path,
        required_checks=required_checks,
        required_headings=required_headings,
        checkpoint_checks=checkpoint_checks,
    )
    # Do not tell the model to stop on an artifact that it is supposed to create in this run.
    task.stop_conditions = ["scope drift", "missing required source facts"]
    return task


def build_tasks() -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    tasks.append(
        base.t0_task(
            name="t0_g1_vendor_return_brief",
            group=1,
            title="Store pickup brief",
            description="Single-surface extraction from a generic store-pickup note with fixed evidence wording.",
            file_path="docs/store_pickup_rules.txt",
            file_body=(
                "Store pickup rules\n"
                "- standard orders use a 2-hour pickup hold after ready notice\n"
                "- photo id is required before handoff\n"
                "- oversized items use curbside check-in instead of counter release\n"
                "- unresolved substitutions stay visible in the pickup note\n"
            ),
            required_facts=["2-hour pickup hold", "photo id"],
            contract_family="generic_policy_extract",
            adapter_family="docs",
        )
    )
    tasks.append(
        base.t0_task(
            name="t0_g2_capacity_threshold_brief",
            group=2,
            title="Meeting capacity brief",
            description="Single-surface extraction from a generic meeting-capacity config with fixed-format output.",
            file_path="data/room_capacity_thresholds.json",
            file_body=(
                "{\n"
                "  \"room_rules\": [\n"
                "    \"amber review starts at 75 percent occupancy\",\n"
                "    \"red review starts at 90 percent occupancy\",\n"
                "    \"overflow seating requires duty manager approval\",\n"
                "    \"external guest delays are reported before internal reshuffling\"\n"
                "  ],\n"
                "  \"notes\": \"apply the highest active threshold first\"\n"
                "}\n"
            ),
            required_facts=["75 percent occupancy", "90 percent occupancy"],
            contract_family="generic_threshold_extract",
            adapter_family="generic-fs",
        )
    )
    tasks.append(
        base.t0_task(
            name="t0_g3_exception_note_brief",
            group=3,
            title="Field outage note brief",
            description="Single-surface extraction from a generic field-outage note with literal evidence requirements.",
            file_path="docs/field_outage_note.txt",
            file_body=(
                "Field outage note\n"
                "- customer-visible outage comes before internal tuning notes\n"
                "- the rollback coordinator is named before closure\n"
                "- unresolved blockers stay visible in the handoff note\n"
                "- scope stays within the named site set\n"
            ),
            required_facts=["customer-visible outage", "rollback coordinator"],
            contract_family="generic_ops_note_extract",
            adapter_family="docs",
        )
    )
    tasks.append(
        base.t1_task(
            name="t1_g1_blank_invoice_review",
            group=1,
            title="Blank shipment code review",
            description="Exactly one review handoff over a shipment helper that breaks when no valid shipment codes remain.",
            source_path="src/shipment_target.py",
            source_body=(
                "def latest_shipment_code(records: list[dict[str, str]]) -> str:\n"
                "    \"\"\"Return the latest non-empty shipment code. Empty input should return 'missing'.\"\"\"\n"
                "    cleaned = [row['shipment_code'].strip() for row in records if row.get('shipment_code', '').strip()]\n"
                "    return cleaned[0]\n"
            ),
            report_bug_line="Identify the highest-risk bug with a concrete file path and explain why an empty or blank shipment-code set breaks the function.",
            keyword_groups=[["empty", "blank"], ["cleaned[0]", "indexerror", "list index"]],
        )
    )
    tasks.append(
        base.t1_task(
            name="t1_g2_zero_sample_review",
            group=2,
            title="Zero attendee review",
            description="Exactly one review handoff over a facility helper with a zero-room failure mode.",
            source_path="src/attendance_target.py",
            source_body=(
                "def average_attendance(total_people: int, rooms_open: int) -> float:\n"
                "    \"\"\"Return the average attendance per open room.\"\"\"\n"
                "    return abs(total_people) / rooms_open\n"
            ),
            report_bug_line="Identify the highest-risk bug with a concrete file path and explain why a zero-room input breaks the function.",
            keyword_groups=[["zero", "0", "rooms open"], ["division by zero", "rooms_open", "zerodivisionerror"]],
        )
    )
    tasks.append(
        base.t1_task(
            name="t1_g3_unknown_route_review",
            group=3,
            title="Unknown locker review",
            description="Exactly one review handoff over a lookup helper that crashes on unknown locker ids.",
            source_path="src/locker_target.py",
            source_body=(
                "def locker_owner(lockers: dict[str, dict[str, str]], locker_id: str) -> str:\n"
                "    \"\"\"Return the owner display name for the given locker id.\"\"\"\n"
                "    normalized = locker_id.strip().lower()\n"
                "    return lockers[normalized]['owner'].strip()\n"
            ),
            report_bug_line="Identify the highest-risk bug with a concrete file path and explain why an unknown locker id breaks the function.",
            keyword_groups=[["unknown", "missing locker", "blank"], ["keyerror", "lockers[normalized]", "missing key"]],
        )
    )
    tasks.append(
        t2_general_task(
            name="t2_g1_picklist_group_fix",
            group=1,
            title="Delivery slot repair",
            description="Multi-step repair of a generic delivery-slot collector with reusable handoff state and validator-backed notes.",
            source_path="src/delivery_slot.py",
            source_body=(
                "from __future__ import annotations\n\n"
                "def collect_delivery_slots(slots: list[str]) -> list[str]:\n"
                "    cleaned: list[str] = []\n"
                "    seen: set[str] = set()\n"
                "    for slot in slots:\n"
                "        value = slot.strip().lower()\n"
                "        if not value:\n"
                "            continue\n"
                "        if value in seen:\n"
                "            continue\n"
                "        seen.add(value)\n"
                "        cleaned.insert(0, value)\n"
                "    return cleaned\n"
            ),
            test_path="tests/test_delivery_slot.py",
            test_body=(
                "from __future__ import annotations\n\n"
                "import unittest\n\n"
                "from src.delivery_slot import collect_delivery_slots\n\n\n"
                "class DeliverySlotTests(unittest.TestCase):\n"
                "    def test_empty_slots(self) -> None:\n"
                "        self.assertEqual(collect_delivery_slots([]), [])\n\n"
                "    def test_preserves_first_seen_order(self) -> None:\n"
                "        slots = ['morning', ' noon ', 'Morning', '', 'evening', 'noon', 'overnight']\n"
                "        self.assertEqual(collect_delivery_slots(slots), ['morning', 'noon', 'evening', 'overnight'])\n\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
            context_path="artifacts/delivery_slot_context.json",
            context_keys=["status", "next_stage", "validated_tests"],
        )
    )
    tasks.append(
        t2_general_task(
            name="t2_g2_capacity_window_fix",
            group=2,
            title="Maintenance window repair",
            description="Multi-step repair of a generic maintenance-window collector with machine-readable next-phase context.",
            source_path="src/maintenance_window.py",
            source_body=(
                "from __future__ import annotations\n\n"
                "def collect_maintenance_windows(windows: list[str]) -> list[str]:\n"
                "    ordered: list[str] = []\n"
                "    seen: set[str] = set()\n"
                "    for window in windows:\n"
                "        value = window.strip().lower()\n"
                "        if not value:\n"
                "            continue\n"
                "        if value in seen:\n"
                "            continue\n"
                "        seen.add(value)\n"
                "        ordered.append(value)\n"
                "    return ordered[1:]\n"
            ),
            test_path="tests/test_maintenance_window.py",
            test_body=(
                "from __future__ import annotations\n\n"
                "import unittest\n\n"
                "from src.maintenance_window import collect_maintenance_windows\n\n\n"
                "class MaintenanceWindowTests(unittest.TestCase):\n"
                "    def test_empty_windows(self) -> None:\n"
                "        self.assertEqual(collect_maintenance_windows([]), [])\n\n"
                "    def test_keeps_first_seen_order(self) -> None:\n"
                "        windows = ['precheck', ' overnight ', 'Precheck', '', 'freeze', 'overnight']\n"
                "        self.assertEqual(collect_maintenance_windows(windows), ['precheck', 'overnight', 'freeze'])\n\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
            context_path="artifacts/maintenance_context.json",
            context_keys=["status", "owner", "validated_tests"],
        )
    )
    tasks.append(
        t2_general_task(
            name="t2_g3_demand_rollup_fix",
            group=3,
            title="Shift label repair",
            description="Multi-step repair of a generic shift-label helper with reusable machine-readable handoff state.",
            source_path="src/shift_label.py",
            source_body=(
                "from __future__ import annotations\n\n"
                "def collect_shift_labels(labels: list[str]) -> list[str]:\n"
                "    cleaned: list[str] = []\n"
                "    for label in labels:\n"
                "        value = label.strip().lower()\n"
                "        if not value:\n"
                "            continue\n"
                "        if value not in cleaned:\n"
                "            cleaned.append(value)\n"
                "    return list(reversed(cleaned))\n"
            ),
            test_path="tests/test_shift_label.py",
            test_body=(
                "from __future__ import annotations\n\n"
                "import unittest\n\n"
                "from src.shift_label import collect_shift_labels\n\n\n"
                "class ShiftLabelTests(unittest.TestCase):\n"
                "    def test_empty_labels(self) -> None:\n"
                "        self.assertEqual(collect_shift_labels([]), [])\n\n"
                "    def test_keeps_first_label_order(self) -> None:\n"
                "        labels = ['early', ' late ', 'Early', '', 'swing', 'late']\n"
                "        self.assertEqual(collect_shift_labels(labels), ['early', 'late', 'swing'])\n\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
            context_path="artifacts/shift_context.json",
            context_keys=["status", "next_label", "validated_tests"],
        )
    )
    tasks.append(
        t3_general_task(
            name="t3_g1_procurement_exception_playbook",
            group=1,
            title="Warehouse cycle count playbook",
            description="Loop-heavy rewrite of a generic warehouse cycle-count playbook with resumable checkpoints and discrepancy-first ordering.",
            document_path="docs/warehouse_cycle_count_playbook.md",
            document_stub=(
                "# Warehouse Cycle Count Playbook\n\n"
                "This draft is incomplete.\n\n"
                "Close the count first, record evidence later, and expand scope if a nearby aisle also looks wrong.\n"
            ),
            checkpoint_path="reports/warehouse_cycle_count_checkpoint.md",
            required_checks={
                "role_lead": ["lead counter"],
                "role_checker": ["spot checker", "checker"],
                "role_recorder": ["recorder"],
                "latest_variance": ["latest variance note first", "use the latest variance note first"],
                "open_discrepancies": ["open discrepancies before closeout", "unresolved discrepancies first"],
                "bounded_scope": ["stay within the named aisle scope", "do not expand scope"],
                "evidence_first": ["evidence before final closeout", "evidence-first"],
            },
            required_headings=["# warehouse cycle count playbook", "## roles", "## count loop", "## guardrails"],
            checkpoint_checks=["current state", "open discrepancies", "next pass"],
        )
    )
    tasks.append(
        t3_general_task(
            name="t3_g2_month_end_handoff_guide",
            group=2,
            title="Vendor maintenance handoff guide",
            description="Loop-heavy rewrite of a generic vendor-maintenance handoff guide with checkpoint continuity and unresolved-first ordering.",
            document_path="docs/vendor_maintenance_handoff_guide.md",
            document_stub=(
                "# Vendor Maintenance Handoff Guide\n\n"
                "This draft is incomplete.\n\n"
                "Start with whatever looks urgent, skip roles, and clean up open work after the next owner takes over.\n"
            ),
            checkpoint_path="reports/vendor_maintenance_handoff_checkpoint.md",
            required_checks={
                "role_sender": ["outgoing owner", "sender"],
                "role_receiver": ["incoming owner", "receiver"],
                "role_verifier": ["verifier"],
                "latest_checkpoint": ["latest checkpoint first", "use the latest checkpoint first"],
                "open_actions": ["open actions before summary", "unresolved actions first"],
                "bounded_scope": ["stay within the supplied service scope", "do not expand scope"],
                "evidence_first": ["evidence before final summary", "evidence-first"],
            },
            required_headings=["# vendor maintenance handoff guide", "## roles", "## handoff loop", "## guardrails"],
            checkpoint_checks=["current state", "open actions", "next pass"],
        )
    )
    tasks.append(
        t3_general_task(
            name="t3_g3_service_change_readiness_manual",
            group=3,
            title="Site readiness manual",
            description="Loop-heavy rewrite of a generic site-readiness manual with explicit roles, blocker-first sequencing, and resumable checkpoints.",
            document_path="docs/site_readiness_manual.md",
            document_stub=(
                "# Site Readiness Manual\n\n"
                "This draft is incomplete.\n\n"
                "Declare readiness first, collect evidence later, and reopen only if another team complains.\n"
            ),
            checkpoint_path="reports/site_readiness_checkpoint.md",
            required_checks={
                "role_planner": ["planner"],
                "role_checker": ["checker"],
                "role_approver": ["approver"],
                "evidence_first": ["evidence before ready status", "evidence-first"],
                "open_blockers": ["open blockers first", "unresolved blockers first"],
                "bounded_scope": ["stay within the named site scope", "do not expand scope"],
                "rollback_visible": ["rollback trigger stays visible", "rollback trigger is visible"],
            },
            required_headings=["# site readiness manual", "## roles", "## readiness loop", "## guardrails"],
            checkpoint_checks=["current state", "open blockers", "next pass"],
        )
    )
    return tasks


def select_tasks(tasks: list[TaskSpec], names: list[str]) -> list[TaskSpec]:
    if not names:
        return list(tasks)
    wanted = {str(name).strip() for name in names if str(name).strip()}
    return [task for task in tasks if task.name in wanted]


def run_gate_tests() -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT)
    command = [
        "python",
        "-m",
        "unittest",
        "tests.test_contract",
        "tests.test_formal_heavy_matrix",
        "tests.test_general_task_heavy_matrix",
        "tests.test_hybrid",
        "tests.test_supervisor",
        "tests.test_strategy_lock",
        "tests.test_t23_real_ab_runner",
        "-q",
    ]
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", env=env)


def validate_t2_generic(task: TaskSpec, workspace: Path) -> tuple[int, list[str], str]:
    spec = dict(task.quality_spec)
    notes: list[str] = []
    score = 0
    test_result = subprocess.run(
        ["python", "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tests_ok = test_result.returncode == 0
    if tests_ok:
        score += 70
    notes.append("unit tests passed" if tests_ok else "unit tests failed")

    context_path = workspace / str(spec["context_path"])
    artifact_format = "missing"
    if context_path.exists():
        artifact_format = context_path.suffix.lstrip(".") or "text"
        try:
            payload = json.loads(context_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            required_keys = [str(item) for item in spec.get("context_keys", [])]
            hits = sum(1 for key in required_keys if str(payload.get(key, "")).strip())
            score += int(round((hits / len(required_keys)) * 15)) if required_keys else 15
            notes.append(f"context keys present: {hits}/{len(required_keys)}")
        else:
            notes.append("context artifact is not valid JSON")
    else:
        notes.append("context artifact missing")

    notes_path = workspace / str(spec["notes_path"])
    if notes_path.exists():
        notes_text = notes_path.read_text(encoding="utf-8", errors="ignore")
        headings = [str(item) for item in spec.get("headings", [])]
        hits = sum(1 for heading in headings if heading in notes_text)
        score += int(round((hits / len(headings)) * 15)) if headings else 15
        notes.append(f"repair note headings: {hits}/{len(headings)}")
    else:
        notes.append("repair notes missing")
    return score, notes, artifact_format


def validate_task(task: TaskSpec, workspace: Path, output_text: str) -> tuple[int, list[str], str]:
    if task.validator == "t0":
        return base.validate_t0(task, output_text)
    if task.validator == "t1":
        return base.validate_t1(task, workspace)
    if task.validator == "t2_generic":
        return validate_t2_generic(task, workspace)
    if task.validator == "t3":
        return base.validate_t3(task, workspace)
    raise ValueError(f"Unsupported validator: {task.validator}")


def run_one(task: TaskSpec, arm: str, home: Path, scratch_root: Path, timeout_seconds: int) -> RunResult:
    run_dir = scratch_root / task.tier / task.name / arm
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace = run_dir / "workspace"
    base.write_workspace(workspace, task.workspace_files)
    run_input = base.build_prompt(task, workspace, arm)
    prompt = run_input.prompt
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"[start] {task.name} {arm}", flush=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["NO_COLOR"] = "1"
    command = [
        base.base.find_codex(),
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "--dangerously-bypass-approvals-and-sandbox",
        "--ephemeral",
        "--color",
        "never",
        "--output-last-message",
        str(run_dir / "last_message.txt"),
    ]
    if run_input.reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{run_input.reasoning_effort}"'])
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=timeout_seconds,
        )
        exit_code = result.returncode
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout_text = exc.stdout or ""
        stderr_text = (exc.stderr or "") + "\nTIMEOUT"
    elapsed = time.perf_counter() - started
    (run_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    output_text = (run_dir / "last_message.txt").read_text(encoding="utf-8") if (run_dir / "last_message.txt").exists() else ""
    quality_score, quality_notes, artifact_format = validate_task(task, workspace, output_text)
    print(f"[done] {task.name} {arm} exit={exit_code} elapsed={elapsed:.2f}s quality={quality_score}", flush=True)
    return RunResult(
        task_name=task.name,
        tier=task.tier,
        group=task.group,
        title=task.title,
        description=task.description,
        arm=arm,
        exit_code=exit_code,
        elapsed_seconds=elapsed,
        reported_total_tokens=base.base.parse_tokens(stderr_text),
        estimated_prompt_tokens=base.base.estimate_tokens(prompt),
        estimated_output_tokens=base.base.estimate_tokens(output_text),
        estimated_total_tokens=base.base.estimate_tokens(prompt) + base.base.estimate_tokens(output_text),
        quality_score=quality_score,
        quality_grade=base.quality_grade(quality_score),
        quality_notes=quality_notes,
        session_id=base.base.parse_session_id(stderr_text),
        artifact_format=artifact_format,
        routed_tier=run_input.tier,
        reasoning_effort=run_input.reasoning_effort,
        run_dir=str(run_dir),
        contract_family=task.contract_family,
        adapter_family=task.adapter_family,
        validator_type=task.validator_type,
        resumability_expected=task.resumability_expected,
        exactness_expected=task.exactness_expected,
        contract_hash=run_input.contract_hash,
        adapter_id=run_input.adapter_id,
        validator_kinds=list(run_input.validator_kinds),
        exactness_rule_count=run_input.exactness_rule_count,
        resumable=run_input.resumable,
        checkpointable=run_input.checkpointable,
    )


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def write_formal_report(summary: dict[str, object], report_path: Path) -> None:
    overall = dict(summary["overall"])
    tier_map = {str(row["tier"]): row for row in summary["tiers"]}
    lines = [
        "# Hybrid General-Task Heavy A/B Formal Report",
        "",
        "## Scope",
        "",
        "This report uses a heavy 4-tier x 3-group A/B matrix built from tasks whose semantic outputs are intentionally not ACL-X-centric.",
        "The task corpus covers generic policy extraction, bug review, code repair, incident and operations document rewrite, and machine-readable handoff packages in ordinary JSON or Markdown.",
        "The objective is to re-measure the current hybrid strategy on more general task semantics, with primary attention to token optimization, runtime optimization, and output quality preservation or improvement.",
        "",
        "## Run Metadata",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Run root: `{summary['run_root']}`",
        f"- Task count: `{summary['task_count']}`",
        f"- Gate tests passed: `{summary['gate_tests']['exit_code'] == 0}`",
        f"- Strategy lock clean: `{not summary['lock_mismatches']}`",
        f"- Release recommendation: `{'GO' if summary['release_ready'] else 'HOLD'}`",
        "",
        "## Overall Metrics",
        "",
        f"- Baseline total tokens: `{overall['baseline_total_tokens']}`",
        f"- Hybrid total tokens: `{overall['hybrid_total_tokens']}`",
        f"- Token optimization vs baseline: `{_fmt_pct(overall['token_optimization_pct'])}`",
        f"- Baseline total time: `{overall['baseline_total_seconds']:.2f}s`",
        f"- Hybrid total time: `{overall['hybrid_total_seconds']:.2f}s`",
        f"- Time optimization vs baseline: `{_fmt_pct(overall['time_optimization_pct'])}`",
        f"- Baseline average quality: `{overall['baseline_avg_quality']:.2f}`",
        f"- Hybrid average quality: `{overall['hybrid_avg_quality']:.2f}`",
        f"- Quality delta: `{overall['quality_delta']:.2f}`",
        "",
        "## Tier Aggregates",
        "",
        "| Tier | Tasks | Baseline Tokens | Hybrid Tokens | Token Opt | Baseline Time (s) | Hybrid Time (s) | Time Opt | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tier in ("t0", "t1", "t2", "t3"):
        row = tier_map[tier]
        agg = row["aggregate"]
        lines.append(
            "| {tier} | {count} | {bt} | {ht} | {tok} | {bs:.2f} | {hs:.2f} | {tim} | {bq:.2f} | {hq:.2f} | {qd:.2f} |".format(
                tier=tier,
                count=row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                tok=_fmt_pct(agg["token_optimization_pct"]),
                bs=agg["baseline_total_seconds"],
                hs=agg["hybrid_total_seconds"],
                tim=_fmt_pct(agg["time_optimization_pct"]),
                bq=agg["baseline_avg_quality"],
                hq=agg["hybrid_avg_quality"],
                qd=agg["quality_delta"],
            )
        )
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Resumability coverage: `{summary['coverage']['resumability']['covered_tasks']}/{summary['coverage']['resumability']['expected_tasks']}` tasks, `{_fmt_pct(summary['coverage']['resumability']['coverage_pct'])}`",
            f"- Exactness preservation coverage: `{summary['coverage']['exactness_preservation']['covered_tasks']}/{summary['coverage']['exactness_preservation']['expected_tasks']}` tasks, `{_fmt_pct(summary['coverage']['exactness_preservation']['coverage_pct'])}`",
            "",
            "## Per-Task Findings",
            "",
        ]
    )
    for row in summary["tasks"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        lines.extend(
            [
                f"### {row['tier']} G{row['group']} - {row['title']}",
                "",
                f"- Description: {row['description']}",
                f"- Contract family: `{row['contract_family']}`",
                f"- Adapter family: `{row['adapter_family']}`",
                f"- Validator type: `{row['validator_type']}`",
                f"- Baseline tokens: `{baseline['reported_total_tokens'] or baseline['estimated_total_tokens']}`",
                f"- Hybrid tokens: `{hybrid['reported_total_tokens'] or hybrid['estimated_total_tokens']}`",
                f"- Token optimization: `{_fmt_pct(row['token_optimization_pct'])}`",
                f"- Baseline time: `{baseline['elapsed_seconds']:.2f}s`",
                f"- Hybrid time: `{hybrid['elapsed_seconds']:.2f}s`",
                f"- Time optimization: `{_fmt_pct(row['time_optimization_pct'])}`",
                f"- Baseline quality: `{baseline['quality_score']}` ({baseline['quality_grade']})",
                f"- Hybrid quality: `{hybrid['quality_score']}` ({hybrid['quality_grade']})",
                f"- Quality delta: `{row['quality_delta']}`",
                f"- Routed tier: expected `{row['tier']}`, observed `{hybrid['routed_tier']}`",
                f"- Observed adapter id: `{hybrid['adapter_id']}`",
                f"- Baseline notes: {'; '.join(baseline['quality_notes'])}",
                f"- Hybrid notes: {'; '.join(hybrid['quality_notes'])}",
                "",
            ]
        )
    positive_quality = [row for row in summary["tasks"] if row["quality_delta"] > 0]
    positive_token = [row for row in summary["tasks"] if row["token_optimization_pct"] is not None and row["token_optimization_pct"] > 0]
    positive_time = [row for row in summary["tasks"] if row["time_optimization_pct"] is not None and row["time_optimization_pct"] > 0]
    lines.extend(
        [
            "## Interpretation",
            "",
            f"- Tasks with hybrid quality gains: `{len(positive_quality)}/{summary['task_count']}`",
            f"- Tasks with positive token optimization: `{len(positive_token)}/{summary['task_count']}`",
            f"- Tasks with positive time optimization: `{len(positive_time)}/{summary['task_count']}`",
            "- The result should be interpreted as evidence about bounded, validator-checkable general tasks, not as a guarantee for arbitrary open-ended work.",
            "- If t0 remains weak on token savings while preserving quality, that is consistent with fixed routing overhead on very small tasks rather than a failure of semantic generalization.",
            "- If t2 or t3 retain quality while improving tokens or time on generic repairs and looped documents, that is the strongest signal that the current hybrid design is no longer overfit to ACL-X-specific project surfaces.",
            "",
            "## Conclusion",
            "",
            (
                "Recommendation: GO for the bounded local general-task range covered by this report. The current hybrid strategy preserved or improved quality on average while staying within the validated task families in this matrix."
                if summary["release_ready"]
                else "Recommendation: HOLD. The current hybrid strategy still shows unresolved regressions in token usage, runtime, routing, or output quality within this generic heavy-task matrix."
            ),
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a heavy A/B matrix for generic non-ACLX task semantics.")
    parser.add_argument("--task", action="append", default=[], help="Optional task name filter. Repeat to select multiple tasks.")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Per-run Codex timeout in seconds.")
    args = parser.parse_args()

    tasks = select_tasks(build_tasks(), args.task)
    if not tasks:
        raise SystemExit("No tasks selected.")

    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_root = RUNS_ROOT / f"hybrid_general_task_heavy_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)

    lock_mismatches = base.base.verify_strategy_lock()
    gate_result = run_gate_tests()
    print(f"[gate] lock_mismatches={len(lock_mismatches)} tests_exit={gate_result.returncode}", flush=True)

    scratch_root = run_root / "artifacts"
    scratch_root.mkdir(parents=True, exist_ok=True)
    baseline_home = scratch_root / "CODEX_HOME_BASELINE"
    hybrid_home = scratch_root / "CODEX_HOME_HYBRID"
    hybrid_t0_home = scratch_root / "CODEX_HOME_HYBRID_T0"
    base.base.prepare_home(baseline_home, hybrid=False)
    base.base.prepare_home(hybrid_home, hybrid=True)
    base.base.prepare_home(
        hybrid_t0_home,
        hybrid=True,
        agents_text=base.T0_MINIMAL_AGENTS,
        copy_agents=False,
        copy_skills=False,
    )

    results: list[RunResult] = []
    for task in tasks:
        results.append(run_one(task, "baseline", baseline_home, scratch_root, args.timeout_seconds))
        active_hybrid_home = hybrid_t0_home if task.tier == "t0" else hybrid_home
        results.append(run_one(task, "hybrid", active_hybrid_home, scratch_root, args.timeout_seconds))

    summary = base.build_summary(
        run_id=run_id,
        gate_result=gate_result,
        lock_mismatches=lock_mismatches,
        task_specs=tasks,
        results=results,
        run_root=run_root,
        timeout_seconds=args.timeout_seconds,
    )
    summary["kind"] = "hybrid_general_task_heavy"
    summary["suite_scope"] = "generic_non_aclx_semantics"
    summary["task_corpus_note"] = "All task semantics and primary deliverables are intentionally generic and not centered on ACL-X-specific outputs."
    summary_path = run_root / f"hybrid_general_task_heavy_{run_id}.json"
    report_path = run_root / f"hybrid_general_task_heavy_{run_id}_formal_report.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    write_formal_report(summary, report_path)
    print(str(run_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
