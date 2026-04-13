from __future__ import annotations

import json
from typing import Any

from aclx.adapters import ACLXAdapter


_adapter = ACLXAdapter()


def compress_phase_to_aclx(
    phase_name: str,
    phase_idx: int,
    gate_passed: bool,
    metrics: dict[str, Any] | None,
    next_phase: str | None,
) -> str:
    metric_payload = {
        "phase_name": phase_name,
        "phase_idx": phase_idx,
        "gate_passed": bool(gate_passed),
        "next_phase": next_phase or "",
        "metrics": metrics or {},
    }
    handoff = {
        "goal": [f"phase:{phase_name}"],
        "current_state": [
            f"phase_idx={phase_idx}",
            f"gate={'pass' if gate_passed else 'fail'}",
        ],
        "next_actions": [f"next_phase={next_phase}" if next_phase else "complete current plan"],
        "evidence": [json.dumps(metric_payload, ensure_ascii=True, sort_keys=True)],
        "priority": 1,
        "certainty": 0.9 if gate_passed else 0.45,
        "scope": f"phase:{phase_idx}",
        "source": "ctx.snapshot",
    }
    return _adapter.handoff_obj_to_aclx(handoff, mode="c")
