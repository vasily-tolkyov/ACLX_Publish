from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _default_codex_home() -> Path:
    candidates = [
        Path(os.environ["ACLX_CURRENT_CODEX_HOME"]) if os.environ.get("ACLX_CURRENT_CODEX_HOME") else None,
        Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else None,
        Path.home() / ".codex",
    ]
    fallback = Path.home() / ".codex"
    for candidate in candidates:
        if candidate is None:
            continue
        fallback = candidate
        if candidate.exists():
            return candidate
    return fallback


def _normalize_plugin_skill_root(candidate: Path) -> Path:
    if (candidate / "SKILL.md").exists():
        return candidate
    nested = candidate / "skills" / "aclx-runtime"
    if (nested / "SKILL.md").exists():
        return nested
    return candidate


def _default_plugin_skill_root(codex_home: Path) -> Path:
    override = os.environ.get("ACLX_PLUGIN_SKILL_ROOT")
    if override:
        return _normalize_plugin_skill_root(Path(override))
    candidates = [
        Path.home() / "plugins" / "aclx-runtime" / "skills" / "aclx-runtime",
        codex_home / "plugins" / "cache" / "local-user-plugins" / "aclx-runtime" / "local",
        codex_home / "plugins" / "cache" / "local-user-plugins" / "aclx-runtime" / "local" / "skills" / "aclx-runtime",
    ]
    fallback = _normalize_plugin_skill_root(candidates[0])
    for candidate in candidates:
        normalized = _normalize_plugin_skill_root(candidate)
        fallback = normalized
        if normalized.exists():
            return normalized
    return fallback


def _default_skill_validator(codex_home: Path) -> Path:
    override = os.environ.get("ACLX_SKILL_VALIDATOR")
    if override:
        return Path(override)
    return codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


CURRENT_CODEX_HOME = _default_codex_home()
PLUGIN_SKILL_ROOT = _default_plugin_skill_root(CURRENT_CODEX_HOME)
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"
ARTIFACT_ROOT = REPO_ROOT / "artifacts"
VALIDATOR = _default_skill_validator(CURRENT_CODEX_HOME)
EXEC_TIMEOUT_SECONDS = 600

import sys

sys.path.insert(0, str(REPO_ROOT / "src"))

from aclx.metrics import model_token_count  # noqa: E402
from aclx.supervisor import ACLXSupervisor, T0_MINIMAL_AGENTS  # noqa: E402


BASELINE_AGENTS = """# Native NL Baseline

Keep runtime-visible machine state in natural language unless the prompt explicitly requires a file format.
Do not use ACL-X runtime bridges, checkpoint wrappers, or hybrid prompt packaging unless the prompt itself demands it.
Keep the final answer concise.
"""


@dataclass(slots=True)
class TaskSpec:
    name: str
    tier: str
    title: str
    profile: str
    validator: str
    task: str = ""
    fixture_name: str | None = None
    task_shape: str | None = None
    expected_handoffs: int = 0
    expected_rounds: int = 1
    child_agents: int = 0
    shared_state: bool = False
    outputs: list[str] | None = None
    constraints: list[str] | None = None
    stop_conditions: list[str] | None = None
    next_actions: list[str] | None = None


@dataclass(slots=True)
class RunInput:
    prompt: str
    tier: str
    reasoning_effort: str | None


@dataclass(slots=True)
class RunResult:
    name: str
    tier: str
    title: str
    arm: str
    exit_code: int
    elapsed_seconds: float
    reported_total_tokens: int | None
    estimated_prompt_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    quality_score: int
    quality_notes: list[str]
    session_id: str | None
    artifact_format: str
    routed_tier: str
    reasoning_effort: str | None


