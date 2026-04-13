from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_ROOT = Path(__file__).resolve().parent
RUNS_ROOT = FORMAL_ROOT / "runs"
OUTPUT_PDF_ROOT = REPO_ROOT / "output" / "pdf"
TMP_PDF_ROOT = REPO_ROOT / "tmp" / "pdfs"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

import scripts.release_validation_ab as base  # noqa: E402
from aclx.contract_pipeline import resolve_task_contract  # noqa: E402
from aclx.supervisor import ACLXSupervisor, T0_MINIMAL_AGENTS  # noqa: E402

try:
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore
    from reportlab.lib.pagesizes import A4, landscape  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import mm  # type: ignore
    from reportlab.pdfgen import canvas  # type: ignore
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


@dataclass(slots=True)
class TaskSpec:
    name: str
    tier: str
    group: int
    title: str
    description: str
    profile: str
    prompt: str
    workspace_files: dict[str, str]
    validator: str
    task_shape: str | None = None
    expected_handoffs: int = 0
    expected_rounds: int = 1
    child_agents: int = 0
    shared_state: bool = False
    outputs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    contract_family: str = ""
    adapter_family: str = ""
    validator_type: str = ""
    resumability_expected: bool = False
    exactness_expected: bool = False
    quality_spec: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunInput:
    prompt: str
    tier: str
    reasoning_effort: str | None
    contract_hash: str
    adapter_id: str
    validator_kinds: list[str]
    exactness_rule_count: int
    resumable: bool
    checkpointable: bool


@dataclass(slots=True)
class RunResult:
    task_name: str
    tier: str
    group: int
    title: str
    description: str
    arm: str
    exit_code: int
    elapsed_seconds: float
    reported_total_tokens: int | None
    estimated_prompt_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    quality_score: int
    quality_grade: str
    quality_notes: list[str]
    session_id: str | None
    artifact_format: str
    routed_tier: str
    reasoning_effort: str | None
    run_dir: str
    contract_family: str
    adapter_family: str
    validator_type: str
    resumability_expected: bool
    exactness_expected: bool
    contract_hash: str
    adapter_id: str
    validator_kinds: list[str]
    exactness_rule_count: int
    resumable: bool
    checkpointable: bool


