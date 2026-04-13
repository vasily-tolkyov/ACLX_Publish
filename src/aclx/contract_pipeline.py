from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .checkpoint_state import CheckpointState
from .contract import TaskContract
from .contract_normalizer import normalize_task_to_contract
from .project_adapters import ProjectContext, build_project_context


def normalize_items(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def coerce_contract(value: TaskContract | dict[str, Any] | None) -> TaskContract | None:
    if isinstance(value, TaskContract):
        return value
    if isinstance(value, dict):
        return TaskContract.from_dict(dict(value))
    return None


def coerce_checkpoint(value: CheckpointState | dict[str, Any] | None) -> CheckpointState | None:
    if isinstance(value, CheckpointState):
        return value
    if isinstance(value, dict):
        return CheckpointState.from_dict(dict(value))
    return None


def merge_items(primary: list[str] | None, fallback: list[str] | tuple[str, ...] | None) -> list[str]:
    return normalize_items(list(primary or []) + list(fallback or []))


class ContractResumeMismatch(RuntimeError):
    pass


@dataclass(slots=True)
class ContractResolution:
    contract: TaskContract
    required_artifacts: list[str]
    acceptance_contract: list[str]
    stop_conditions: list[str]
    next_actions: list[str]
    scope_in: list[str]
    scope_out: list[str]
    inputs: list[str]
    project_context: ProjectContext | None = None
    checkpoint_state: CheckpointState | None = None


def resolve_task_contract(
    task_description: str,
    *,
    project_root: str | Path | None = None,
    contract: TaskContract | dict[str, Any] | None = None,
    required_artifacts: list[str] | None = None,
    acceptance_contract: list[str] | None = None,
    stop_conditions: list[str] | None = None,
    next_actions: list[str] | None = None,
    scope_in: list[str] | None = None,
    scope_out: list[str] | None = None,
    inputs: list[str] | None = None,
    expected_handoffs: int = 0,
    expected_rounds: int = 1,
    child_agents: int = 0,
    shared_state: bool | None = None,
    checkpointable: bool | None = None,
    resumable: bool | None = None,
    loop_heavy: bool | None = None,
    metadata: dict[str, Any] | None = None,
    checkpoint: CheckpointState | dict[str, Any] | None = None,
    active_phase: str | None = None,
    runtime_tier: str | None = None,
    build_context: bool = True,
    request_supplies_contract_override: bool | None = None,
) -> ContractResolution:
    root = Path(project_root) if project_root is not None else None
    checkpoint_state = coerce_checkpoint(checkpoint)
    task_text = str(task_description or "").strip()
    if not task_text and checkpoint_state is not None:
        task_text = str(checkpoint_state.task_description or "").strip()
    requested_outputs = normalize_items(required_artifacts)
    requested_acceptance = normalize_items(acceptance_contract)
    requested_stop = normalize_items(stop_conditions)
    requested_next = normalize_items(next_actions)
    requested_scope_in = normalize_items(scope_in)
    requested_scope_out = normalize_items(scope_out)
    requested_inputs = normalize_items(inputs)
    requested_shared_state = _default_shared_state(
        shared_state=shared_state,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        checkpointable=checkpointable,
        resumable=resumable,
        loop_heavy=loop_heavy,
    )
    provided_contract = coerce_contract(contract)
    requested_contract = _build_base_contract(
        task_text,
        root=root,
        provided_contract=provided_contract,
        required_artifacts=requested_outputs,
        acceptance_contract=requested_acceptance,
        stop_conditions=requested_stop,
        next_actions=requested_next,
        scope_in=requested_scope_in,
        scope_out=requested_scope_out,
        inputs=requested_inputs,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=requested_shared_state,
        checkpointable=checkpointable,
        resumable=resumable,
        loop_heavy=loop_heavy,
        metadata=metadata,
    )
    normalized_outputs = merge_items(requested_outputs, checkpoint_state.required_artifacts if checkpoint_state is not None else None)
    normalized_acceptance = merge_items(
        requested_acceptance,
        checkpoint_state.acceptance_contract if checkpoint_state is not None else None,
    )
    normalized_stop = merge_items(requested_stop, checkpoint_state.stop_conditions if checkpoint_state is not None else None)
    normalized_next = merge_items(requested_next, checkpoint_state.next_actions if checkpoint_state is not None else None)
    normalized_scope_in = requested_scope_in
    normalized_scope_out = requested_scope_out
    normalized_inputs = requested_inputs
    shared_state_flag = _default_shared_state(
        shared_state=shared_state,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        checkpointable=checkpointable,
        resumable=resumable,
        loop_heavy=loop_heavy,
    )
    resolved_contract = _build_base_contract(
        task_text,
        root=root,
        provided_contract=provided_contract,
        required_artifacts=normalized_outputs,
        acceptance_contract=normalized_acceptance,
        stop_conditions=normalized_stop,
        next_actions=normalized_next,
        scope_in=normalized_scope_in,
        scope_out=normalized_scope_out,
        inputs=normalized_inputs,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=shared_state_flag,
        checkpointable=checkpointable,
        resumable=resumable,
        loop_heavy=loop_heavy,
        metadata=metadata,
    )
    request_supplies_contract = (
        bool(request_supplies_contract_override)
        if request_supplies_contract_override is not None
        else _request_supplies_contract(
            task_description=task_text,
            active_phase=active_phase,
            contract=provided_contract,
            required_artifacts=requested_outputs,
            acceptance_contract=requested_acceptance,
            stop_conditions=requested_stop,
            next_actions=requested_next,
            scope_in=requested_scope_in,
            scope_out=requested_scope_out,
            inputs=requested_inputs,
        )
    )
    if checkpoint_state is not None:
        _assert_checkpoint_tier_compatibility(checkpoint_state, runtime_tier)
        checkpoint_hash = _checkpoint_contract_hash(checkpoint_state)
        if request_supplies_contract and checkpoint_hash and checkpoint_hash != requested_contract.contract_hash():
            raise ContractResumeMismatch(
                "Checkpoint contract mismatch: the current resume request describes a different task contract."
            )
        if checkpoint_state.contract is not None:
            resolved_contract = checkpoint_state.contract.merge_missing(resolved_contract)
    project_context = (
        build_project_context(
            root or Path("."),
            resolved_contract,
            checkpoint=checkpoint_state.to_dict() if checkpoint_state is not None else None,
        )
        if build_context
        else None
    )
    if project_context is not None:
        if (
            checkpoint_state is not None
            and checkpoint_state.adapter_id
            and checkpoint_state.adapter_id != project_context.adapter_id
        ):
            raise ContractResumeMismatch(
                "Checkpoint adapter mismatch: the current resume request resolved to a different project adapter stack."
            )
        resolved_contract = project_context.contract
    resolved_outputs = merge_items(normalized_outputs, resolved_contract.output_artifacts)
    resolved_acceptance = merge_items(
        normalized_acceptance,
        resolved_contract.acceptance_rules or resolved_contract.exactness_rules,
    )
    resolved_stop = merge_items(normalized_stop, resolved_contract.stop_conditions)
    resolved_next = merge_items(normalized_next, resolved_contract.next_actions)
    resolved_scope_in = merge_items(normalized_scope_in, resolved_contract.scope_in)
    resolved_scope_out = merge_items(normalized_scope_out, resolved_contract.scope_out)
    resolved_inputs = merge_items(normalized_inputs, resolved_contract.input_artifacts)
    return ContractResolution(
        contract=resolved_contract,
        required_artifacts=resolved_outputs,
        acceptance_contract=resolved_acceptance,
        stop_conditions=resolved_stop,
        next_actions=resolved_next,
        scope_in=resolved_scope_in,
        scope_out=resolved_scope_out,
        inputs=resolved_inputs,
        project_context=project_context,
        checkpoint_state=checkpoint_state,
    )


def _build_base_contract(
    task_text: str,
    *,
    root: Path | None,
    provided_contract: TaskContract | None,
    required_artifacts: list[str],
    acceptance_contract: list[str],
    stop_conditions: list[str],
    next_actions: list[str],
    scope_in: list[str],
    scope_out: list[str],
    inputs: list[str],
    expected_handoffs: int,
    expected_rounds: int,
    child_agents: int,
    shared_state: bool,
    checkpointable: bool | None,
    resumable: bool | None,
    loop_heavy: bool | None,
    metadata: dict[str, Any] | None,
) -> TaskContract:
    normalized_contract = normalize_task_to_contract(
        task_text,
        project_root=root,
        required_artifacts=required_artifacts,
        acceptance_contract=acceptance_contract,
        stop_conditions=stop_conditions,
        next_actions=next_actions,
        scope_in=scope_in,
        scope_out=scope_out,
        inputs=inputs,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=shared_state,
        checkpointable=checkpointable,
        resumable=resumable,
        loop_heavy=loop_heavy,
        metadata=metadata,
    )
    return normalized_contract if provided_contract is None else provided_contract.merge_missing(normalized_contract)


def _request_supplies_contract(
    *,
    task_description: str,
    active_phase: str | None,
    contract: TaskContract | None,
    required_artifacts: list[str],
    acceptance_contract: list[str],
    stop_conditions: list[str],
    next_actions: list[str],
    scope_in: list[str],
    scope_out: list[str],
    inputs: list[str],
) -> bool:
    if contract is not None:
        return True
    if any((required_artifacts, acceptance_contract, stop_conditions, next_actions, scope_in, scope_out, inputs)):
        return True
    return _task_text_supplies_contract(task_description, active_phase=active_phase)


def _task_text_supplies_contract(task_description: str, *, active_phase: str | None) -> bool:
    text = str(task_description or "").strip()
    if not text:
        return False
    lowered = " ".join(text.lower().split())
    if str(active_phase or "").lower() != "resume":
        return True
    semantic_tokens = (
        "`",
        "/",
        "\\",
        ".py",
        ".md",
        ".txt",
        ".rst",
        " read ",
        " write ",
        " fix ",
        " repair ",
        " rewrite ",
        " update ",
        " inspect ",
        " review ",
        " summarize ",
        " compare ",
        " implement ",
        " delegate ",
    )
    if any(token in f" {lowered} " for token in semantic_tokens):
        return True
    return not lowered.startswith(("resume", "continue"))


def _checkpoint_contract_hash(checkpoint_state: CheckpointState) -> str:
    if checkpoint_state.contract_hash:
        return str(checkpoint_state.contract_hash)
    if checkpoint_state.contract is not None:
        return checkpoint_state.contract.contract_hash()
    return ""


def _assert_checkpoint_tier_compatibility(
    checkpoint_state: CheckpointState,
    runtime_tier: str | None,
) -> None:
    current_tier = str(runtime_tier or "").strip().lower()
    checkpoint_tier = str(checkpoint_state.runtime_tier or "").strip().lower()
    if current_tier and checkpoint_tier and current_tier != checkpoint_tier:
        raise ContractResumeMismatch(
            f"Checkpoint tier mismatch: requested {current_tier}, checkpoint stores {checkpoint_tier}."
        )


def _default_shared_state(
    *,
    shared_state: bool | None,
    expected_handoffs: int,
    expected_rounds: int,
    child_agents: int,
    checkpointable: bool | None,
    resumable: bool | None,
    loop_heavy: bool | None,
) -> bool:
    if shared_state is not None:
        return bool(shared_state)
    return bool(
        int(expected_handoffs or 0) > 0
        or int(expected_rounds or 1) > 1
        or int(child_agents or 0) > 0
        or checkpointable
        or resumable
        or loop_heavy
    )
