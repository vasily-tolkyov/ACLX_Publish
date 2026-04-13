from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contract import TaskContract
from .contract_pipeline import normalize_items, resolve_task_contract
from .ctxbridge import load_ctx_module
from .delegation import ACLXDelegation
from .hybrid import (
    ACLXHybridPromptBuilder,
    HybridTaskSpec,
    classify_hybrid_route,
    infer_hybrid_profile,
    load_hybrid_router_map,
)
from .runtime_bridge import ACLXRuntimeBridge
from .transcoder import ACLXTranscoder

DEFAULT_CODEX_CWD = Path("D:/")
DEFAULT_SUPERVISOR_STYLE = "adaptive"
DEFAULT_SUPERVISOR_TASK = (
    "Use ACL-X as the default runtime-visible protocol. "
    "Keep human-facing output concise. "
    "Avoid unnecessary shell exploration and only run commands that materially improve correctness."
)
T0_COMPACT_GUARD = "Keep the required output shape and explicit literal facts verbatim."
T0_MINIMAL_AGENTS = (
    "# T0\n"
    "One-shot NL only. No ACL-X bundles, runtime files, skills, or handoffs. "
    "Keep exact shape or literal facts only when the task explicitly requires them.\n"
)


@dataclass(slots=True)
class SupervisorPayload:
    task: str
    codex_prompt: str
    aclx_bundle: str
    delegation_json: str
    cwd: str
    tier: str = "t0"
    bridge_mode: str = "none"
    style: str = DEFAULT_SUPERVISOR_STYLE
    reasoning_effort: str = ""