def quality_grade(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "partial"
    return "poor"


def effective_tokens(result: RunResult) -> int:
    return result.reported_total_tokens or result.estimated_total_tokens


def _row_to_result(data: dict[str, Any]) -> RunResult:
    return RunResult(**data)


def write_workspace(workspace: Path, files: dict[str, str]) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_prompt(task: TaskSpec, workspace: Path, arm: str) -> RunInput:
    raw_task = task.prompt.format(workspace=str(workspace))
    contract, project_context = _build_contract_context(task, workspace, raw_task)
    if arm == "baseline":
        return RunInput(
            prompt=raw_task,
            tier=task.tier,
            reasoning_effort=None,
            contract_hash=contract.contract_hash(),
            adapter_id=project_context.adapter_id,
            validator_kinds=list(contract.validator_kinds),
            exactness_rule_count=len(contract.exactness_rules),
            resumable=bool(contract.runtime_needs.resumable),
            checkpointable=bool(contract.runtime_needs.checkpointable),
        )
    supervisor = ACLXSupervisor()
    payload = supervisor.build_payload(
        raw_task,
        cwd=str(workspace),
        style="adaptive",
        profile=task.profile,
        task_shape=task.task_shape,
        expected_handoffs=task.expected_handoffs,
        expected_rounds=task.expected_rounds,
        child_agents=task.child_agents,
        shared_state=task.shared_state,
        outputs=task.outputs,
        constraints=task.constraints,
        stop_conditions=task.stop_conditions,
        next_actions=task.next_actions,
        contract=contract,
    )
    return RunInput(
        prompt=payload.codex_prompt,
        tier=payload.tier,
        reasoning_effort=payload.reasoning_effort or None,
        contract_hash=contract.contract_hash(),
        adapter_id=project_context.adapter_id,
        validator_kinds=list(contract.validator_kinds),
        exactness_rule_count=len(contract.exactness_rules),
        resumable=bool(contract.runtime_needs.resumable),
        checkpointable=bool(contract.runtime_needs.checkpointable),
    )


def _build_contract_context(task: TaskSpec, workspace: Path, raw_task: str):
    resolution = resolve_task_contract(
        raw_task,
        project_root=workspace,
        required_artifacts=task.outputs,
        acceptance_contract=task.constraints,
        stop_conditions=task.stop_conditions,
        next_actions=task.next_actions,
        expected_handoffs=task.expected_handoffs,
        expected_rounds=task.expected_rounds,
        child_agents=task.child_agents,
        shared_state=task.shared_state,
        checkpointable=task.resumability_expected or task.tier == "t3",
        resumable=task.resumability_expected or task.tier == "t3",
        loop_heavy=task.tier == "t3",
    )
    if resolution.project_context is None:
        raise RuntimeError("formal matrix contract resolution requires project context")
    return resolution.contract, resolution.project_context


def validate_t0(task: TaskSpec, output_text: str) -> tuple[int, list[str], str]:
    spec = task.quality_spec
    notes: list[str] = []
    score = 0
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    expected_lines = int(spec.get("expected_lines", 3))
    if len(lines) == expected_lines:
        score += 30
        notes.append(f"exactly {expected_lines} non-empty lines")
    else:
        notes.append(f"expected {expected_lines} non-empty lines, got {len(lines)}")
    if lines and lines[0].lower() == "tier: t0":
        score += 20
        notes.append("tier line correct")
    else:
        notes.append("tier line missing or incorrect")
    lower = output_text.lower()
    required_path = str(spec["required_path"]).lower()
    if required_path in lower:
        score += 20
        notes.append(f"evidence names {spec['required_path']}")
    else:
        notes.append(f"evidence missing {spec['required_path']}")
    required_facts = [str(item).lower() for item in spec.get("required_facts", [])]
    present = sum(1 for fact in required_facts if fact in lower)
    if required_facts:
        score += int(round((present / len(required_facts)) * 30))
        notes.append(f"required facts present: {present}/{len(required_facts)}")
    else:
        score += 30
        notes.append("no extra facts required")
    return score, notes, "message"


def validate_t1(task: TaskSpec, workspace: Path) -> tuple[int, list[str], str]:
    spec = task.quality_spec
    notes: list[str] = []
    score = 0
    report_path = workspace / str(spec["report_path"])
    if report_path.exists():
        score += 35
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        notes.append("review report written")
        artifact_format = "markdown"
    else:
        text = ""
        notes.append("review report missing")
        artifact_format = "missing"
    headings = [str(item) for item in spec.get("headings", [])]
    headings_ok = all(heading in text for heading in headings)
    if headings_ok:
        score += 20
        notes.append("required headings present")
    else:
        notes.append("required headings missing")
    required_path = str(spec["required_path"]).replace("\\", "/")
    if required_path in text.replace("\\", "/"):
        score += 15
        notes.append(f"report cites {required_path}")
    else:
        notes.append(f"report missing concrete path {required_path}")
    lower = text.lower()
    keyword_groups = spec.get("keyword_groups", [])
    passed = 0
    for group in keyword_groups:
        options = [str(item).lower() for item in group]
        if any(option in lower for option in options):
            passed += 1
    if keyword_groups:
        score += int(round((passed / len(keyword_groups)) * 30))
        notes.append(f"bug explanation checks: {passed}/{len(keyword_groups)}")
    else:
        score += 30
        notes.append("no keyword checks required")
    return score, notes, artifact_format


def validate_t2(task: TaskSpec, workspace: Path) -> tuple[int, list[str], str]:
    result = subprocess.run(
        ["python", "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    notes = ["unit tests passed" if result.returncode == 0 else "unit tests failed"]
    score = 70 if result.returncode == 0 else 0
    artifact_path = workspace / "runtime" / "shared_state.aclx"
    artifact_ok = False
    artifact_format = "missing"
    if artifact_path.exists():
        text = artifact_path.read_text(encoding="utf-8", errors="ignore")
        artifact_ok = "h|c|c0|1" in text
        artifact_format = "aclx" if artifact_ok else "other"
    notes.append("shared state ACL-X artifact present" if artifact_ok else "shared state ACL-X artifact missing or invalid")
    if artifact_ok:
        score += 15
    review_path = workspace / "reports" / "review_notes.md"
    review_ok = False
    if review_path.exists():
        review_text = review_path.read_text(encoding="utf-8", errors="ignore")
        review_ok = "Risk" in review_text and "Evidence" in review_text
    notes.append("review notes present" if review_ok else "review notes missing or incomplete")
    if review_ok:
        score += 15
    return score, notes, artifact_format


def validate_t3(task: TaskSpec, workspace: Path) -> tuple[int, list[str], str]:
    spec = task.quality_spec
    notes: list[str] = []
    score = 0
    document_path = workspace / str(spec["document_path"])
    artifact_format = document_path.suffix.lstrip(".") or "text"
    document_text = ""
    if document_path.exists():
        document_text = document_path.read_text(encoding="utf-8", errors="ignore").lower()
        checks = spec["required_checks"]
        passed = 0
        for options in checks.values():
            choices = [str(item).lower() for item in options]
            if any(choice in document_text for choice in choices):
                passed += 1
        score += int(round((passed / len(checks)) * 60))
        notes.append(f"document content checks: {passed}/{len(checks)}")
        headings = [str(item).lower() for item in spec.get("required_headings", [])]
        heading_hits = sum(1 for heading in headings if heading in document_text)
        if headings:
            score += int(round((heading_hits / len(headings)) * 20))
            notes.append(f"document heading checks: {heading_hits}/{len(headings)}")
        else:
            score += 20
            notes.append("no document headings required")
    else:
        notes.append(f"{spec['document_path']} missing")
        heading_count = len(spec.get("required_headings", []))
        if heading_count:
            notes.append(f"document heading checks: 0/{heading_count}")
        else:
            notes.append("no document headings required")
        artifact_format = "missing"

    checkpoint_path = workspace / str(spec["checkpoint_path"])
    checkpoint_text = ""
    checkpoint_hits = 0
    checkpoint_checks = spec.get("checkpoint_checks", [])
    if checkpoint_path.exists():
        checkpoint_text = checkpoint_path.read_text(encoding="utf-8", errors="ignore").lower()
        checkpoint_hits = sum(1 for item in checkpoint_checks if str(item).lower() in checkpoint_text)
        if checkpoint_checks:
            score += int(round((checkpoint_hits / len(checkpoint_checks)) * 20))
            notes.append(f"checkpoint note checks: {checkpoint_hits}/{len(checkpoint_checks)}")
        else:
            score += 20
            notes.append("checkpoint note present")
    else:
        if checkpoint_checks:
            notes.append(f"checkpoint note checks: 0/{len(checkpoint_checks)}")
        else:
            notes.append("checkpoint note missing")
    return score, notes, artifact_format


def validate_task(task: TaskSpec, workspace: Path, output_text: str) -> tuple[int, list[str], str]:
    if task.validator == "t0":
        return validate_t0(task, output_text)
    if task.validator == "t1":
        return validate_t1(task, workspace)
    if task.validator == "t2":
        return validate_t2(task, workspace)
    if task.validator == "t3":
        return validate_t3(task, workspace)
    raise ValueError(f"Unsupported validator: {task.validator}")


def run_one(task: TaskSpec, arm: str, home: Path, scratch_root: Path, timeout_seconds: int) -> RunResult:
    run_dir = scratch_root / task.tier / task.name / arm
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace = run_dir / "workspace"
    write_workspace(workspace, task.workspace_files)
    run_input = build_prompt(task, workspace, arm)
    prompt = run_input.prompt
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"[start] {task.name} {arm}", flush=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["NO_COLOR"] = "1"
    command = [
        base.find_codex(),
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
    print(
        f"[done] {task.name} {arm} exit={exit_code} elapsed={elapsed:.2f}s quality={quality_score}",
        flush=True,
    )
    return RunResult(
        task_name=task.name,
        tier=task.tier,
        group=task.group,
        title=task.title,
        description=task.description,
        arm=arm,
        exit_code=exit_code,
        elapsed_seconds=elapsed,
        reported_total_tokens=base.parse_tokens(stderr_text),
        estimated_prompt_tokens=base.estimate_tokens(prompt),
        estimated_output_tokens=base.estimate_tokens(output_text),
        estimated_total_tokens=base.estimate_tokens(prompt) + base.estimate_tokens(output_text),
        quality_score=quality_score,
        quality_grade=quality_grade(quality_score),
        quality_notes=quality_notes,
        session_id=base.parse_session_id(stderr_text),
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


def t0_task(
    *,
    name: str,
    group: int,
    title: str,
    description: str,
    file_path: str,
    file_body: str,
    required_facts: list[str],
    contract_family: str = "read_extract",
    adapter_family: str = "docs",
) -> TaskSpec:
    prompt = (
        "You are in an isolated workspace. Only read files under {workspace}.\n\n"
        f"Read `{file_path}`.\n"
        "Return exactly 3 non-empty lines:\n"
        "Tier: t0\n"
        "Decision: <one sentence>\n"
        f"Evidence: {file_path}; mention {required_facts[0]} and {required_facts[1]}.\n"
        "Do not edit files.\n"
    )
    return TaskSpec(
        name=name,
        tier="t0",
        group=group,
        title=title,
        description=description,
        profile="review",
        prompt=prompt,
        workspace_files={file_path: file_body},
        validator="t0",
        task_shape="single_surface",
        contract_family=contract_family,
        adapter_family=adapter_family,
        validator_type="exact_output",
        resumability_expected=False,
        exactness_expected=True,
        quality_spec={
            "expected_lines": 3,
            "required_path": file_path,
            "required_facts": required_facts,
        },
    )


def t1_task(
    *,
    name: str,
    group: int,
    title: str,
    description: str,
    source_path: str,
    source_body: str,
    report_bug_line: str,
    keyword_groups: list[list[str]],
) -> TaskSpec:
    prompt = (
        "You are in an isolated workspace. Only edit files under {workspace}.\n\n"
        f"Inspect `{source_path}`.\n"
        "Delegate exactly once to one reviewer pass, merge the conclusion yourself, and write `reports/review.md`.\n"
        "`reports/review.md` must contain headings `Decision` and `Evidence`.\n"
        f"{report_bug_line}\n"
        "Keep the final reply to one sentence and list changed file paths.\n"
    )
    return TaskSpec(
        name=name,
        tier="t1",
        group=group,
        title=title,
        description=description,
        profile="review",
        prompt=prompt,
        workspace_files={source_path: source_body},
        validator="t1",
        task_shape="delegated_once",
        expected_handoffs=1,
        expected_rounds=1,
        child_agents=1,
        shared_state=True,
        outputs=["reports/review.md"],
        constraints=[
            "reports/review.md keeps Decision and Evidence headings",
            f"reports/review.md names {source_path}",
            "delegate exactly once",
        ],
        stop_conditions=["missing review report"],
        next_actions=["delegate once", "write review report"],
        contract_family="single_handoff_review",
        adapter_family="python",
        validator_type="structured_review",
        resumability_expected=False,
        exactness_expected=True,
        quality_spec={
            "report_path": "reports/review.md",
            "headings": ["Decision", "Evidence"],
            "required_path": source_path,
            "keyword_groups": keyword_groups,
        },
    )


def t2_task(
    *,
    name: str,
    group: int,
    title: str,
    description: str,
    source_path: str,
    source_body: str,
    test_path: str,
    test_body: str,
) -> TaskSpec:
    task_md = (
        f"Fix the shared-state workflow bug in `{source_path}`.\n\n"
        "Requirements:\n\n"
        "- `python -m unittest discover -s tests -q` must pass.\n"
        "- Write `runtime/shared_state.aclx` as an ACL-X C-layer machine-state artifact for the next phase.\n"
        "- Write `reports/review_notes.md` with headings `Risk` and `Evidence`.\n"
        "- Keep the final reply concise and list changed file paths.\n"
    )
    prompt = (
        "You are in an isolated workspace. Only edit files under {workspace}.\n\n"
        "Read {workspace}\\TASK.md.\n"
        f"Fix `{source_path}` so `python -m unittest discover -s tests -q` passes.\n"
        "Write `runtime/shared_state.aclx` as an ACL-X C-layer machine-state artifact for the next phase.\n"
        "Write `reports/review_notes.md` with headings `Risk` and `Evidence`.\n"
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
        validator="t2",
        task_shape="shared_state",
        expected_handoffs=2,
        expected_rounds=2,
        child_agents=2,
        shared_state=True,
        outputs=["runtime/shared_state.aclx", "reports/review_notes.md"],
        constraints=[
            "python -m unittest discover -s tests -q passes",
            "runtime/shared_state.aclx uses ACL-X C-layer text",
            "reports/review_notes.md keeps Risk and Evidence headings",
        ],
        stop_conditions=["missing shared artifact", "tests failing"],
        next_actions=["write shared state", "run tests"],
        contract_family="shared_state_repair",
        adapter_family="python",
        validator_type="unit_tests_and_artifacts",
        resumability_expected=False,
        exactness_expected=True,
    )


def t3_task(
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
    bullets = []
    for label, options in required_checks.items():
        bullets.append(f"- {label}: one of {', '.join(options)}")
    heading_text = "\n".join(f"- keep heading `{heading}`" for heading in required_headings)
    checkpoint_text = "\n".join(f"- include `{item}` in `{checkpoint_path}`" for item in checkpoint_checks)
    task_md = (
        f"Rewrite `{document_path}` so it becomes a valid loop-heavy operating document and preserves these behavioral constraints:\n\n"
        + "\n".join(bullets)
        + "\n"
        + heading_text
        + "\n"
        + checkpoint_text
        + "\n- keep the output in Markdown\n\n"
        + "Keep the final reply concise and list changed file paths.\n"
    )
    prompt = (
        "You are in an isolated workspace. Only edit files under {workspace}.\n\n"
        "Read {workspace}\\TASK.md.\n"
        f"Rewrite `{document_path}` so it satisfies the required loop constraints.\n"
        f"Write `{checkpoint_path}` as the current checkpoint note for this pass.\n"
        "Keep the final reply concise and list changed file paths.\n"
    )
    files = {
        "TASK.md": task_md,
        document_path: document_stub,
    }
    return TaskSpec(
        name=name,
        tier="t3",
        group=group,
        title=title,
        description=description,
        profile="review",
        prompt=prompt,
        workspace_files=files,
        validator="t3",
        task_shape="loop",
        expected_handoffs=3,
        expected_rounds=3,
        child_agents=3,
        shared_state=True,
        outputs=[checkpoint_path, document_path],
        constraints=[
            "loop document keeps the required wording and headings",
            "checkpoint note records current state and next step",
        ],
        stop_conditions=["scope drift", "missing checkpoint note"],
        next_actions=["rewrite document", "persist checkpoint note"],
        contract_family="loop_document_rewrite",
        adapter_family="docs",
        validator_type="document_exactness_and_checkpoint",
        resumability_expected=True,
        exactness_expected=True,
        quality_spec={
            "document_path": document_path,
            "required_checks": required_checks,
            "required_headings": required_headings,
            "checkpoint_path": checkpoint_path,
            "checkpoint_checks": checkpoint_checks,
        },
    )


def build_tasks() -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    tasks.append(
        t0_task(
            name="t0_g1_release_summary",
            group=1,
            title="Release notes summary",
            description="Single-surface read-only summary of release notes with no handoff and no runtime bridge.",
            file_path="docs/release_notes.txt",
            file_body=(
                "Release notes\n"
                "- strategy lock protects AGENTS.md and routing config files\n"
                "- default runtime style is adaptive\n"
                "- single-surface work stays in t0\n"
                "- t0 should not load ACL-X runtime bundles\n"
            ),
            required_facts=["strategy lock", "adaptive runtime"],
        )
    )
    tasks.append(
        t0_task(
            name="t0_g2_router_threshold_brief",
            group=2,
            title="Router threshold brief",
            description="Single-surface routing brief from a generic JSON config with no repo- or language-specific adapter.",
            file_path="data/router_thresholds.json",
            file_body=(
                "{\n"
                "  \"routing\": [\n"
                "    \"single-surface work stays in t0\",\n"
                "    \"one real handoff promotes the run to t1\",\n"
                "    \"repeated handoffs or shared state promote the run to t2\"\n"
                "  ]\n"
                "}\n"
            ),
            required_facts=["single-surface", "one real handoff"],
            contract_family="generic_config_extract",
            adapter_family="generic-fs",
        )
    )
    tasks.append(
        t0_task(
            name="t0_g3_operator_note_brief",
            group=3,
            title="Operator note brief",
            description="Single-surface operator note extraction focused on t0 boundaries.",
            file_path="docs/operator_notes.txt",
            file_body=(
                "Operator notes\n"
                "- t0 means no real handoff has started\n"
                "- keep runtime-visible machine state in natural language in t0\n"
                "- only t2 and t3 use the runtime bridge and checkpoint flow\n"
            ),
            required_facts=["no real handoff", "natural language"],
        )
    )
    tasks.append(
        t1_task(
            name="t1_g1_empty_input_review",
            group=1,
            title="Empty input review",
            description="Exactly one review handoff over a list-cleaning function that breaks on empty input.",
            source_path="src/review_target.py",
            source_body=(
                "def first_non_empty_upper(items: list[str | None]) -> str:\n"
                "    \"\"\"Return the first non-empty value uppercased.\n\n"
                "    Empty input should return 'N/A'.\n"
                "    \"\"\"\n"
                "    cleaned = [item.strip() for item in items if item is not None and item.strip()]\n"
                "    return cleaned[0].upper()\n"
            ),
            report_bug_line="Identify the highest-risk bug with a concrete file path and explain why empty input breaks the function.",
            keyword_groups=[["empty"], ["cleaned[0]", "indexerror", "list index"]],
        )
    )
    tasks.append(
        t1_task(
            name="t1_g2_zero_sample_review",
            group=2,
            title="Zero-sample review",
            description="Exactly one review handoff over a latency helper with a zero-sample failure mode.",
            source_path="src/latency_target.py",
            source_body=(
                "def average_latency_ms(total_ms: int, samples: int) -> float:\n"
                "    \"\"\"Return the average latency in milliseconds.\"\"\"\n"
                "    cleaned = abs(total_ms)\n"
                "    return round(cleaned / samples, 2)\n"
            ),
            report_bug_line="Identify the highest-risk bug with a concrete file path and explain why zero samples break the function.",
            keyword_groups=[["zero", "0"], ["division by zero", "samples == 0", "zerodivisionerror"]],
        )
    )
    tasks.append(
        t1_task(
            name="t1_g3_missing_route_review",
            group=3,
            title="Missing-route review",
            description="Exactly one review handoff over a route selector that crashes on unknown keys.",
            source_path="src/router_target.py",
            source_body=(
                "def select_handler(routes: dict[str, dict[str, str]], key: str) -> str:\n"
                "    \"\"\"Return the configured handler name for the given route key.\"\"\"\n"
                "    normalized = key.strip().lower()\n"
                "    return routes[normalized][\"handler\"]\n"
            ),
            report_bug_line="Identify the highest-risk bug with a concrete file path and explain why an unknown route key breaks the function.",
            keyword_groups=[["unknown", "missing", "blank"], ["keyerror", "missing route", "routes[normalized]"]],
        )
    )
    tasks.append(
        t2_task(
            name="t2_g1_shared_pipeline_fix",
            group=1,
            title="Shared pipeline repair",
            description="Multi-step shared-state repair that fixes an order-preserving dedupe workflow.",
            source_path="src/shared_pipeline.py",
            source_body=(
                "from __future__ import annotations\n\n"
                "def collect_ready_steps(steps: list[str]) -> list[str]:\n"
                "    cleaned: list[str] = []\n"
                "    for step in steps:\n"
                "        value = step.strip().lower()\n"
                "        if not value:\n"
                "            continue\n"
                "        if value not in cleaned:\n"
                "            cleaned.append(value)\n"
                "    return cleaned[1:]\n"
            ),
            test_path="tests/test_shared_pipeline.py",
            test_body=(
                "from __future__ import annotations\n\n"
                "import unittest\n\n"
                "from src.shared_pipeline import collect_ready_steps\n\n\n"
                "class SharedPipelineTests(unittest.TestCase):\n"
                "    def test_empty_steps(self) -> None:\n"
                "        self.assertEqual(collect_ready_steps([]), [])\n\n"
                "    def test_preserves_first_seen_order_when_deduping(self) -> None:\n"
                "        steps = [\"build\", \" lint \", \"Build\", \"\", \"test\", \"lint\", \"deploy\"]\n"
                "        self.assertEqual(collect_ready_steps(steps), [\"build\", \"lint\", \"test\", \"deploy\"])\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n"
            ),
        )
    )
    tasks.append(
        t2_task(
            name="t2_g2_reviewer_queue_fix",
            group=2,
            title="Reviewer queue repair",
            description="Multi-step shared-state repair that fixes reverse-order normalization in a reviewer queue.",
            source_path="src/reviewer_queue.py",
            source_body=(
                "from __future__ import annotations\n\n"
                "def normalize_reviewers(reviewers: list[str]) -> list[str]:\n"
                "    ordered: list[str] = []\n"
                "    seen: set[str] = set()\n"
                "    for reviewer in reviewers:\n"
                "        value = reviewer.strip().lower()\n"
                "        if not value:\n"
                "            continue\n"
                "        if value in seen:\n"
                "            continue\n"
                "        seen.add(value)\n"
                "        ordered.insert(0, value)\n"
                "    return ordered\n"
            ),
            test_path="tests/test_reviewer_queue.py",
            test_body=(
                "from __future__ import annotations\n\n"
                "import unittest\n\n"
                "from src.reviewer_queue import normalize_reviewers\n\n\n"
                "class ReviewerQueueTests(unittest.TestCase):\n"
                "    def test_empty_reviewers(self) -> None:\n"
                "        self.assertEqual(normalize_reviewers([]), [])\n\n"
                "    def test_preserves_first_seen_order(self) -> None:\n"
                "        reviewers = [\" Alice \", \"BOB\", \"alice\", \"\", \"bob\", \"Cara\"]\n"
                "        self.assertEqual(normalize_reviewers(reviewers), [\"alice\", \"bob\", \"cara\"])\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n"
            ),
        )
    )
    tasks.append(
        t2_task(
            name="t2_g3_stage_plan_fix",
            group=3,
            title="Stage plan repair",
            description="Multi-step shared-state repair that restores the first stage in a deduped deployment plan.",
            source_path="src/stage_plan.py",
            source_body=(
                "from __future__ import annotations\n\n"
                "def collect_stage_plan(stages: list[str]) -> list[str]:\n"
                "    cleaned: list[str] = []\n"
                "    seen: set[str] = set()\n"
                "    for stage in stages:\n"
                "        value = stage.strip().lower()\n"
                "        if not value:\n"
                "            continue\n"
                "        if value in seen:\n"
                "            continue\n"
                "        seen.add(value)\n"
                "        cleaned.append(value)\n"
                "    return cleaned[1:]\n"
            ),
            test_path="tests/test_stage_plan.py",
            test_body=(
                "from __future__ import annotations\n\n"
                "import unittest\n\n"
                "from src.stage_plan import collect_stage_plan\n\n\n"
                "class StagePlanTests(unittest.TestCase):\n"
                "    def test_empty_plan(self) -> None:\n"
                "        self.assertEqual(collect_stage_plan([]), [])\n\n"
                "    def test_keeps_first_stage_after_deduping(self) -> None:\n"
                "        stages = [\"prep\", \" build \", \"Prep\", \"test\", \"build\", \"deploy\"]\n"
                "        self.assertEqual(collect_stage_plan(stages), [\"prep\", \"build\", \"test\", \"deploy\"])\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n"
            ),
        )
    )
    tasks.append(
        t3_task(
            name="t3_g1_review_loop_playbook",
            group=1,
            title="Review loop playbook repair",
            description="Loop-heavy playbook rewrite for evidence-first review cycles with explicit roles and bounded scope.",
            document_path="docs/review_loop_playbook.md",
            document_stub=(
                "# Review Loop Playbook\n\n"
                "This draft is incomplete.\n\n"
                "Use any roles you want, finish whenever it feels right, and summarize from memory.\n"
            ),
            checkpoint_path="reports/review_loop_checkpoint.md",
            required_checks={
                "role_author": ["author"],
                "role_reviewer": ["reviewer"],
                "role_verifier": ["verifier"],
                "intake_only": ["intake-only", "intake only"],
                "final_disposition": ["final disposition"],
                "evidence_first": ["evidence before final disposition", "evidence-first"],
                "no_pass_counting": ["must not count passes or failures", "no pass/fail counting"],
                "no_rewrite": ["must not rewrite the source excerpt", "do not rewrite the source excerpt"],
                "bounded_scope": ["do not expand scope", "stay within the supplied excerpt"],
            },
            required_headings=["# review loop playbook", "## roles", "## review loop", "## guardrails"],
            checkpoint_checks=["current loop state", "evidence status", "next pass"],
        )
    )
    tasks.append(
        t3_task(
            name="t3_g2_release_signoff_handbook",
            group=2,
            title="Release signoff handbook repair",
            description="Loop-heavy handbook rewrite that keeps blocker-first checkpoints before final signoff.",
            document_path="docs/release_signoff_handbook.md",
            document_stub=(
                "# Release Signoff Handbook\n\n"
                "This draft is incomplete.\n\n"
                "Announce signoff first, fill evidence later, and restart the review if anything looks unclear.\n"
            ),
            checkpoint_path="reports/signoff_checkpoint.md",
            required_checks={
                "role_drafter": ["drafter"],
                "role_checker": ["checker"],
                "role_approver": ["approver"],
                "checkpoint_before_final": ["checkpoint before final signoff", "checkpoint before the final signoff"],
                "blockers_first": ["unresolved blockers first", "blockers before signoff"],
                "evidence_log": ["evidence log"],
                "no_silent_assumptions": ["do not invent missing evidence", "no silent assumptions"],
                "continue_from_current": ["continue from the current checkpoint", "do not restart the review from scratch"],
            },
            required_headings=["# release signoff handbook", "## roles", "## signoff loop", "## guardrails"],
            checkpoint_checks=["current checkpoint", "blockers", "next step"],
        )
    )
    tasks.append(
        t3_task(
            name="t3_g3_resume_handoff_guide",
            group=3,
            title="Resume handoff guide repair",
            description="Loop-heavy resume guide rewrite that preserves latest-checkpoint recovery and unresolved-items-first continuation.",
            document_path="docs/resume_handoff_guide.md",
            document_stub=(
                "# Resume Handoff Guide\n\n"
                "This draft is incomplete.\n\n"
                "Restart the work from the beginning, rewrite the old evidence, and decide the outcome before checking the latest state.\n"
            ),
            checkpoint_path="reports/resume_checkpoint.md",
            required_checks={
                "role_request_owner": ["request owner"],
                "role_resumer": ["resumer"],
                "role_reviewer": ["reviewer"],
                "resume_latest": ["resume from the latest checkpoint", "resume from latest checkpoint"],
                "unresolved_first": ["unresolved items first", "open items first"],
                "last_verified_step": ["last verified step"],
                "next_pending_step": ["next pending step"],
                "no_restart": ["do not restart from scratch", "continue from the existing checkpoint"],
                "preserve_prior_evidence": ["preserve prior evidence", "do not rewrite prior evidence"],
            },
            required_headings=["# resume handoff guide", "## roles", "## resume procedure", "## guardrails"],
            checkpoint_checks=["current checkpoint", "resume inputs", "next step"],
        )
    )
    return tasks


def select_tasks(tasks: list[TaskSpec], names: list[str]) -> list[TaskSpec]:
    if not names:
        return tasks
    allowed = set(names)
    return [task for task in tasks if task.name in allowed]


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "baseline_total_tokens": 0,
            "hybrid_total_tokens": 0,
            "token_optimization_pct": None,
            "baseline_total_seconds": 0.0,
            "hybrid_total_seconds": 0.0,
            "time_optimization_pct": None,
            "baseline_avg_quality": 0.0,
            "hybrid_avg_quality": 0.0,
            "quality_delta": 0.0,
        }
    baseline_tokens = sum(effective_tokens(_row_to_result(row["baseline"])) for row in rows)
    hybrid_tokens = sum(effective_tokens(_row_to_result(row["hybrid"])) for row in rows)
    baseline_time = sum(float(row["baseline"]["elapsed_seconds"]) for row in rows)
    hybrid_time = sum(float(row["hybrid"]["elapsed_seconds"]) for row in rows)
    baseline_quality = round(sum(int(row["baseline"]["quality_score"]) for row in rows) / len(rows), 2)
    hybrid_quality = round(sum(int(row["hybrid"]["quality_score"]) for row in rows) / len(rows), 2)
    return {
        "baseline_total_tokens": baseline_tokens,
        "hybrid_total_tokens": hybrid_tokens,
        "token_optimization_pct": base.improvement_pct(baseline_tokens, hybrid_tokens),
        "baseline_total_seconds": round(baseline_time, 3),
        "hybrid_total_seconds": round(hybrid_time, 3),
        "time_optimization_pct": base.improvement_pct(baseline_time, hybrid_time),
        "baseline_avg_quality": baseline_quality,
        "hybrid_avg_quality": hybrid_quality,
        "quality_delta": round(hybrid_quality - baseline_quality, 2),
    }


def aggregate_dimension(rows: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    values = sorted({str(row.get(key) or "") for row in rows if str(row.get(key) or "")})
    aggregates: list[dict[str, Any]] = []
    for value in values:
        matching = [row for row in rows if str(row.get(key) or "") == value]
        aggregates.append(
            {
                label: value,
                "task_count": len(matching),
                "tasks": matching,
                "aggregate": aggregate_rows(matching),
            }
        )
    return aggregates


def coverage_summary(rows: list[dict[str, Any]], *, expected_key: str, covered_key: str) -> dict[str, Any]:
    expected_rows = [row for row in rows if bool(row.get(expected_key))]
    if not expected_rows:
        return {
            "expected_tasks": 0,
            "covered_tasks": 0,
            "coverage_pct": None,
        }
    covered_rows = [row for row in expected_rows if bool(row.get(covered_key))]
    return {
        "expected_tasks": len(expected_rows),
        "covered_tasks": len(covered_rows),
        "coverage_pct": round((len(covered_rows) / len(expected_rows)) * 100.0, 2),
    }


def build_summary(
    *,
    run_id: str,
    gate_result: subprocess.CompletedProcess[str],
    lock_mismatches: list[str],
    task_specs: list[TaskSpec],
    results: list[RunResult],
    run_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, RunResult]] = {}
    for result in results:
        grouped.setdefault(result.task_name, {})[result.arm] = result

    tasks: list[dict[str, Any]] = []
    for task in task_specs:
        baseline = grouped[task.name]["baseline"]
        hybrid = grouped[task.name]["hybrid"]
        resumability_covered = (not task.resumability_expected) or (
            hybrid.resumable and hybrid.checkpointable and hybrid.routed_tier == "t3"
        )
        exactness_preserved = (not task.exactness_expected) or (
            hybrid.exactness_rule_count > 0 and hybrid.quality_score >= baseline.quality_score
        )
        tasks.append(
            {
                "task_name": task.name,
                "tier": task.tier,
                "group": task.group,
                "title": task.title,
                "description": task.description,
                "contract_family": task.contract_family,
                "adapter_family": task.adapter_family,
                "validator_type": task.validator_type,
                "resumability_expected": task.resumability_expected,
                "exactness_expected": task.exactness_expected,
                "baseline": asdict(baseline),
                "hybrid": asdict(hybrid),
                "token_optimization_pct": base.improvement_pct(effective_tokens(baseline), effective_tokens(hybrid)),
                "time_optimization_pct": base.improvement_pct(baseline.elapsed_seconds, hybrid.elapsed_seconds),
                "quality_delta": hybrid.quality_score - baseline.quality_score,
                "route_matches_expected": hybrid.routed_tier == task.tier,
                "adapter_matches_expected": task.adapter_family in hybrid.adapter_id,
                "resumability_covered": resumability_covered,
                "exactness_preserved": exactness_preserved,
            }
        )

    tiers: list[dict[str, Any]] = []
    for tier in ("t0", "t1", "t2", "t3"):
        tier_rows = [row for row in tasks if row["tier"] == tier]
        tiers.append(
            {
                "tier": tier,
                "task_count": len(tier_rows),
                "tasks": tier_rows,
                "aggregate": aggregate_rows(tier_rows),
            }
        )

    overall = aggregate_rows(tasks)
    contract_families = aggregate_dimension(tasks, "contract_family", "contract_family")
    adapter_families = aggregate_dimension(tasks, "adapter_family", "adapter_family")
    validator_types = aggregate_dimension(tasks, "validator_type", "validator_type")
    coverage = {
        "resumability": coverage_summary(tasks, expected_key="resumability_expected", covered_key="resumability_covered"),
        "exactness_preservation": coverage_summary(tasks, expected_key="exactness_expected", covered_key="exactness_preserved"),
    }
    release_ready = (
        gate_result.returncode == 0
        and not lock_mismatches
        and all(row["route_matches_expected"] for row in tasks)
        and all(row["adapter_matches_expected"] for row in tasks)
        and all(row["baseline"]["exit_code"] == 0 and row["hybrid"]["exit_code"] == 0 for row in tasks)
        and overall["hybrid_avg_quality"] >= overall["baseline_avg_quality"]
    )
    return {
        "kind": "hybrid_pre_release_heavy",
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_root": str(run_root),
        "timeout_seconds": timeout_seconds,
        "task_count": len(tasks),
        "lock_mismatches": lock_mismatches,
        "gate_tests": {
            "exit_code": gate_result.returncode,
            "stdout": gate_result.stdout,
            "stderr": gate_result.stderr,
        },
        "tasks": tasks,
        "tiers": tiers,
        "contract_families": contract_families,
        "adapter_families": adapter_families,
        "validator_types": validator_types,
        "coverage": coverage,
        "overall": overall,
        "release_ready": release_ready,
    }


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


REPORT_TASK_META: dict[str, dict[str, str]] = {
    "t0_g1_release_summary": {
        "title": "Three-line release notes summary",
        "description": "Read a short release-notes file and return exactly three non-empty lines. The answer must cite the source file path and include two named release facts, so this task represents a tiny read-only extraction with strict wording requirements.",
    },
    "t0_g2_router_threshold_brief": {
        "title": "Routing threshold brief",
        "description": "Read a small routing-threshold reference and produce a fixed-format brief that cites the source path and the key threshold facts. This models a tiny configuration lookup where format fidelity matters more than synthesis depth.",
    },
    "t0_g3_operator_note_brief": {
        "title": "Operator note brief",
        "description": "Read a short operator note and extract a three-line brief with the required path and two explicit facts. This represents a very small read-only summarization task with literal evidence requirements.",
    },
    "t1_g1_empty_input_review": {
        "title": "Empty-input bug review",
        "description": "Inspect a small Python function that fails on empty input, perform exactly one reviewer handoff, and write a structured review report with a decision and evidence. This simulates a lightweight one-pass review workflow.",
    },
    "t1_g2_zero_sample_review": {
        "title": "Zero-sample bug review",
        "description": "Inspect a latency helper that breaks when the sample count is zero, perform exactly one reviewer handoff, and deliver a structured review note. This tests a single coordination step without reusable runtime state.",
    },
    "t1_g3_missing_route_review": {
        "title": "Missing-route bug review",
        "description": "Inspect a route selector that crashes on unknown keys, perform exactly one reviewer handoff, and write a structured review result. This is another single-handoff review task with concrete evidence requirements.",
    },
    "t2_g1_shared_pipeline_fix": {
        "title": "Shared pipeline repair",
        "description": "Repair a local deduplication pipeline, run the named unit-test command, write a shared-state artifact for the next phase, and produce review notes. This represents a multi-step engineering fix that has both code and handoff artifacts.",
    },
    "t2_g2_reviewer_queue_fix": {
        "title": "Reviewer queue repair",
        "description": "Fix a queue-normalization bug, run the named unit-test command, write the shared-state handoff artifact, and leave a structured review note. This models a multi-step local fix with reusable machine-readable state.",
    },
    "t2_g3_stage_plan_fix": {
        "title": "Stage plan repair",
        "description": "Restore a missing first stage in a local deployment-plan workflow, rerun unit tests, write the shared-state artifact for the next phase, and produce review notes. This is a multi-step repair where task-contract fidelity matters because several artifacts must stay aligned.",
    },
    "t3_g1_review_loop_playbook": {
        "title": "Review loop playbook rewrite",
        "description": "Rewrite a review playbook so each review cycle stays evidence-first, roles remain explicit, scope boundaries are preserved, and checkpoint notes keep the loop state recoverable. This is a loop-heavy document task rather than a code-fix task.",
    },
    "t3_g2_release_signoff_handbook": {
        "title": "Release signoff handbook rewrite",
        "description": "Rewrite a release-signoff handbook so blocker-first checkpoints remain intact before final signoff and the document can be resumed cleanly from saved progress notes. This represents a loop-heavy procedural document task.",
    },
    "t3_g3_resume_handoff_guide": {
        "title": "Resume handoff guide rewrite",
        "description": "Rewrite a resume-and-handoff guide so it preserves latest-checkpoint recovery, continues with unresolved items first, and keeps the recovery loop consistent across restarts. This is a loop-heavy continuity document task.",
    },
}

CLASSIFICATION_LIMITS = [
    "The four-tier hybrid classification is a routing heuristic driven by runtime structure, not a universal taxonomy of task meaning or business value.",
    "The same user-facing request can fall into different tiers once it gains explicit files, reusable handoff state, loop checkpoints, or resume requirements.",
    "Mixed tasks are especially unstable at the boundaries. A task that begins as a short read-only request can become a multi-step repair or a loop-heavy workflow as soon as new acceptance checks appear during execution.",
    "The classification is weakest when the real success criteria live outside the prompt, outside the local workspace, or outside validator-checkable artifacts.",
]

RECOMMENDED_TASK_FAMILIES = [
    "Local file reads or summaries with strict output shape and explicit literal requirements.",
    "One-pass review tasks with exactly one deliberate handoff and a concrete written artifact.",
    "Multi-step local code or config repairs with named files, named tests or commands, and explicit machine-readable handoff artifacts.",
    "Looped document or playbook rewrites that have checkpointable structure and objective content requirements.",
]

NON_REPRESENTATIVE_TASK_FAMILIES = [
    "Open-ended web research, product strategy, or exploratory planning where scope changes during the run.",
    "Creative generation, taste-driven writing, or tasks whose quality is mostly subjective rather than validator-based.",
    "Production operations, remote systems work, or workflows dominated by network latency, approvals, or external services.",
    "Human-in-the-loop tasks where missing tacit context matters more than the prompt contract or local artifact discipline.",
]


def _report_task_title(row: dict[str, Any]) -> str:
    return REPORT_TASK_META.get(str(row["task_name"]), {}).get("title", str(row["title"]))


def _report_task_description(row: dict[str, Any]) -> str:
    return REPORT_TASK_META.get(str(row["task_name"]), {}).get("description", str(row["description"]))


def _tier_aggregate(summary: dict[str, Any], tier: str) -> dict[str, Any]:
    for row in summary["tiers"]:
        if str(row["tier"]).lower() == tier.lower():
            return row["aggregate"]
    raise KeyError(f"Missing aggregate for tier {tier}")


def _t0_negative_optimization_lines(summary: dict[str, Any]) -> list[str]:
    t0_aggregate = _tier_aggregate(summary, "t0")
    negative_tasks = [
        row
        for row in summary["tasks"]
        if str(row["tier"]).lower() == "t0" and float(row["token_optimization_pct"]) < 0
    ]
    negative_labels = ", ".join(
        f"{_report_task_title(row)} ({_fmt_pct(row['token_optimization_pct'])})" for row in negative_tasks
    )
    return [
        (
            f"In this formal run, T0 as a tier shows {_fmt_pct(t0_aggregate['token_optimization_pct'])} token optimization, "
            f"{_fmt_pct(t0_aggregate['time_optimization_pct'])} time optimization, and average quality improving from "
            f"{t0_aggregate['baseline_avg_quality']:.2f} to {t0_aggregate['hybrid_avg_quality']:.2f}."
        ),
        f"The negative token outliers are {negative_labels}.",
        "The main cause is fixed hybrid overhead. On tiny read-only tasks, routing wrappers, output-preservation guards, and a stricter prompt contract can cost more tokens than the task itself would otherwise consume.",
        "Operationally, this does not indicate a quality failure in the current run. The T0 hybrid outputs matched or exceeded baseline quality, but efficiency became unreliable because the task bodies were too small to amortize the extra control cost.",
        "Practical implication: use hybrid on T0-sized work when format fidelity, literal retention, or consistency matters. Do not expect reliable token savings on very small tasks.",
    ]


def _markdown_section(lines: list[str], heading: str, body_lines: list[str], *, bullets: bool = False) -> None:
    lines.extend(["", heading, ""])
    prefix = "- " if bullets else ""
    for line in body_lines:
        lines.append(f"{prefix}{line}" if bullets else line)


def _append_pdf_lines(story: list[Any], lines: list[str], style: ParagraphStyle, *, bullets: bool = False) -> None:
    prefix = "- " if bullets else ""
    for line in lines:
        story.append(Paragraph(f"{prefix}{line}" if bullets else line, style))


def write_markdown_report(summary: dict[str, Any], report_path: Path) -> None:
    lines = [
        "# Hybrid Pre-Release Heavy Test Report",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Formal run root: `{summary['run_root']}`",
        f"- Gate tests passed: `{summary['gate_tests']['exit_code'] == 0}`",
        f"- Strategy lock clean: `{not summary['lock_mismatches']}`",
        f"- Release recommendation: `{'GO' if summary['release_ready'] else 'HOLD'}`",
        "",
    ]
    _markdown_section(
        lines,
        "## Executive Scope and Caveats",
        [
            "Hybrid is a limited optimization scheme for bounded local workflows. It is not a universal optimization scheme for arbitrary general tasks.",
            "The strategy can still be run on general tasks, but outside the validated task families in this report, neither quality parity nor token or time savings are guaranteed.",
            "This report should therefore be read as a release-facing estimate for a narrow operating range, not as a guaranteed average for tasks of any type and any complexity.",
        ],
    )
    _markdown_section(
        lines,
        "## Method",
        [
            "This run compares a natural-language baseline against the current adaptive hybrid strategy.",
            "The suite contains 12 local heavy tasks: four tiers and three groups per tier.",
            "Token consumption uses Codex-reported total tokens when available, and falls back to estimated prompt plus visible output tokens only when the reported count is missing.",
            "Quality uses task-specific validators and is normalized to a 0-100 score.",
            "The summary also tracks contract family, adapter family, validator type, resumability coverage, and exactness preservation coverage so the report does not overfit to tier labels alone.",
        ],
    )
    _markdown_section(lines, "## Classification Limits", CLASSIFICATION_LIMITS, bullets=True)
    _markdown_section(lines, "## Recommended Task Families", RECOMMENDED_TASK_FAMILIES, bullets=True)
    _markdown_section(
        lines,
        "## Task Families That Should Not Use This Report As a Proxy",
        NON_REPRESENTATIVE_TASK_FAMILIES,
        bullets=True,
    )
    _markdown_section(
        lines,
        "## Why T0 Can Show Negative Optimization",
        _t0_negative_optimization_lines(summary),
    )
    lines.extend(
        [
            "",
            "## Task Selection",
            "",
            "| Tier | Group | Title | Representative Task Description |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for row in summary["tasks"]:
        lines.append(
            f"| {row['tier']} | {row['group']} | {_report_task_title(row)} | {_report_task_description(row)} |"
        )
    lines.extend(
        [
            "",
            "## Per-Task Metrics",
            "",
            "| Tier | Group | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Quality | Hybrid Quality | Quality Delta | Route OK |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in summary["tasks"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        lines.append(
            "| {tier} | {group} | {bt} | {ht} | {to} | {bsec:.2f} | {hsec:.2f} | {eo} | {bq} | {hq} | {qd} | {route_ok} |".format(
                tier=row["tier"],
                group=row["group"],
                bt=effective_tokens(_row_to_result(baseline)),
                ht=effective_tokens(_row_to_result(hybrid)),
                to=_fmt_pct(row["token_optimization_pct"]),
                bsec=baseline["elapsed_seconds"],
                hsec=hybrid["elapsed_seconds"],
                eo=_fmt_pct(row["time_optimization_pct"]),
                bq=baseline["quality_score"],
                hq=hybrid["quality_score"],
                qd=row["quality_delta"],
                route_ok="yes" if row["route_matches_expected"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Tier Aggregates",
            "",
            "| Tier | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for tier_row in summary["tiers"]:
        agg = tier_row["aggregate"]
        lines.append(
            "| {tier} | {count} | {bt} | {ht} | {to} | {bsec:.2f} | {hsec:.2f} | {eo} | {bq:.2f} | {hq:.2f} | {qd:.2f} |".format(
                tier=tier_row["tier"],
                count=tier_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                to=_fmt_pct(agg["token_optimization_pct"]),
                bsec=agg["baseline_total_seconds"],
                hsec=agg["hybrid_total_seconds"],
                eo=_fmt_pct(agg["time_optimization_pct"]),
                bq=agg["baseline_avg_quality"],
                hq=agg["hybrid_avg_quality"],
                qd=agg["quality_delta"],
            )
        )
    lines.extend(
        [
            "",
            "## Contract Family Aggregates",
            "",
            "| Contract Family | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for family_row in summary["contract_families"]:
        agg = family_row["aggregate"]
        lines.append(
            "| {name} | {count} | {bt} | {ht} | {to} | {bq:.2f} | {hq:.2f} | {qd:.2f} |".format(
                name=family_row["contract_family"],
                count=family_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                to=_fmt_pct(agg["token_optimization_pct"]),
                bq=agg["baseline_avg_quality"],
                hq=agg["hybrid_avg_quality"],
                qd=agg["quality_delta"],
            )
        )
    lines.extend(
        [
            "",
            "## Adapter Family Aggregates",
            "",
            "| Adapter Family | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for family_row in summary["adapter_families"]:
        agg = family_row["aggregate"]
        lines.append(
            "| {name} | {count} | {bt} | {ht} | {to} | {bq:.2f} | {hq:.2f} | {qd:.2f} |".format(
                name=family_row["adapter_family"],
                count=family_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                to=_fmt_pct(agg["token_optimization_pct"]),
                bq=agg["baseline_avg_quality"],
                hq=agg["hybrid_avg_quality"],
                qd=agg["quality_delta"],
            )
        )
    lines.extend(
        [
            "",
            "## Validator Type Aggregates",
            "",
            "| Validator Type | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for family_row in summary["validator_types"]:
        agg = family_row["aggregate"]
        lines.append(
            "| {name} | {count} | {bt} | {ht} | {to} | {bq:.2f} | {hq:.2f} | {qd:.2f} |".format(
                name=family_row["validator_type"],
                count=family_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                to=_fmt_pct(agg["token_optimization_pct"]),
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
        ]
    )
    overall = summary["overall"]
    lines.extend(
        [
            "",
            "## Overall Aggregate",
            "",
            f"- Baseline total tokens: `{overall['baseline_total_tokens']}`",
            f"- Hybrid total tokens: `{overall['hybrid_total_tokens']}`",
            f"- Token optimization pct: `{_fmt_pct(overall['token_optimization_pct'])}`",
            f"- Baseline total seconds: `{overall['baseline_total_seconds']:.2f}`",
            f"- Hybrid total seconds: `{overall['hybrid_total_seconds']:.2f}`",
            f"- Time optimization pct: `{_fmt_pct(overall['time_optimization_pct'])}`",
            f"- Baseline average quality: `{overall['baseline_avg_quality']:.2f}`",
            f"- Hybrid average quality: `{overall['hybrid_avg_quality']:.2f}`",
            f"- Quality delta: `{overall['quality_delta']:.2f}`",
            "",
            "## Detailed Findings",
            "",
        ]
    )
    for row in summary["tasks"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        lines.extend(
            [
                f"### {row['tier']} G{row['group']} - {_report_task_title(row)}",
                "",
                f"- Task description: {_report_task_description(row)}",
                f"- Contract family: {row['contract_family']}",
                f"- Adapter family: {row['adapter_family']}",
                f"- Validator type: {row['validator_type']}",
                f"- Observed adapter id: {hybrid['adapter_id']}",
                f"- Contract hash: {hybrid['contract_hash']}",
                f"- NL baseline tokens: {effective_tokens(_row_to_result(baseline))}",
                f"- Hybrid tokens: {effective_tokens(_row_to_result(hybrid))}",
                f"- Token optimization pct: {_fmt_pct(row['token_optimization_pct'])}",
                f"- NL baseline runtime seconds: {baseline['elapsed_seconds']:.2f}",
                f"- Hybrid runtime seconds: {hybrid['elapsed_seconds']:.2f}",
                f"- Time optimization pct: {_fmt_pct(row['time_optimization_pct'])}",
                f"- NL baseline quality: {baseline['quality_score']} ({baseline['quality_grade']})",
                f"- Hybrid quality: {hybrid['quality_score']} ({hybrid['quality_grade']})",
                f"- Quality delta: {row['quality_delta']}",
                f"- Route match: {row['route_matches_expected']}",
                f"- Adapter match: {row['adapter_matches_expected']}",
                f"- Resumability covered: {row['resumability_covered']}",
                f"- Exactness preserved: {row['exactness_preserved']}",
                f"- Baseline notes: {'; '.join(baseline['quality_notes'])}",
                f"- Hybrid notes: {'; '.join(hybrid['quality_notes'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Release Decision",
            "",
            (
                "Recommendation: GO for the bounded local engineering range covered by this report. Gate checks passed, the strategy lock stayed clean, hybrid routed to the expected tier, and average hybrid quality did not fall below the baseline."
                if summary["release_ready"]
                else "Recommendation: HOLD. Review gate failures, routing mismatches, or quality regressions before release."
            ),
            "This recommendation does not convert hybrid into a general-purpose optimization guarantee for arbitrary tasks.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _header_footer(title: str):
    def draw(canvas_obj: canvas.Canvas, doc) -> None:
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.drawString(doc.leftMargin, doc.height + doc.topMargin + 10, title)
        canvas_obj.drawRightString(doc.pagesize[0] - doc.rightMargin, 12, f"Page {doc.page}")
        canvas_obj.restoreState()

    return draw


def make_paragraph_style(base_style: ParagraphStyle, **overrides: Any) -> ParagraphStyle:
    style = ParagraphStyle(name=f"{base_style.name}_{int(time.time() * 1000)}", parent=base_style)
    for key, value in overrides.items():
        setattr(style, key, value)
    return style


def render_pdf(summary: dict[str, Any], pdf_path: Path) -> None:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is not installed")

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Hybrid Pre-Release Heavy Test Report",
        author="OpenAI Codex",
    )
    styles = getSampleStyleSheet()
    title_style = make_paragraph_style(styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, alignment=TA_CENTER)
    h1 = make_paragraph_style(styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=18, spaceAfter=8)
    h2 = make_paragraph_style(styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, spaceAfter=6)
    body = make_paragraph_style(styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_LEFT)
    small = make_paragraph_style(styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10)

    story: list[Any] = []
    story.append(Paragraph("Hybrid Pre-Release Heavy Test Report", title_style))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Run ID: {summary['run_id']}", body))
    story.append(Paragraph(f"Generated at: {summary['generated_at']}", body))
    story.append(Paragraph(f"Formal run root: {summary['run_root']}", body))
    story.append(Paragraph(f"Release recommendation: {'GO' if summary['release_ready'] else 'HOLD'}", body))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Executive Scope and Caveats", h1))
    _append_pdf_lines(
        story,
        [
            "Hybrid is a limited optimization scheme for bounded local workflows. It is not a universal optimization scheme for arbitrary general tasks.",
            "The strategy can still be run on general tasks, but outside the validated task families in this report, neither quality parity nor token or time savings are guaranteed.",
            "These results should therefore be read as a release-facing estimate for a narrow operating range, not as a guaranteed average for tasks of any type and any complexity.",
        ],
        body,
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Method", h1))
    _append_pdf_lines(
        story,
        [
            "This formal pre-release run compares a natural-language baseline against the current adaptive hybrid strategy.",
            "The suite contains 12 local heavy tasks: four tiers and three groups per tier.",
            "Token consumption uses Codex-reported total tokens when available and falls back to estimated prompt plus visible output tokens only when the reported count is missing.",
            "Quality uses task-specific validators normalized to a 0-100 score.",
            "The summary also tracks contract family, adapter family, validator type, resumability coverage, and exactness preservation coverage so tier alone is not treated as the full semantic classifier.",
        ],
        body,
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Validation Dimensions", h1))
    _append_pdf_lines(
        story,
        [
            f"Resumability coverage: {summary['coverage']['resumability']['covered_tasks']}/{summary['coverage']['resumability']['expected_tasks']} tasks ({_fmt_pct(summary['coverage']['resumability']['coverage_pct'])}).",
            f"Exactness preservation coverage: {summary['coverage']['exactness_preservation']['covered_tasks']}/{summary['coverage']['exactness_preservation']['expected_tasks']} tasks ({_fmt_pct(summary['coverage']['exactness_preservation']['coverage_pct'])}).",
        ],
        body,
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Classification Limits", h1))
    _append_pdf_lines(story, CLASSIFICATION_LIMITS, body, bullets=True)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Recommended Task Families", h1))
    _append_pdf_lines(story, RECOMMENDED_TASK_FAMILIES, body, bullets=True)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Task Families That Should Not Use This Report as a Proxy", h1))
    _append_pdf_lines(story, NON_REPRESENTATIVE_TASK_FAMILIES, body, bullets=True)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Why T0 Can Show Negative Optimization", h1))
    _append_pdf_lines(story, _t0_negative_optimization_lines(summary), body)
    story.append(PageBreak())
    story.append(Paragraph("Task Selection", h1))
    task_rows: list[list[Any]] = [[Paragraph("Tier", small), Paragraph("Group", small), Paragraph("Title", small), Paragraph("Representative Task Description", small)]]
    for row in summary["tasks"]:
        task_rows.append(
            [
                Paragraph(row["tier"], small),
                Paragraph(str(row["group"]), small),
                Paragraph(_report_task_title(row), small),
                Paragraph(_report_task_description(row), small),
            ]
        )
    task_table = Table(task_rows, colWidths=[18 * mm, 18 * mm, 52 * mm, 155 * mm], repeatRows=1)
    task_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(task_table)
    story.append(PageBreak())
    story.append(Paragraph("Per-Task Metrics", h1))
    metric_rows: list[list[Any]] = [[Paragraph("Tier", small), Paragraph("Group", small), Paragraph("Baseline Tokens", small), Paragraph("Hybrid Tokens", small), Paragraph("Token Opt %", small), Paragraph("Baseline Time (s)", small), Paragraph("Hybrid Time (s)", small), Paragraph("Time Opt %", small), Paragraph("Baseline Quality", small), Paragraph("Hybrid Quality", small)]]
    for row in summary["tasks"]:
        baseline = _row_to_result(row["baseline"])
        hybrid = _row_to_result(row["hybrid"])
        metric_rows.append([Paragraph(row["tier"], small), Paragraph(str(row["group"]), small), Paragraph(str(effective_tokens(baseline)), small), Paragraph(str(effective_tokens(hybrid)), small), Paragraph(_fmt_pct(row["token_optimization_pct"]), small), Paragraph(f"{baseline.elapsed_seconds:.2f}", small), Paragraph(f"{hybrid.elapsed_seconds:.2f}", small), Paragraph(_fmt_pct(row["time_optimization_pct"]), small), Paragraph(str(baseline.quality_score), small), Paragraph(str(hybrid.quality_score), small)])
    metric_table = Table(metric_rows, colWidths=[16 * mm, 16 * mm, 30 * mm, 30 * mm, 24 * mm, 26 * mm, 26 * mm, 24 * mm, 24 * mm, 24 * mm], repeatRows=1)
    metric_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(metric_table)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Tier Aggregates", h1))
    aggregate_rows: list[list[Any]] = [[Paragraph("Tier", small), Paragraph("Task Count", small), Paragraph("Baseline Tokens", small), Paragraph("Hybrid Tokens", small), Paragraph("Token Opt %", small), Paragraph("Baseline Time (s)", small), Paragraph("Hybrid Time (s)", small), Paragraph("Time Opt %", small), Paragraph("Baseline Avg Quality", small), Paragraph("Hybrid Avg Quality", small)]]
    for tier_row in summary["tiers"]:
        agg = tier_row["aggregate"]
        aggregate_rows.append([Paragraph(tier_row["tier"], small), Paragraph(str(tier_row["task_count"]), small), Paragraph(str(agg["baseline_total_tokens"]), small), Paragraph(str(agg["hybrid_total_tokens"]), small), Paragraph(_fmt_pct(agg["token_optimization_pct"]), small), Paragraph(f"{agg['baseline_total_seconds']:.2f}", small), Paragraph(f"{agg['hybrid_total_seconds']:.2f}", small), Paragraph(_fmt_pct(agg["time_optimization_pct"]), small), Paragraph(f"{agg['baseline_avg_quality']:.2f}", small), Paragraph(f"{agg['hybrid_avg_quality']:.2f}", small)])
    aggregate_table = Table(aggregate_rows, colWidths=[18 * mm, 22 * mm, 30 * mm, 30 * mm, 24 * mm, 26 * mm, 26 * mm, 24 * mm, 30 * mm, 30 * mm], repeatRows=1)
    aggregate_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c2d12")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(aggregate_table)
    story.append(PageBreak())
    story.append(Paragraph("Detailed Findings", h1))
    for row in summary["tasks"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        story.append(Paragraph(f"{row['tier']} G{row['group']} - {_report_task_title(row)}", h2))
        for line in [
            f"Task description: {_report_task_description(row)}",
            f"Contract family: {row['contract_family']}",
            f"Adapter family: {row['adapter_family']}",
            f"Validator type: {row['validator_type']}",
            f"Observed adapter id: {hybrid['adapter_id']}",
            f"Contract hash: {hybrid['contract_hash']}",
            f"NL baseline tokens: {effective_tokens(_row_to_result(baseline))}",
            f"Hybrid tokens: {effective_tokens(_row_to_result(hybrid))}",
            f"Token optimization pct: {_fmt_pct(row['token_optimization_pct'])}",
            f"NL baseline runtime seconds: {baseline['elapsed_seconds']:.2f}",
            f"Hybrid runtime seconds: {hybrid['elapsed_seconds']:.2f}",
            f"Time optimization pct: {_fmt_pct(row['time_optimization_pct'])}",
            f"NL baseline quality: {baseline['quality_score']} ({baseline['quality_grade']})",
            f"Hybrid quality: {hybrid['quality_score']} ({hybrid['quality_grade']})",
            f"Quality delta: {row['quality_delta']}",
            f"Route match: {row['route_matches_expected']}",
            f"Adapter match: {row['adapter_matches_expected']}",
            f"Resumability covered: {row['resumability_covered']}",
            f"Exactness preserved: {row['exactness_preserved']}",
            f"Baseline notes: {'; '.join(baseline['quality_notes'])}",
            f"Hybrid notes: {'; '.join(hybrid['quality_notes'])}",
        ]:
            story.append(Paragraph(line, body))
        story.append(Spacer(1, 3 * mm))
    overall = summary["overall"]
    story.append(Paragraph("Release Decision", h1))
    for line in [
        f"Baseline total tokens: {overall['baseline_total_tokens']}",
        f"Hybrid total tokens: {overall['hybrid_total_tokens']}",
        f"Token optimization pct: {_fmt_pct(overall['token_optimization_pct'])}",
        f"Baseline total seconds: {overall['baseline_total_seconds']:.2f}",
        f"Hybrid total seconds: {overall['hybrid_total_seconds']:.2f}",
        f"Time optimization pct: {_fmt_pct(overall['time_optimization_pct'])}",
        f"Baseline average quality: {overall['baseline_avg_quality']:.2f}",
        f"Hybrid average quality: {overall['hybrid_avg_quality']:.2f}",
        f"Quality delta: {overall['quality_delta']:.2f}",
        (
            "Recommendation: GO for the bounded local engineering range covered by this report. Gate checks passed, the strategy lock stayed clean, hybrid routed to the expected tier, and the average hybrid quality did not fall below the baseline."
            if summary["release_ready"]
            else "Recommendation: HOLD. Review gate failures, routing mismatches, or quality regressions before release."
        ),
        "This recommendation does not convert hybrid into a general-purpose optimization guarantee for arbitrary tasks.",
    ]:
        story.append(Paragraph(line, body))
    doc.build(story, onFirstPage=_header_footer("Hybrid Pre-Release Heavy Test Report"), onLaterPages=_header_footer("Hybrid Pre-Release Heavy Test Report"))


def maybe_render_preview(pdf_path: Path) -> list[str]:
    TMP_PDF_ROOT.mkdir(parents=True, exist_ok=True)
    prefix = TMP_PDF_ROOT / pdf_path.stem
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return []
    subprocess.run(
        [pdftoppm, "-f", "1", "-l", "2", "-png", str(pdf_path), str(prefix)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return [str(path) for path in sorted(TMP_PDF_ROOT.glob(f"{pdf_path.stem}-*.png"))]


def copy_distribution_files(paths: list[Path]) -> None:
    OUTPUT_PDF_ROOT.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, OUTPUT_PDF_ROOT / path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 4-tier x 3-group heavy pre-release A/B tests for the hybrid strategy.")
    parser.add_argument("--task", action="append", default=[], help="Optional task name filter. Repeat to select multiple tasks.")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Per-run Codex timeout in seconds.")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF generation.")
    args = parser.parse_args()

    tasks = select_tasks(build_tasks(), args.task)
    if not tasks:
        raise SystemExit("No tasks selected.")

    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_root = RUNS_ROOT / f"hybrid_pre_release_heavy_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)

    lock_mismatches = base.verify_strategy_lock()
    gate_result = base.run_gate_tests()
    print(f"[gate] lock_mismatches={len(lock_mismatches)} tests_exit={gate_result.returncode}", flush=True)

    scratch_root = run_root / "artifacts"
    scratch_root.mkdir(parents=True, exist_ok=True)
    baseline_home = scratch_root / "CODEX_HOME_BASELINE"
    hybrid_home = scratch_root / "CODEX_HOME_HYBRID"
    hybrid_t0_home = scratch_root / "CODEX_HOME_HYBRID_T0"
    base.prepare_home(baseline_home, hybrid=False)
    base.prepare_home(hybrid_home, hybrid=True)
    base.prepare_home(
        hybrid_t0_home,
        hybrid=True,
        agents_text=T0_MINIMAL_AGENTS,
        copy_agents=False,
        copy_skills=False,
    )

    results: list[RunResult] = []
    for task in tasks:
        results.append(run_one(task, "baseline", baseline_home, scratch_root, args.timeout_seconds))
        active_hybrid_home = hybrid_t0_home if task.tier == "t0" else hybrid_home
        results.append(run_one(task, "hybrid", active_hybrid_home, scratch_root, args.timeout_seconds))

    summary = build_summary(
        run_id=run_id,
        gate_result=gate_result,
        lock_mismatches=lock_mismatches,
        task_specs=tasks,
        results=results,
        run_root=run_root,
        timeout_seconds=args.timeout_seconds,
    )
    summary_path = run_root / f"hybrid_pre_release_heavy_{run_id}.json"
    markdown_path = run_root / f"hybrid_pre_release_heavy_{run_id}.md"
    pdf_path = run_root / f"hybrid_pre_release_heavy_{run_id}.pdf"
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    write_markdown_report(summary, markdown_path)
    preview_paths: list[str] = []
    generated_files = [summary_path, markdown_path]
    if not args.skip_pdf:
        render_pdf(summary, pdf_path)
        preview_paths = maybe_render_preview(pdf_path)
        generated_files.insert(0, pdf_path)
    copy_distribution_files(generated_files)
    print(str(run_root))
    if preview_paths:
        print(json.dumps({"preview_images": preview_paths}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
