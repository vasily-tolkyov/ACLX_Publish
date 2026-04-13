from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contract import RuntimeNeeds, TaskContract


TASK_SHAPE_RUNTIME_DEFAULTS: dict[str, dict[str, Any]] = {
    "single_surface": {
        "expected_handoffs": 0,
        "expected_rounds": 1,
        "child_agents": 0,
        "shared_state": False,
    },
    "delegated_once": {
        "expected_handoffs": 1,
        "expected_rounds": 1,
        "child_agents": 1,
        "shared_state": True,
    },
    "shared_state": {
        "expected_handoffs": 1,
        "expected_rounds": 1,
        "child_agents": 1,
        "shared_state": True,
    },
    "multi_step": {
        "expected_handoffs": 2,
        "expected_rounds": 2,
        "child_agents": 2,
        "shared_state": True,
    },
    "loop": {
        "expected_handoffs": 5,
        "expected_rounds": 5,
        "child_agents": 2,
        "shared_state": True,
    },
}


@dataclass(slots=True)
class TierProjection:
    task_shape: str
    tier: str
    bridge_mode: str
    expected_handoffs: int
    expected_rounds: int
    child_agents: int
    shared_state: bool
    signals: list[str] = field(default_factory=list)


def project_tier(
    task: str,
    *,
    contract: TaskContract | None,
    task_shape: str | None,
    real_handoff_started: bool,
    real_loop_started: bool,
    resume_depth: int,
    rule_map: dict[str, Any],
) -> TierProjection:
    lowered = _normalize_text(task)
    shape_map = (rule_map or {}).get("task_shapes", {})
    needs = contract.runtime_needs if contract is not None else RuntimeNeeds()
    signals: list[str] = []
    if task_shape and task_shape in shape_map:
        shape = str(task_shape)
        signals.append("explicit-task-shape")
    elif real_loop_started or resume_depth >= 2 or needs.loop_heavy or needs.resumable:
        shape = "loop"
        signals.append("runtime-loop")
    elif needs.expected_handoffs >= 2 or needs.expected_rounds >= 2 or needs.child_agents >= 2:
        if needs.shared_state:
            shape = "multi_step"
            signals.append("runtime-multi-step")
        else:
            shape = "multi_step"
            signals.append("runtime-multi-step")
    elif _text_signals_loop_runtime(lowered):
        shape = "loop"
        signals.append("text-loop")
    elif needs.shared_state or needs.checkpointable:
        shape = "shared_state"
        signals.append("runtime-shared-state")
    elif real_handoff_started or needs.expected_handoffs == 1 or needs.child_agents == 1:
        shape = "delegated_once"
        signals.append("runtime-single-handoff")
    elif _text_signals_multi_step_runtime(lowered):
        shape = "multi_step"
        signals.append("text-multi-step")
    elif _text_signals_single_handoff_runtime(lowered):
        shape = "delegated_once"
        signals.append("text-single-handoff")
    elif _task_is_meta_only(lowered):
        shape = "single_surface"
        signals.append("meta-only")
    else:
        shape = "single_surface"
        signals.append("default-single-surface")
    tier = str(shape_map.get(shape) or "t0")
    tier_config = ((rule_map or {}).get("tiers") or {}).get(tier) or {}
    defaults = TASK_SHAPE_RUNTIME_DEFAULTS.get(shape, TASK_SHAPE_RUNTIME_DEFAULTS["single_surface"])
    expected_handoffs = int(needs.expected_handoffs)
    expected_rounds = int(needs.expected_rounds)
    child_agents = int(needs.child_agents)
    if shape != "single_surface":
        expected_handoffs = max(expected_handoffs, int(defaults["expected_handoffs"]))
        expected_rounds = max(expected_rounds, int(defaults["expected_rounds"]))
        child_agents = max(child_agents, int(defaults["child_agents"]))
    return TierProjection(
        task_shape=shape,
        tier=tier,
        bridge_mode=str(tier_config.get("bridge_mode", "none")),
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=bool(needs.shared_state or defaults["shared_state"]),
        signals=signals,
    )


def _normalize_text(task: str) -> str:
    return " ".join(str(task or "").lower().split())


def _text_signals_loop_runtime(text: str) -> bool:
    if "without loop" in text or "without looped" in text or "no loop" in text:
        return False
    tokens = (
        "verification loop",
        "generator critic loop",
        "checkpoint and resume",
        "resume from checkpoint",
        "continue next round",
        "multi-round",
        "iterate until",
        "until clean",
        "until pass",
    )
    return any(token in text for token in tokens)


def _text_signals_multi_step_runtime(text: str) -> bool:
    return any(
        token in text
        for token in (
            "multi-step",
            "shared state",
            "across phases",
            "across phase",
            "multiple passes",
            "phase by phase",
        )
    )


def _text_signals_single_handoff_runtime(text: str) -> bool:
    return any(token in text for token in ("delegate once", "one handoff", "single handoff", "single delegated pass"))


def _task_is_meta_only(text: str) -> bool:
    meta_tokens = ("acl-x", "aclx", "skill", "protocol", "port", "audit", "benchmark", "config")
    return any(token in text for token in meta_tokens) and not any(
        token in text for token in ("checkpoint", "resume", "shared state", "delegate once")
    )
