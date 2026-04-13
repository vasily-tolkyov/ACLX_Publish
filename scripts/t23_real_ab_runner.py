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

import sys

sys.path.insert(0, str(REPO_ROOT / "src"))

from aclx.metrics import model_token_count  # noqa: E402
from aclx.supervisor import ACLXSupervisor  # noqa: E402


BASELINE_AGENTS = """# Native NL Baseline

Keep runtime-visible machine state in natural language unless the prompt explicitly requires a file format.
Do not use ACL-X runtime bridges, checkpoint wrappers, or hybrid prompt packaging unless the prompt itself demands it.
Keep the final answer concise.
"""


@dataclass(slots=True)
class RunResult:
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


@dataclass(slots=True)
class RunInput:
    prompt: str
    tier: str
    reasoning_effort: str | None


def find_codex() -> str:
    return shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex") or "codex"


def copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def prepare_home(home: Path, *, hybrid: bool) -> None:
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CURRENT_CODEX_HOME / "auth.json", home / "auth.json")
    shutil.copy2(CURRENT_CODEX_HOME / "config.toml", home / "config.toml")
    agents_dir = CURRENT_CODEX_HOME / "agents"
    if agents_dir.exists():
        copytree(agents_dir, home / "agents")
    skills_dir = home / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    router_skill = CURRENT_CODEX_HOME / "skills" / "codex-subagent-router"
    if router_skill.exists():
        copytree(router_skill, skills_dir / "codex-subagent-router")
    if PLUGIN_SKILL_ROOT.exists():
        copytree(PLUGIN_SKILL_ROOT, skills_dir / "aclx-runtime")
    if hybrid:
        shutil.copy2(CURRENT_CODEX_HOME / "AGENTS.md", home / "AGENTS.md")
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


def load_fixture(name: str) -> dict[str, object]:
    fixture_dir = FIXTURE_ROOT / name
    data = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    data["fixture_dir"] = str(fixture_dir)
    return data


def build_prompt(task: dict[str, object], workspace: Path, arm: str) -> RunInput:
    raw_task = str(task["task"]).format(workspace=str(workspace))
    if arm == "baseline":
        return RunInput(prompt=raw_task, tier=str(task["tier"]), reasoning_effort=None)
    supervisor = ACLXSupervisor()
    payload = supervisor.build_payload(
        raw_task,
        cwd=str(workspace),
        style="adaptive",
        profile=str(task["profile"]),
        task_shape="shared_state" if str(task["tier"]) == "t2" else "loop",
        outputs=[str(value) for value in task.get("outputs", [])],
        constraints=[str(value) for value in task.get("constraints", [])],
        stop_conditions=[str(value) for value in task.get("stop_conditions", [])],
        next_actions=[str(value) for value in task.get("next_actions", [])],
        shared_state=str(task["tier"]) == "t2",
    )
    return RunInput(
        prompt=payload.codex_prompt,
        tier=payload.tier,
        reasoning_effort=payload.reasoning_effort or None,
    )


def run_one(task: dict[str, object], arm: str, home: Path, scratch_root: Path) -> RunResult:
    run_dir = scratch_root / str(task["tier"]) / arm
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace = run_dir / "workspace"
    copytree(Path(str(task["fixture_dir"])), workspace)
    run_input = build_prompt(task, workspace, arm)
    prompt = run_input.prompt
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
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
            timeout=1800,
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
    if str(task["validator"]) == "t2":
        quality_score, quality_notes, artifact_format = validate_t2(workspace)
    else:
        quality_score, quality_notes, artifact_format = validate_t3(workspace)
    return RunResult(
        tier=str(task["tier"]),
        title=str(task["title"]),
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
    )


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


def build_summary(results: list[RunResult], artifact_dir: Path) -> dict[str, object]:
    grouped: dict[str, dict[str, RunResult]] = {}
    for row in results:
        grouped.setdefault(row.tier, {})[row.arm] = row
    tiers: list[dict[str, object]] = []
    for tier in ("t2", "t3"):
        baseline = grouped[tier]["baseline"]
        hybrid = grouped[tier]["hybrid"]
        tiers.append(
            {
                "tier": tier,
                "baseline": asdict(baseline),
                "hybrid": asdict(hybrid),
                "reported_token_delta_pct": _pct_delta(baseline.reported_total_tokens or 0, hybrid.reported_total_tokens or 0),
                "elapsed_delta_pct": _pct_delta(baseline.elapsed_seconds, hybrid.elapsed_seconds),
                "quality_delta": hybrid.quality_score - baseline.quality_score,
            }
        )
    return {
        "kind": "t23_real_ab",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "artifact_dir": str(artifact_dir),
        "tiers": tiers,
    }


def write_report(summary: dict[str, object], out_dir: Path) -> None:
    lines = [
        "# T2/T3 Real A/B Verification",
        "",
    ]
    for row in summary["tiers"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        lines.extend(
            [
                f"## {row['tier']}",
                "",
                f"- baseline: {baseline['elapsed_seconds']:.2f}s, reported tokens {baseline['reported_total_tokens']}, quality {baseline['quality_score']}, artifact {baseline['artifact_format']}",
                f"- hybrid: {hybrid['elapsed_seconds']:.2f}s, reported tokens {hybrid['reported_total_tokens']}, quality {hybrid['quality_score']}, artifact {hybrid['artifact_format']}",
                f"- elapsed delta pct (baseline->hybrid): {row['elapsed_delta_pct']}",
                f"- reported token delta pct (baseline->hybrid): {row['reported_token_delta_pct']}",
                f"- quality delta (hybrid - baseline): {row['quality_delta']}",
                f"- baseline notes: {'; '.join(baseline['quality_notes'])}",
                f"- hybrid notes: {'; '.join(hybrid['quality_notes'])}",
                "",
            ]
        )
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _pct_delta(baseline: float, hybrid: float) -> float | None:
    if not baseline:
        return None
    return round(((hybrid - baseline) / baseline) * 100.0, 2)


def main() -> int:
    scratch_root = Path(tempfile.mkdtemp(prefix="aclx-t23-repair-"))
    baseline_home = scratch_root / "CODEX_HOME_BASELINE"
    hybrid_home = scratch_root / "CODEX_HOME_HYBRID"
    prepare_home(baseline_home, hybrid=False)
    prepare_home(hybrid_home, hybrid=True)
    results: list[RunResult] = []
    for name in ("t2_shared_state_task", "t3_loop_skill_task"):
        task = load_fixture(name)
        results.append(run_one(task, "baseline", baseline_home, scratch_root))
        results.append(run_one(task, "hybrid", hybrid_home, scratch_root))
    out_dir = ARTIFACT_ROOT / f"t23_real_ab_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(results, out_dir)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    write_report(summary, out_dir)
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