class ACLXSupervisor:
    def __init__(self) -> None:
        self.transcoder = ACLXTranscoder()
        self.runtime_bridge = ACLXRuntimeBridge(transcoder=self.transcoder)
        self.delegation = ACLXDelegation()
        self.hybrid = ACLXHybridPromptBuilder(adapter=self.delegation.adapter)

    def build_payload(
        self,
        task: str,
        *,
        cwd: str | None = None,
        style: str = DEFAULT_SUPERVISOR_STYLE,
        profile: str | None = None,
        lane: str = "",
        task_shape: str | None = None,
        expected_handoffs: int = 0,
        expected_rounds: int = 1,
        child_agents: int = 0,
        shared_state: bool | None = None,
        current_state: list[str] | None = None,
        next_actions: list[str] | None = None,
        outputs: list[str] | None = None,
        constraints: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        scope_in: list[str] | None = None,
        scope_out: list[str] | None = None,
        inputs: list[str] | None = None,
        contract: TaskContract | dict[str, object] | None = None,
    ) -> SupervisorPayload:
        cwd = cwd or str(DEFAULT_CODEX_CWD)
        normalized_style = "adaptive" if style == "hybrid" else style
        current_state = normalize_items(current_state)
        resolution = resolve_task_contract(
            task,
            project_root=cwd,
            contract=contract,
            required_artifacts=outputs,
            acceptance_contract=constraints,
            stop_conditions=stop_conditions,
            next_actions=next_actions,
            scope_in=scope_in,
            scope_out=scope_out,
            inputs=inputs,
            expected_handoffs=expected_handoffs,
            expected_rounds=expected_rounds,
            child_agents=child_agents,
            shared_state=shared_state,
        )
        task_contract = resolution.contract
        outputs = resolution.required_artifacts
        constraints = resolution.acceptance_contract
        stop_conditions = resolution.stop_conditions
        next_actions = resolution.next_actions
        scope_in = resolution.scope_in
        scope_out = resolution.scope_out
        inputs = resolution.inputs
        shared_state_flag = bool(shared_state) if shared_state is not None else False
        shared_state_flag = bool(shared_state_flag or task_contract.runtime_needs.shared_state)
        route = classify_hybrid_route(
            task,
            contract=task_contract,
            profile=profile,
            task_shape=task_shape,
            expected_handoffs=expected_handoffs,
            expected_rounds=expected_rounds,
            child_agents=child_agents,
            shared_state=shared_state_flag,
        )
        resolved_tier = route.tier
        delegation_json = ""
        reasoning_effort = ""
        if normalized_style == "full":
            resolved_profile = profile or infer_hybrid_profile(task)
            handoff = {
                "goal": task,
                "current_state": "Execute the user task with ACL-X-first runtime-visible state.",
                "next_actions": [
                    "Use ACL-X for visible machine-only state and handoffs.",
                    "Keep human output short unless the user asked otherwise.",
                    "Avoid unnecessary shell commands.",
                ],
                "priority": 1,
                "certainty": 0.9,
                "scope": "local",
                "source": "aclx-supervisor",
            }
            delegation_payload = self.delegation.from_handoff_obj(handoff, aclx_only=False)
            delegation_json = self.delegation.payload_json(delegation_payload)
            bundle = self.runtime_bridge.encode_supervisor_task(task, cwd=cwd)
            prompt = self._build_codex_prompt_full(
                task=task,
                cwd=cwd,
                aclx_bundle=bundle,
                delegation_json=delegation_json,
            )
            resolved_tier = "t3"
            bridge_mode = "session"
            reasoning_effort = "high"
        else:
            tier = resolved_tier
            route_shape = route.task_shape
            expected_handoffs = route.expected_handoffs
            expected_rounds = route.expected_rounds
            child_agents = route.child_agents
            shared_state_flag = route.shared_state
            bridge_mode = route.bridge_mode
            if tier == "t0":
                return self._build_t0_payload(task, cwd=cwd, style=normalized_style)
            if bridge_mode == "session" and (not outputs or not constraints):
                return self._build_t0_payload(task, cwd=cwd, style=normalized_style)
            resolved_profile = profile or infer_hybrid_profile(task)
            tier_config = _tier_router_config(tier) if bridge_mode == "session" else {}
            doc_loop_compaction = str(tier).lower() == "t3" and _t3_prefers_doc_loop_reasoning(
                outputs=outputs,
                max_choice_lines=int(tier_config.get("doc_loop_low_reasoning_max_choice_lines", 8) or 8),
                contract=task_contract,
            )
            reasoning_effort = self._reasoning_effort_for_tier(tier)
            if doc_loop_compaction:
                if "doc_loop_reasoning_effort" in tier_config:
                    reasoning_effort = str(tier_config.get("doc_loop_reasoning_effort") or "").strip()
            hybrid_payload = self.hybrid.build_prompt(
                HybridTaskSpec(
                    task=task,
                    profile=resolved_profile,
                    lane=lane,
                    tier=tier,
                    contract=task_contract,
                    task_shape=route_shape,
                    cwd=cwd,
                    expected_handoffs=expected_handoffs,
                    expected_rounds=expected_rounds,
                    child_agents=child_agents,
                    shared_state=shared_state_flag,
                    real_handoff_started=tier != "t0",
                    real_loop_started=tier == "t3",
                    current_state=current_state,
                    next_actions=next_actions,
                    scope_in=scope_in,
                    scope_out=scope_out,
                    inputs=inputs,
                    outputs=outputs,
                    constraints=constraints,
                    stop_conditions=stop_conditions,
                )
            )
            bundle = hybrid_payload.aclx_bundle
            if bridge_mode == "session":
                contract_max_lines = int(tier_config.get("task_contract_max_lines", 1) or 1)
                contract_max_chars = int(tier_config.get("task_contract_max_chars", 84) or 84)
                if doc_loop_compaction:
                    contract_max_lines = int(tier_config.get("doc_loop_low_task_contract_max_lines", contract_max_lines) or contract_max_lines)
                    contract_max_chars = int(tier_config.get("doc_loop_low_task_contract_max_chars", contract_max_chars) or contract_max_chars)
                compact_task = _compact_runtime_task(
                    task,
                    outputs=outputs,
                    constraints=constraints,
                    tier=tier,
                    cwd=cwd,
                    preserve_task_contract=bool(tier_config.get("preserve_task_contract", False)),
                    task_contract_max_lines=contract_max_lines,
                    task_contract_max_chars=contract_max_chars,
                    whole_line_only=bool(tier_config.get("whole_line_only", False)),
                    contract=task_contract,
                )
                prompt = self._build_session_prompt(
                    task=compact_task,
                    cwd=cwd,
                    tier=tier,
                    bundle=bundle,
                    outputs=outputs,
                    constraints=constraints,
                    stop_conditions=stop_conditions,
                    next_actions=next_actions,
                    contract=task_contract,
                )
            else:
                prompt = hybrid_payload.prompt
            resolved_tier = hybrid_payload.tier
        return SupervisorPayload(
            task=task,
            codex_prompt=prompt,
            aclx_bundle=bundle,
            delegation_json=delegation_json,
            cwd=cwd,
            tier=resolved_tier,
            bridge_mode=bridge_mode,
            style=normalized_style,
            reasoning_effort=reasoning_effort,
        )

    def _build_t0_payload(self, task: str, *, cwd: str, style: str) -> SupervisorPayload:
        tier_config = _tier_router_config("t0")
        guard_lines = _selective_t0_guard_lines(
            task,
            guard_mode=str(tier_config.get("guard_mode", "selective") or "selective"),
            max_guard_lines=int(tier_config.get("max_guard_lines", 2) or 2),
        )
        return SupervisorPayload(
            task=task,
            codex_prompt=_compose_t0_prompt(task, guard_lines),
            aclx_bundle="",
            delegation_json="{}",
            cwd=cwd,
            tier="t0",
            bridge_mode="none",
            style=style,
            reasoning_effort=_t0_reasoning_effort(task, tier_config),
        )

    def run_codex(
        self,
        payload: SupervisorPayload,
        *,
        model: str | None = None,
        output_json: bool = False,
        dangerously_bypass: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            self._resolve_codex_executable(),
            "exec",
            "--skip-git-repo-check",
            "-C",
            payload.cwd,
            "--output-last-message",
        ]
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as tmp:
            output_path = Path(tmp.name)
        command.append(str(output_path))
        if output_json:
            command.append("--json")
        if model:
            command.extend(["--model", model])
        if payload.reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{payload.reasoning_effort}"'])
        if dangerously_bypass:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        command.append(payload.codex_prompt)
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        try:
            last_message = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        finally:
            output_path.unlink(missing_ok=True)
        if last_message:
            result.stdout = (result.stdout or "") + ("\n" if result.stdout else "") + last_message
        return result

    def _resolve_codex_executable(self) -> str:
        # On this Windows setup the Store-installed codex.exe is visible in PATH
        # but not directly executable from subprocess; prefer the npm shim first.
        for candidate in ("codex.cmd", "codex.exe", "codex"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return "codex"

    def _build_codex_prompt_full(self, *, task: str, cwd: str, aclx_bundle: str, delegation_json: str) -> str:
        sections = [
            "Use $aclx-runtime and $acl-x-protocol.",
            "Keep ACL-X as the default visible runtime protocol for handoffs, machine-only summaries, snapshots, and resumable state.",
            "Use context layering, tool summaries, policy constraints, and session assembly from the local ACL-X runtime when available.",
            "Keep human output short unless the user explicitly asks for more detail.",
            "Avoid unnecessary shell commands.",
            f"Workspace: {cwd}",
        ]
        context_prompt = self._build_ctx_prompt(task=task, cwd=cwd, aclx_bundle=aclx_bundle)
        if context_prompt:
            sections.extend(["", "Default runtime context:", context_prompt])
        sections.extend(
            [
                "",
                "Runtime ACL-X bundle follows.",
                aclx_bundle,
                "",
                "Compact child-agent delegation JSON:",
                delegation_json,
            ]
        )
        return "\n".join(sections)

    def _build_ctx_prompt(self, *, task: str, cwd: str, aclx_bundle: str) -> str:
        session_module = load_ctx_module("session")
        if session_module is None:
            return ""
        run_turn = getattr(session_module, "run_codex_turn", None)
        if not callable(run_turn):
            return ""
        candidates = [
            {
                "active_phase": "integration",
                "task_description": task,
                "tool_results": [],
                "hard_limit": 8000,
                "cwd": cwd,
                "runtime_bundle": aclx_bundle,
                "runtime_tier": "t3",
            },
            {
                "active_phase": "integration",
                "task_description": task,
                "tool_results": [],
                "hard_limit": 8000,
                "runtime_tier": "t3",
            },
        ]
        for kwargs in candidates:
            try:
                value = run_turn(**kwargs)
            except TypeError:
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _reasoning_effort_for_tier(self, tier: str) -> str:
        tier_map = (load_hybrid_router_map().get("tiers") or {}).get(str(tier).lower()) or {}
        return str(tier_map.get("reasoning_effort") or "").strip()

    def _build_session_prompt(
        self,
        *,
        task: str,
        cwd: str,
        tier: str,
        bundle: str,
        outputs: list[str],
        constraints: list[str],
        stop_conditions: list[str],
        next_actions: list[str],
        contract: TaskContract,
    ) -> str:
        session_module = load_ctx_module("session")
        if session_module is None:
            return task if tier == "t0" else "\n".join(part for part in [task, bundle] if part)
        run_turn = getattr(session_module, "run_codex_turn", None)
        if not callable(run_turn):
            return task if tier == "t0" else "\n".join(part for part in [task, bundle] if part)
        project_root = Path(cwd)
        try:
            return str(
                run_turn(
                    active_phase="integration",
                    task_description=task,
                    tool_results=[],
                    hard_limit=8000,
                    project_root=project_root,
                    cwd=cwd,
                    runtime_bundle=bundle,
                    runtime_tier=tier,
                    required_artifacts=outputs,
                    acceptance_contract=constraints,
                    stop_conditions=stop_conditions,
                    next_actions=next_actions,
                    contract=contract,
                )
            ).strip()
        except TypeError:
            return task if tier == "t0" else "\n".join(part for part in [task, bundle] if part)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACL-X supervisor for Codex CLI")
    parser.add_argument("--task", help="Natural-language task")
    parser.add_argument("--task-file", help="Path to a UTF-8 task file")
    parser.add_argument("--cwd", default=str(DEFAULT_CODEX_CWD), help="Working directory for Codex CLI")
    parser.add_argument("--mode", choices=["prepare", "run"], default="prepare")
    parser.add_argument("--style", choices=["adaptive", "hybrid", "full"], default=DEFAULT_SUPERVISOR_STYLE)
    parser.add_argument("--profile", help="Optional hybrid task profile override")
    parser.add_argument("--model", help="Optional Codex model override")
    parser.add_argument("--json", action="store_true", help="Emit or request JSONL-style runtime output when running")
    parser.add_argument("--dangerously-bypass", action="store_true", help="Forward dangerous no-sandbox execution to Codex CLI")
    return parser


def read_task(args: argparse.Namespace) -> str:
    if args.task:
        return args.task
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8").strip()
    data = sys.stdin.read().strip()
    if not data:
        raise SystemExit("Missing task input")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    task = read_task(args)
    supervisor = ACLXSupervisor()
    payload = supervisor.build_payload(task, cwd=args.cwd, style=args.style, profile=args.profile)

    if args.mode == "prepare":
        print(
            json.dumps(
                {
                    "task": payload.task,
                    "cwd": payload.cwd,
                    "style": payload.style,
                    "bridge_mode": payload.bridge_mode,
                    "delegation": json.loads(payload.delegation_json),
                    "prompt": payload.codex_prompt,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0

    result = supervisor.run_codex(
        payload,
        model=args.model,
        output_json=args.json,
        dangerously_bypass=args.dangerously_bypass,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode


def _normalize_items(values: list[str] | None) -> list[str]:
    return normalize_items(values)


def _compact_runtime_task(
    task: str,
    *,
    outputs: list[str],
    constraints: list[str],
    tier: str,
    cwd: str | None = None,
    preserve_task_contract: bool = False,
    task_contract_max_lines: int = 1,
    task_contract_max_chars: int = 84,
    whole_line_only: bool = False,
    contract: TaskContract | None = None,
) -> str:
    text = str(task or "").strip()
    if not text:
        return text
    lowered_tier = str(tier).lower()
    if preserve_task_contract and lowered_tier in {"t2", "t3"}:
        if lowered_tier == "t3" and _task_md_contract_source(contract):
            return _compact_task_md_authoritative_task(
                text,
                outputs=outputs,
                constraints=constraints,
            )
        return _compact_task_contract_lines(
            text,
            outputs=outputs,
            constraints=constraints,
            max_lines=task_contract_max_lines,
            max_chars=task_contract_max_chars,
            whole_line_only=whole_line_only,
            contract=contract,
            include_contract_rules=lowered_tier == "t3",
            include_contract_sources=lowered_tier != "t2",
        )
    if lowered_tier == "t3":
        return text
    output_markers = {value.replace("\\", "/").lower() for value in outputs}
    constraint_markers = {value.lower() for value in constraints}
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        normalized = line.replace("\\", "/").lower()
        if not line:
            continue
        if lowered.startswith("you are in an isolated workspace"):
            continue
        if lowered.startswith("only edit files under "):
            continue
        if lowered.startswith("read ") and "task.md" in lowered:
            continue
        if lowered.startswith("keep the final reply concise"):
            continue
        if lowered.startswith("write ") and any(marker in normalized for marker in output_markers):
            continue
        if any(marker and marker in lowered for marker in constraint_markers):
            continue
        kept.append(line)
    if not kept:
        return text
    kept = kept[:1]
    return "\n".join(kept).strip() or text


def _tier_router_config(tier: str) -> dict[str, object]:
    tiers = load_hybrid_router_map().get("tiers") or {}
    selected = tiers.get(str(tier).lower()) or {}
    return dict(selected)


def _compose_t0_prompt(task: str, guard_lines: list[str]) -> str:
    task_text = str(task or "").strip()
    if not guard_lines:
        return task_text
    return "\n".join(guard_lines) + "\n" + task_text


def _selective_t0_guard_lines(task: str, *, guard_mode: str, max_guard_lines: int) -> list[str]:
    if str(guard_mode or "").strip().lower() != "selective":
        return []
    if not (_t0_has_output_shape_signal(task) or _t0_has_literal_fact_signal(task)):
        return []
    return [T0_COMPACT_GUARD][: max(0, int(max_guard_lines))]


def _t0_reasoning_effort(task: str, tier_config: dict[str, object]) -> str:
    if _t0_has_output_shape_signal(task) or _t0_has_literal_fact_signal(task):
        return str(tier_config.get("exact_output_reasoning_effort", "low") or "low").strip()
    return str(tier_config.get("generic_reasoning_effort", "medium") or "medium").strip()


def _t0_has_output_shape_signal(task: str) -> bool:
    text = str(task or "")
    lowered = text.lower()
    if "return exactly" in lowered or re.search(r"\bexactly\s+\d+\s+non-empty\s+lines?\b", lowered):
        return True
    field_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.match(r"^(tier|decision|evidence)\s*:", line, re.IGNORECASE):
            field_lines += 1
    return field_lines >= 2


def _t0_has_literal_fact_signal(task: str) -> bool:
    lowered = str(task or "").lower()
    if "verbatim" in lowered or "must include" in lowered:
        return True
    if "mention " in lowered and " and " in lowered:
        return True
    return bool(re.search(r"\bkeep\b.+\bliteral\b", lowered))


def _compact_task_contract_lines(
    task: str,
    *,
    outputs: list[str],
    constraints: list[str],
    max_lines: int,
    max_chars: int,
    whole_line_only: bool,
    contract: TaskContract | None,
    include_contract_rules: bool,
    include_contract_sources: bool,
) -> str:
    output_markers = {value.replace("\\", "/").lower() for value in outputs}
    constraint_markers = {value.lower() for value in constraints}
    use_literal_text_fallback = contract is None or not contract.exactness_rules
    main_lines: list[str] = []
    source_lines: list[str] = []
    literal_lines: list[str] = []
    other_lines: list[str] = []
    for raw_line in str(task or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        normalized = line.replace("\\", "/").lower()
        if _is_runtime_boilerplate_line(lowered):
            continue
        if lowered.startswith("write ") and any(marker and marker in normalized for marker in output_markers):
            continue
        if any(marker and marker in lowered for marker in constraint_markers):
            continue
        if _is_contract_source_line(lowered, contract):
            if not include_contract_sources:
                continue
            has_checkpoint_artifact = any(str(item).lower().endswith(".aclx") for item in outputs)
            if include_contract_rules and contract is not None and contract.exactness_rules and not has_checkpoint_artifact:
                continue
            source_lines.append(line)
            continue
        if use_literal_text_fallback and _is_literal_requirement_line(lowered):
            literal_lines.append(line)
            continue
        if _is_main_task_line(lowered):
            main_lines.append(line)
            continue
        other_lines.append(line)
    contract_lines = _contract_rule_lines(contract, outputs=outputs) if include_contract_rules else []
    if contract_lines:
        other_lines = ["Task contract lines:"] + contract_lines + other_lines
    ordered = _unique_lines(main_lines + source_lines + literal_lines + other_lines)
    if not ordered:
        return str(task or "").strip()
    selected = _trim_contract_lines(
        ordered,
        max_lines=max_lines,
        max_chars=max_chars,
        whole_line_only=whole_line_only,
    )
    if not selected:
        return str(task or "").strip()
    return "\n".join(selected)


def _compact_task_md_authoritative_task(
    task: str,
    *,
    outputs: list[str],
    constraints: list[str],
) -> str:
    output_markers = {value.replace("\\", "/").lower() for value in outputs}
    constraint_markers = {value.lower() for value in constraints}
    main_lines: list[str] = []
    fallback_lines: list[str] = []
    for raw_line in str(task or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        normalized = line.replace("\\", "/").lower()
        if _is_runtime_boilerplate_line(lowered):
            continue
        if lowered.startswith("read ") and "task.md" in lowered:
            continue
        if lowered.startswith("write ") and any(marker and marker in normalized for marker in output_markers):
            continue
        if any(marker and marker in lowered for marker in constraint_markers):
            continue
        if _is_literal_requirement_line(lowered):
            continue
        if _is_main_task_line(lowered):
            main_lines.append(line)
            continue
        fallback_lines.append(line)
    ordered = _unique_lines(main_lines + fallback_lines)
    if not ordered:
        return str(task or "").strip()
    return ordered[0]


def _trim_contract_lines(lines: list[str], *, max_lines: int, max_chars: int, whole_line_only: bool) -> list[str]:
    limit_lines = max(1, int(max_lines))
    limit_chars = max(1, int(max_chars))
    selected: list[str] = []
    current_chars = 0
    for line in lines:
        if len(selected) >= limit_lines:
            break
        projected = current_chars + len(line) + (1 if selected else 0)
        if projected > limit_chars and whole_line_only:
            if not selected:
                return [line]
            break
        if projected > limit_chars:
            break
        selected.append(line)
        current_chars = projected
    return selected


def _is_runtime_boilerplate_line(lowered: str) -> bool:
    if lowered.startswith("you are in an isolated workspace"):
        return True
    if lowered.startswith("only edit files under "):
        return True
    if lowered.startswith("keep the final reply concise"):
        return True
    return lowered == "requirements:"


def _is_contract_source_line(lowered: str, contract: TaskContract | None) -> bool:
    if not lowered.startswith("read "):
        return False
    if "task.md" in lowered:
        return True
    if contract is None:
        return False
    contract_sources = [str(item).replace("\\", "/").lower() for item in contract.metadata.get("contract_sources", [])]
    return any(source and source in lowered for source in contract_sources)


def _task_md_contract_source(contract: TaskContract | None) -> bool:
    if contract is None:
        return False
    contract_sources = [str(item).replace("\\", "/").strip().lower() for item in contract.metadata.get("contract_sources", [])]
    return any(source.endswith(("task.md", "task.txt", "task.rst")) for source in contract_sources)


def _is_literal_requirement_line(lowered: str) -> bool:
    if "verbatim" in lowered or "literal" in lowered or "must include" in lowered:
        return True
    if lowered.startswith("return exactly") or "exactly " in lowered:
        return True
    return "headings `" in lowered or "heading `" in lowered


def _is_main_task_line(lowered: str) -> bool:
    prefixes = (
        "fix ",
        "repair ",
        "rewrite ",
        "update ",
        "inspect ",
        "implement ",
        "review ",
        "summarize ",
        "analyze ",
        "analyse ",
        "delegate ",
        "run ",
    )
    return lowered.startswith(prefixes)


def _t3_prefers_doc_loop_reasoning(
    *,
    outputs: list[str] | None,
    max_choice_lines: int,
    contract: TaskContract | None = None,
) -> bool:
    items = _normalize_items(outputs)
    if not items:
        return False
    lowered = [item.replace("\\", "/").lower() for item in items]
    if any(item.endswith(".aclx") for item in lowered):
        return False
    if not all(item.endswith((".md", ".txt", ".rst")) for item in lowered):
        return False
    if contract is None or not contract.exactness_rules:
        return False
    choice_lines = sum(1 for item in contract.exactness_rules if "one of " in item.lower())
    return 0 < choice_lines <= max(1, int(max_choice_lines))


def _contract_rule_lines(contract: TaskContract | None, *, outputs: list[str]) -> list[str]:
    if contract is None:
        return []
    output_markers = {value.replace("\\", "/").lower() for value in outputs}
    selected: list[str] = []
    for line in contract.exactness_rules:
        lowered = line.lower()
        normalized = line.replace("\\", "/").lower()
        if "one of " in lowered or "keep heading " in lowered or "include `" in line or "output in markdown" in lowered:
            selected.append(line)
            continue
        if any(marker and marker in normalized for marker in output_markers):
            selected.append(line)
    return _unique_lines(selected)


def _unique_lines(lines: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