TASKS: list[TaskSpec] = [
    TaskSpec(
        name="t0_single_surface_summary",
        tier="t0",
        title="Single-surface summary",
        profile="review",
        validator="t0",
        task_shape="single_surface",
        task=(
            "You are in an isolated workspace. Only read files under {workspace}.\n\n"
            "Read `docs/release_notes.txt`.\n"
            "Return exactly 3 lines:\n"
            "Tier: t0\n"
            "Decision: <one sentence>\n"
            "Evidence: docs/release_notes.txt; mention strategy lock and adaptive runtime.\n"
            "Do not edit files.\n"
        ),
    ),
    TaskSpec(
        name="t1_single_handoff_review",
        tier="t1",
        title="Single-handoff review",
        profile="review",
        validator="t1",
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
        task=(
            "You are in an isolated workspace. Only edit files under {workspace}.\n\n"
            "Inspect `src/review_target.py`.\n"
            "Delegate exactly once to one reviewer pass, merge the conclusion yourself, "
            "and write `reports/review.md`.\n"
            "`reports/review.md` must contain headings `Decision` and `Evidence`.\n"
            "Identify the highest-risk bug with a concrete file path and explain why empty input breaks the function.\n"
            "Keep the final reply to one sentence and list changed file paths.\n"
        ),
    ),
    TaskSpec(
        name="t2_shared_state_task",
        tier="t2",
        title="Shared-state repair",
        profile="implement",
        validator="t2",
        fixture_name="t2_shared_state_task",
        task_shape="shared_state",
    ),
    TaskSpec(
        name="t3_loop_skill_task",
        tier="t3",
        title="Loop skill repair",
        profile="review",
        validator="t3",
        fixture_name="t3_loop_skill_task",
        task_shape="loop",
    ),
]


def find_codex() -> str:
    return shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex") or "codex"


def copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def prepare_home(
    home: Path,
    *,
    hybrid: bool,
    agents_text: str | None = None,
    copy_agents: bool = True,
    copy_skills: bool = True,
) -> None:
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CURRENT_CODEX_HOME / "auth.json", home / "auth.json")
    shutil.copy2(CURRENT_CODEX_HOME / "config.toml", home / "config.toml")
    agents_dir = CURRENT_CODEX_HOME / "agents"
    if copy_agents and agents_dir.exists():
        copytree(agents_dir, home / "agents")
    if copy_skills:
        skills_dir = home / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        router_skill = CURRENT_CODEX_HOME / "skills" / "codex-subagent-router"
        if router_skill.exists():
            copytree(router_skill, skills_dir / "codex-subagent-router")
        if PLUGIN_SKILL_ROOT.exists():
            copytree(PLUGIN_SKILL_ROOT, skills_dir / "aclx-runtime")
    if agents_text is not None:
        (home / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    elif hybrid:
        shutil.copy2(REPO_ROOT / "AGENTS.md", home / "AGENTS.md")
    else:
        (home / "AGENTS.md").write_text(BASELINE_AGENTS, encoding="utf-8")


def parse_tokens(stderr_text: str) -> int | None:
    match = re.search(r"tokens used\s*\r?\n([0-9,]+)", stderr_text, flags=re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else None


def parse_session_id(stderr_text: str) -> str | None:
    match = re.search(r"session id:\s*([^\r\n]+)", stderr_text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def estimate_tokens(text: str) -> int:
    return int(model_token_count(text))


def verify_strategy_lock() -> list[str]:
    manifest = json.loads((REPO_ROOT / "configs" / "strategy_lock.json").read_text(encoding="utf-8"))
    mismatches: list[str] = []
    for relative_path, expected_hash in sorted(manifest["files"].items()):
        path = REPO_ROOT / str(relative_path)
        if not path.exists():
            mismatches.append(f"{relative_path} missing")
            continue
        actual_hash = _sha256(path)
        if actual_hash != str(expected_hash).lower():
            mismatches.append(f"{relative_path} expected {expected_hash} got {actual_hash}")
    return mismatches


def _sha256(path: Path) -> str:
    import hashlib

    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        normalized = data
    else:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def run_gate_tests() -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    command = [
        "python",
        "-m",
        "unittest",
        "tests.test_contract",
        "tests.test_formal_heavy_matrix",
        "tests.test_hybrid",
        "tests.test_supervisor",
        "tests.test_strategy_lock",
        "tests.test_t23_real_ab_runner",
        "-q",
    ]
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", env=env)


def load_fixture(task: TaskSpec) -> dict[str, Any]:
    if not task.fixture_name:
        return {}
    fixture_dir = FIXTURE_ROOT / task.fixture_name
    data = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    data["fixture_dir"] = str(fixture_dir)
    return data


def build_workspace(task: TaskSpec, workspace: Path) -> None:
    if task.fixture_name:
        copytree(Path(str(load_fixture(task)["fixture_dir"])), workspace)
        return
    workspace.mkdir(parents=True, exist_ok=True)
    if task.tier == "t0":
        (workspace / "docs").mkdir(parents=True, exist_ok=True)
        (workspace / "docs" / "release_notes.txt").write_text(
            "Release validation facts\n"
            "- strategy lock protects AGENTS.md, configs/hybrid_router_map.yaml, src/aclx/hybrid.py, and src/aclx/supervisor.py\n"
            "- default runtime style is adaptive\n"
            "- single-surface work stays in t0\n"
            "- t0 should not load ACL-X runtime bundles\n",
            encoding="utf-8",
        )
        return
    if task.tier == "t1":
        (workspace / "src").mkdir(parents=True, exist_ok=True)
        (workspace / "reports").mkdir(parents=True, exist_ok=True)
        (workspace / "src" / "review_target.py").write_text(
            "def first_non_empty_upper(items: list[str | None]) -> str:\n"
            "    \"\"\"Return the first non-empty value uppercased.\n\n"
            "    Empty input should return 'N/A'.\n"
            "    \"\"\"\n"
            "    cleaned = [item.strip() for item in items if item is not None and item.strip()]\n"
            "    return cleaned[0].upper()\n",
            encoding="utf-8",
        )
        return
    raise ValueError(f"Unsupported lightweight workspace tier: {task.tier}")


def build_prompt(task: TaskSpec, workspace: Path, arm: str) -> RunInput:
    if task.fixture_name:
        fixture = load_fixture(task)
        raw_task = str(fixture["task"]).format(workspace=str(workspace))
        if arm == "baseline":
            return RunInput(prompt=raw_task, tier=task.tier, reasoning_effort=None)
        supervisor = ACLXSupervisor()
        payload = supervisor.build_payload(
            raw_task,
            cwd=str(workspace),
            style="adaptive",
            profile=str(fixture["profile"]),
            task_shape="shared_state" if task.tier == "t2" else "loop",
            outputs=[str(value) for value in fixture.get("outputs", [])],
            constraints=[str(value) for value in fixture.get("constraints", [])],
            stop_conditions=[str(value) for value in fixture.get("stop_conditions", [])],
            next_actions=[str(value) for value in fixture.get("next_actions", [])],
            shared_state=task.tier == "t2",
        )
        return RunInput(prompt=payload.codex_prompt, tier=payload.tier, reasoning_effort=payload.reasoning_effort or None)

    raw_task = task.task.format(workspace=str(workspace))
    if arm == "baseline":
        return RunInput(prompt=raw_task, tier=task.tier, reasoning_effort=None)
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
        outputs=task.outputs or [],
        constraints=task.constraints or [],
        stop_conditions=task.stop_conditions or [],
        next_actions=task.next_actions or [],
    )
    return RunInput(prompt=payload.codex_prompt, tier=payload.tier, reasoning_effort=payload.reasoning_effort or None)


def run_one(task: TaskSpec, arm: str, home: Path, scratch_root: Path) -> RunResult:
    run_dir = scratch_root / task.tier / arm
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace = run_dir / "workspace"
    build_workspace(task, workspace)
    run_input = build_prompt(task, workspace, arm)
    prompt = run_input.prompt
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"[start] {task.tier} {arm}", flush=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["NO_COLOR"] = "1"
    command = [
        find_codex(),
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
            timeout=EXEC_TIMEOUT_SECONDS,
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
        f"[done] {task.tier} {arm} exit={exit_code} elapsed={elapsed:.2f}s quality={quality_score}",
        flush=True,
    )
    return RunResult(
        name=task.name,
        tier=task.tier,
        title=task.title,
        arm=arm,
        exit_code=exit_code,
        elapsed_seconds=elapsed,
        reported_total_tokens=parse_tokens(stderr_text),
        estimated_prompt_tokens=estimate_tokens(prompt),
        estimated_output_tokens=estimate_tokens(output_text),
        estimated_total_tokens=estimate_tokens(prompt) + estimate_tokens(output_text),
        quality_score=quality_score,
        quality_notes=quality_notes,
        session_id=parse_session_id(stderr_text),
        artifact_format=artifact_format,
        routed_tier=run_input.tier,
        reasoning_effort=run_input.reasoning_effort,
    )


def validate_task(task: TaskSpec, workspace: Path, output_text: str) -> tuple[int, list[str], str]:
    if task.validator == "t0":
        return validate_t0(output_text)
    if task.validator == "t1":
        return validate_t1(workspace)
    if task.validator == "t2":
        return validate_t2(workspace)
    if task.validator == "t3":
        return validate_t3(workspace)
    raise ValueError(f"Unknown validator: {task.validator}")


def validate_t0(output_text: str) -> tuple[int, list[str], str]:
    notes: list[str] = []
    score = 0
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    three_lines = len(lines) == 3
    if three_lines:
        score += 35
    notes.append("exactly 3 non-empty lines" if three_lines else f"expected 3 non-empty lines, got {len(lines)}")
    tier_ok = len(lines) >= 1 and lines[0].lower() == "tier: t0"
    if tier_ok:
        score += 25
    notes.append("tier line correct" if tier_ok else "tier line missing or incorrect")
    evidence_text = output_text.lower()
    source_ok = "docs/release_notes.txt" in evidence_text
    if source_ok:
        score += 20
    notes.append("evidence names docs/release_notes.txt" if source_ok else "evidence missing docs/release_notes.txt")
    facts_ok = "strategy lock" in evidence_text and "adaptive runtime" in evidence_text
    if facts_ok:
        score += 20
    notes.append("evidence cites strategy lock and adaptive runtime" if facts_ok else "required facts missing")
    return score, notes, "message"


def validate_t1(workspace: Path) -> tuple[int, list[str], str]:
    notes: list[str] = []
    score = 0
    report_path = workspace / "reports" / "review.md"
    if report_path.exists():
        score += 35
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        artifact_format = "markdown"
        notes.append("review report written")
    else:
        text = ""
        artifact_format = "missing"
        notes.append("review report missing")
    headings_ok = "Decision" in text and "Evidence" in text
    if headings_ok:
        score += 20
    notes.append("Decision and Evidence headings present" if headings_ok else "Decision/Evidence headings missing")
    path_ok = "src/review_target.py" in text.replace("\\", "/")
    if path_ok:
        score += 15
    notes.append("review cites src/review_target.py" if path_ok else "review missing concrete file path")
    bug_ok = ("empty" in text.lower()) and (
        "indexerror" in text.lower()
        or "cleaned[0]" in text.lower()
        or "list index" in text.lower()
        or "first element" in text.lower()
    )
    if bug_ok:
        score += 30
    notes.append("review explains empty-input failure" if bug_ok else "review missed empty-input list access bug")
    return score, notes, artifact_format


def validate_t2(workspace: Path) -> tuple[int, list[str], str]:
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


def validate_t3(workspace: Path) -> tuple[int, list[str], str]:
    notes: list[str] = []
    score = 0
    skill_path = workspace / "target_skill" / "SKILL.md"
    if skill_path.exists():
        text = skill_path.read_text(encoding="utf-8", errors="ignore").lower()
        checks = {
            "roles": all(token in text for token in ("generator", "critic", "refiner")),
            "intake only": "intake-only" in text or "intake only" in text,
            "critic verdict": "final outward verdict" in text,
            "strict mode": "strict mode" in text or "strict-mode-only" in text,
            "not for new tasks": "do not use for new tasks" in text,
            "no pass counting": "must not count passes or failures" in text,
            "no rewrite": "must not rewrite" in text,
        }
        passed = sum(1 for ok in checks.values() if ok)
        score += int(round((passed / len(checks)) * 60))
        notes.append(f"skill content checks: {passed}/{len(checks)}")
    else:
        notes.append("target_skill/SKILL.md missing")
    validator_ok = False
    if skill_path.exists() and VALIDATOR.exists():
        result = subprocess.run(
            ["python", str(VALIDATOR), str(workspace / "target_skill")],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        validator_ok = result.returncode == 0 and "Skill is valid!" in ((result.stdout or "") + (result.stderr or ""))
    notes.append("skill validator passed" if validator_ok else "skill validator failed")
    if validator_ok:
        score += 20
    artifact_path = workspace / "runtime" / "checkpoints" / "checkpoint_01.aclx"
    artifact_ok = False
    artifact_format = "missing"
    if artifact_path.exists():
        text = artifact_path.read_text(encoding="utf-8", errors="ignore")
        artifact_ok = "h|c|c0|1" in text
        artifact_format = "aclx" if artifact_ok else "other"
    notes.append("checkpoint ACL-X artifact present" if artifact_ok else "checkpoint ACL-X artifact missing or invalid")
    if artifact_ok:
        score += 20
    return score, notes, artifact_format


def build_summary(
    *,
    run_id: str,
    gate_result: subprocess.CompletedProcess[str],
    lock_mismatches: list[str],
    results: list[RunResult],
    scratch_root: Path,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, RunResult]] = {}
    for row in results:
        grouped.setdefault(row.tier, {})[row.arm] = row

    tiers: list[dict[str, Any]] = []
    for tier in ("t0", "t1", "t2", "t3"):
        baseline = grouped[tier]["baseline"]
        hybrid = grouped[tier]["hybrid"]
        baseline_tokens = baseline.reported_total_tokens or baseline.estimated_total_tokens
        hybrid_tokens = hybrid.reported_total_tokens or hybrid.estimated_total_tokens
        tiers.append(
            {
                "tier": tier,
                "title": hybrid.title,
                "baseline": asdict(baseline),
                "hybrid": asdict(hybrid),
                "token_optimization_pct": improvement_pct(baseline_tokens, hybrid_tokens),
                "time_optimization_pct": improvement_pct(baseline.elapsed_seconds, hybrid.elapsed_seconds),
                "quality_delta": hybrid.quality_score - baseline.quality_score,
                "route_matches_expected": hybrid.routed_tier == tier,
            }
        )

    release_ready = (
        gate_result.returncode == 0
        and not lock_mismatches
        and all(row["route_matches_expected"] for row in tiers)
        and all((row["hybrid"]["exit_code"] == 0 and row["baseline"]["exit_code"] == 0) for row in tiers)
        and all(row["hybrid"]["quality_score"] >= row["baseline"]["quality_score"] for row in tiers)
    )
    return {
        "kind": "release_validation_ab",
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scratch_root": str(scratch_root),
        "lock_mismatches": lock_mismatches,
        "gate_tests": {
            "exit_code": gate_result.returncode,
            "stdout": gate_result.stdout,
            "stderr": gate_result.stderr,
        },
        "tiers": tiers,
        "release_ready": release_ready,
    }


def improvement_pct(baseline: float, hybrid: float) -> float | None:
    if not baseline:
        return None
    return round(((baseline - hybrid) / baseline) * 100.0, 2)


def write_report(summary: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# ACL-X Lightweight Release Validation Report",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Strategy lock clean: `{not summary['lock_mismatches']}`",
        f"- Gate tests passed: `{summary['gate_tests']['exit_code'] == 0}`",
        f"- Release recommendation: `{'GO' if summary['release_ready'] else 'HOLD'}`",
        "",
        "## Executive Summary",
        "",
        "This report compares the current adaptive tier strategy against a natural-language baseline using one fresh lightweight A/B task per tier.",
        "Token optimization uses the Codex-reported total token count when available, with estimated prompt+output tokens only as fallback.",
        "",
        "## Tier Results",
        "",
        "| Tier | Title | Route OK | Baseline Tokens | Hybrid Tokens | Token Opt | Baseline Time (s) | Hybrid Time (s) | Time Opt | Baseline Quality | Hybrid Quality | Quality Delta |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["tiers"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        baseline_tokens = baseline["reported_total_tokens"] or baseline["estimated_total_tokens"]
        hybrid_tokens = hybrid["reported_total_tokens"] or hybrid["estimated_total_tokens"]
        lines.append(
            "| {tier} | {title} | {route_ok} | {bt} | {ht} | {to}% | {bsec:.2f} | {hsec:.2f} | {eo}% | {bq} | {hq} | {qd} |".format(
                tier=row["tier"],
                title=row["title"],
                route_ok="yes" if row["route_matches_expected"] else "no",
                bt=baseline_tokens,
                ht=hybrid_tokens,
                to=_fmt_pct(row["token_optimization_pct"]),
                bsec=baseline["elapsed_seconds"],
                hsec=hybrid["elapsed_seconds"],
                eo=_fmt_pct(row["time_optimization_pct"]),
                bq=baseline["quality_score"],
                hq=hybrid["quality_score"],
                qd=row["quality_delta"],
            )
        )

    for row in summary["tiers"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        lines.extend(
            [
                "",
                f"### {row['tier']} - {row['title']}",
                "",
                f"- Expected route: `{row['tier']}`; hybrid routed to `{hybrid['routed_tier']}`.",
                f"- NL baseline: `{baseline['elapsed_seconds']:.2f}s`, `{baseline['reported_total_tokens'] or baseline['estimated_total_tokens']}` tokens, quality `{baseline['quality_score']}/100`.",
                f"- Current strategy: `{hybrid['elapsed_seconds']:.2f}s`, `{hybrid['reported_total_tokens'] or hybrid['estimated_total_tokens']}` tokens, quality `{hybrid['quality_score']}/100`.",
                f"- Token optimization vs NL baseline: `{_fmt_pct(row['token_optimization_pct'])}%`.",
                f"- Time optimization vs NL baseline: `{_fmt_pct(row['time_optimization_pct'])}%`.",
                f"- Quality delta: `{row['quality_delta']}`.",
                f"- Baseline notes: {'; '.join(baseline['quality_notes'])}.",
                f"- Hybrid notes: {'; '.join(hybrid['quality_notes'])}.",
            ]
        )

    lines.extend(
        [
            "",
            "## Gate Checks",
            "",
            f"- Strategy lock mismatches: `{0 if not summary['lock_mismatches'] else len(summary['lock_mismatches'])}`",
            f"- Unit gate command exit code: `{summary['gate_tests']['exit_code']}`",
            "",
            "## Release Decision",
            "",
            (
                "Recommendation: GO. The current strategy stayed on the expected tier for all four tasks, "
                "passed the gate tests, preserved the lock manifest, and did not underperform the NL baseline on quality."
                if summary["release_ready"]
                else "Recommendation: HOLD. Review the failed gate checks or tier regressions before release."
            ),
            "",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def main() -> int:
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_dir = ARTIFACT_ROOT / f"release_validation_ab_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    lock_mismatches = verify_strategy_lock()
    gate_result = run_gate_tests()
    print(f"[gate] lock_mismatches={len(lock_mismatches)} tests_exit={gate_result.returncode}", flush=True)

    scratch_root = Path(tempfile.mkdtemp(prefix="aclx-release-validation-"))
    baseline_home = scratch_root / "CODEX_HOME_BASELINE"
    hybrid_home = scratch_root / "CODEX_HOME_HYBRID"
    hybrid_t0_home = scratch_root / "CODEX_HOME_HYBRID_T0"
    prepare_home(baseline_home, hybrid=False)
    prepare_home(hybrid_home, hybrid=True)
    prepare_home(
        hybrid_t0_home,
        hybrid=True,
        agents_text=T0_MINIMAL_AGENTS,
        copy_agents=False,
        copy_skills=False,
    )
    print(f"[scratch] {scratch_root}", flush=True)

    results: list[RunResult] = []
    for task in TASKS:
        results.append(run_one(task, "baseline", baseline_home, scratch_root))
        active_hybrid_home = hybrid_t0_home if task.tier == "t0" else hybrid_home
        results.append(run_one(task, "hybrid", active_hybrid_home, scratch_root))

    summary = build_summary(
        run_id=run_id,
        gate_result=gate_result,
        lock_mismatches=lock_mismatches,
        results=results,
        scratch_root=scratch_root,
    )
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    write_report(summary, out_dir)
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
