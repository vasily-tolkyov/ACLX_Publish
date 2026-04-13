from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from aclx.adapters import ACLXAdapter
from aclx.checkpoint_state import CheckpointState
from aclx.contract import TaskContract
from aclx.contract_pipeline import ContractResumeMismatch, merge_items, normalize_items, resolve_task_contract
from aclx.project_adapters import ResumeDelta

from .builder import build_context
from .policy import DEFAULT_CONSTRAINTS, PolicySpec, generate_policy_file
from .snapshot import SnapshotStore
from .tool_summary import ToolSummary, summarize_bash, summarize_file_read


DEFAULT_CONFIG = {
    "hard_token_limit": 8000,
    "layer0_budget": 600,
    "layer1_budget": 2500,
    "layer2_budget": 800,
    "tool_summary_ratio_target": 5.0,
    "tool_summary_keep": 3,
    "snapshot_dir": ".aclx_runtime/snapshots",
    "checkpoint_dir": ".aclx_runtime/checkpoints",
    "policy_file": ".aclx_runtime/policy_active.aclx",
    "tiers": {
        "t0": {
            "emit_header": True,
            "include_archive": False,
            "write_checkpoint": False,
            "write_policy": False,
            "use_aclx": False,
            "tool_summary_keep": 0,
        },
        "t1": {
            "emit_header": False,
            "include_archive": False,
            "write_checkpoint": False,
            "write_policy": False,
            "use_aclx": True,
            "tool_summary_keep": 0,
        },
        "t2": {
            "emit_header": True,
            "include_archive": False,
            "write_checkpoint": False,
            "write_policy": True,
            "use_aclx": True,
            "tool_summary_keep": 1,
            "read_hint_keep": 2,
            "validator_plan_keep": 2,
            "emit_artifact_manifest": False,
            "emit_validated_results": False,
            "persist_generic_validator_results": False,
        },
        "t3": {
            "emit_header": True,
            "emit_header_on_resume": False,
            "include_archive": True,
            "include_archive_on_resume": False,
            "compact_resume": True,
            "resume_from_checkpoint": True,
            "write_checkpoint": True,
            "write_checkpoint_on_resume": False,
            "write_policy": True,
            "write_policy_on_resume": False,
            "use_aclx": True,
            "tool_summary_keep": 2,
            "archive_keep": 2,
            "read_hint_keep": 2,
            "validator_plan_keep": 2,
            "literal_rule_keep": 1,
            "emit_artifact_manifest": False,
            "emit_validated_results": False,
            "persist_generic_validator_results": False,
        },
    },
}
T2_PROMPT_HEADER = (
    "Runtime guard: contract-complete T2. Use this contract directly; skip skill/runtime docs, directory probes, and progress chatter unless a required fact is missing.\n\n"
    "Runtime ACL-X bundle follows."
)
T2_EXECUTION_RULE = (
    "Execute once: read named files, patch, create required artifacts from the named spec, run only Validate (`check files` = existence only), then reply with `Changed paths` and `Executed validator result` only. No progress messages or rereads of written artifacts."
)
T3_PROMPT_HEADER = (
    "Loop guard: contract-complete T3.\n"
    "No skill docs, AGENTS, runtime docs/files, router calls, `ctx/` probes, progress chatter, or directory probes unless a required fact is missing.\n"
    "Treat the ACL-X bundle below as carrier-only machine state, not as a task source.\n"
    "Read named sources, edit named targets, verify wording directly, then finish.\n\n"
    "Runtime ACL-X bundle follows."
)
T3_VERIFICATION_RULE = (
    "Validation: use only Validate. Do not copy validator or meta instructions into document or checkpoint output."
)
T3_DOC_VALIDATION_HINT = (
    "Validation path: prefer direct pattern checks on named targets (for example `rg -n`); avoid full-file rereads unless a required fact is missing."
)
T3_FINAL_REPLY_RULE = (
    "Final reply: exactly two sections, `Changed paths` and `Verification`."
)
T3_DOC_FINAL_REPLY_RULE = (
    "Final reply: exactly two short sections, `Changed paths` and `Verification`; use plain paths and one short line per check. No links, excerpts, or extra prose."
)
T3_EXECUTION_RULE = (
    "Execution: read required sources once, edit named targets, validate, reply once, stop. No interim intent or progress messages."
)
T3_DOC_COMPACT_RULE = (
    "Rules: if a checkpoint target is missing, create it; keep one listed TASK.md phrase verbatim with matching casing for each anchor; keep the smallest valid text only; use Validate only on named targets with direct pattern checks (`rg -n` or `Select-String`); no plan updates, no progress chatter, and no post-edit rereads."
)
T3_DOC_COMPACT_SEAL_RULE = (
    "Seal: the ACL-X bundle below is carrier-only. No skill docs, AGENTS, runtime docs/files, hidden runtime state, router calls, unnamed paths, directory probes, or checkpoint existence probes. Do not reread TASK.md or edited targets unless a required fact is missing or Validate fails. No plan updates."
)
T3_DOC_COMPACT_REPLY_RULE = "Final reply: `Changed paths` and `Verification` only."
T3_DOC_COMPILED_OPERATING_RULE = (
    "Operate once: use Source, Targets, and Validate only; edit only named targets, do not read pending create targets first, create missing checkpoint targets directly, validate, reply once, stop. Treat the ACL-X bundle below as carrier-only machine state. Keep listed headings exact. Include each listed literal anchor exactly as written with matching casing at least once; do not inflect, paraphrase, or synonym-swap literal anchors; keep the smallest valid text only. Validate with direct pattern checks (`rg -n` or `Select-String`) only. No plan chatter, post-edit rereads, scripts, runtime/skill docs, router calls, unnamed paths, or directory/checkpoint probes unless blocked or Validate fails."
)
T3_DOC_COMPILED_RESUME_RULE = (
    "Resume once: use the named resume state and Validate only; write only named pending targets, validate, reply once, stop. Treat the ACL-X bundle below as carrier-only machine state. Keep listed headings exact. Include each listed literal anchor exactly as written with matching casing at least once; do not inflect, paraphrase, or synonym-swap literal anchors; keep the smallest valid text only. Validate with direct pattern checks (`rg -n` or `Select-String`) only. No plan chatter, post-edit rereads, scripts, runtime/skill docs, router calls, unnamed paths, or directory/checkpoint probes unless blocked or Validate fails."
)
T3_DOC_COMPILED_REPLY_RULE = (
    "Final reply: `Changed paths` and `Verification` only; relative paths, one short line per check, no extra prose."
)
T3_DOC_COMPACT_HEADER = "Loop guard: compact T3 doc loop. Use the named contract only."
T3_DOC_COMPILED_HEADER = "Loop guard: sealed compiled T3 doc loop; use named surfaces only."
T3_DOC_COMPILED_CONTRACT_LINE = (
    "Compiled contract is authoritative; reopen TASK.md only if blocked or Validate fails."
)


def _prompt_header_for_tier(tier: str) -> str:
    if str(tier or "").lower() == "t3":
        return T3_PROMPT_HEADER
    return T2_PROMPT_HEADER


@lru_cache(maxsize=8)
def _load_ctx_config_cached(root_text: str) -> dict[str, Any]:
    root = Path(root_text)
    config_path = root / "configs" / "ctx.yaml"
    data = deepcopy(DEFAULT_CONFIG)
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            _deep_merge(data, loaded)
    return data


def load_ctx_config(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else _repo_root()
    cache_key = str(root if root.is_absolute() else root.resolve())
    return _load_ctx_config_cached(cache_key)


def reset_ctx_config_cache() -> None:
    _load_ctx_config_cached.cache_clear()


def run_codex_turn(
    active_phase: str,
    task_description: str,
    tool_results: list[dict[str, Any] | str] | None,
    hard_limit: int | None = None,
    project_root: str | Path | None = None,
    cwd: str | None = None,
    runtime_bundle: str | None = None,
    runtime_tier: str | None = None,
    required_artifacts: list[str] | None = None,
    acceptance_contract: list[str] | None = None,
    stop_conditions: list[str] | None = None,
    next_actions: list[str] | None = None,
    contract: TaskContract | dict[str, Any] | None = None,
) -> str:
    root = Path(project_root) if project_root is not None else _repo_root()
    config = load_ctx_config(root)
    tier = str(runtime_tier or "t0").lower()
    tier_cfg = (config.get("tiers") or {}).get(tier) or {}
    required_artifacts = normalize_items(required_artifacts)
    acceptance_contract = normalize_items(acceptance_contract)
    stop_conditions = normalize_items(stop_conditions)
    next_actions = normalize_items(next_actions)
    request_resolution = resolve_task_contract(
        task_description,
        project_root=root,
        contract=contract,
        required_artifacts=required_artifacts,
        acceptance_contract=acceptance_contract,
        stop_conditions=stop_conditions,
        next_actions=next_actions,
        checkpointable=tier == "t3",
        resumable=active_phase == "resume" or tier == "t3",
        loop_heavy=tier == "t3",
        active_phase=active_phase,
        runtime_tier=tier,
    )
    task_contract = request_resolution.contract
    required_artifacts = request_resolution.required_artifacts
    acceptance_contract = request_resolution.acceptance_contract
    stop_conditions = request_resolution.stop_conditions
    next_actions = request_resolution.next_actions
    request_supplies_contract = _resume_request_supplies_contract(
        task_description=task_description,
        contract=contract,
        required_artifacts=required_artifacts,
        acceptance_contract=acceptance_contract,
        stop_conditions=stop_conditions,
        next_actions=next_actions,
    )
    keep = int(tier_cfg.get("tool_summary_keep", config.get("tool_summary_keep", 3)))
    use_aclx = bool(tier_cfg.get("use_aclx", True))
    emit_header = bool(tier_cfg.get("emit_header", True))
    include_archive = bool(tier_cfg.get("include_archive", active_phase != "resume"))
    write_checkpoint = bool(tier_cfg.get("write_checkpoint", True))
    write_policy = bool(tier_cfg.get("write_policy", True))
    if active_phase != "resume":
        if not use_aclx and not emit_header and not include_archive and not write_checkpoint and not write_policy and keep <= 0:
            return task_description.strip()
    if active_phase == "resume":
        emit_header = bool(tier_cfg.get("emit_header_on_resume", emit_header))
        include_archive = bool(tier_cfg.get("include_archive_on_resume", include_archive))
        write_checkpoint = bool(tier_cfg.get("write_checkpoint_on_resume", write_checkpoint))
        write_policy = bool(tier_cfg.get("write_policy_on_resume", write_policy))
    resume_from_checkpoint = (
        active_phase == "resume" and runtime_bundle is None and bool(tier_cfg.get("resume_from_checkpoint", False))
    )
    if not use_aclx and not emit_header and not include_archive and not write_checkpoint and not write_policy and keep <= 0:
        return task_description.strip()
    checkpoints = root / str(config["checkpoint_dir"]) if (resume_from_checkpoint or write_checkpoint) else None
    checkpoint_state: dict[str, Any] | None = None
    checkpoint_model: CheckpointState | None = None
    checkpoint_mismatches: list[str] = []
    resume_contract = task_contract if request_supplies_contract else None
    if resume_from_checkpoint:
        checkpoint_state = _load_checkpoint_state(
            checkpoints=checkpoints or (root / str(config["checkpoint_dir"])),
            tier=tier,
            policy_path=root / str(config["policy_file"]),
        )
        if checkpoint_state:
            checkpoint_model = CheckpointState.from_dict(checkpoint_state)
            checkpoint_mismatches = (
                _checkpoint_request_mismatches(
                    checkpoint_model,
                    contract=task_contract,
                    adapter_id=request_resolution.project_context.adapter_id if request_resolution.project_context is not None else "",
                    runtime_tier=tier,
                )
                if request_supplies_contract
                else []
            )
            if not checkpoint_mismatches:
                checkpoint_task_description = str(checkpoint_state.get("task_description") or "").strip()
                runtime_bundle = str(checkpoint_state.get("runtime_bundle") or "").strip() or runtime_bundle
                if not request_supplies_contract and checkpoint_task_description:
                    task_description = checkpoint_task_description
                else:
                    task_description = str(task_description or "").strip() or checkpoint_task_description
                if request_supplies_contract:
                    required_artifacts = _merge_contract_items(required_artifacts, checkpoint_model.required_artifacts)
                    acceptance_contract = _merge_contract_items(acceptance_contract, checkpoint_model.acceptance_contract)
                    stop_conditions = _merge_contract_items(stop_conditions, checkpoint_model.stop_conditions)
                    next_actions = _merge_contract_items(next_actions, checkpoint_model.next_actions)
            else:
                raise RuntimeError(
                    "Checkpoint contract mismatch: "
                    + ", ".join(checkpoint_mismatches)
                )
    try:
        resolution = resolve_task_contract(
            task_description,
            project_root=root,
            contract=resume_contract,
            required_artifacts=required_artifacts,
            acceptance_contract=acceptance_contract,
            stop_conditions=stop_conditions,
            next_actions=next_actions,
            checkpointable=tier == "t3",
            resumable=active_phase == "resume" or tier == "t3",
            loop_heavy=tier == "t3",
            checkpoint=checkpoint_model,
            active_phase=active_phase,
            runtime_tier=tier,
            request_supplies_contract_override=request_supplies_contract,
        )
    except ContractResumeMismatch as exc:
        if request_supplies_contract:
            raise RuntimeError(str(exc)) from exc
        checkpoint_mismatches = _fallback_checkpoint_mismatches(checkpoint_mismatches, exc)
        runtime_bundle = None
        checkpoint_state = None
        checkpoint_model = None
        resolution = resolve_task_contract(
            task_description,
            project_root=root,
            contract=resume_contract,
            required_artifacts=required_artifacts,
            acceptance_contract=acceptance_contract,
            stop_conditions=stop_conditions,
            next_actions=next_actions,
            checkpointable=tier == "t3",
            resumable=active_phase == "resume" or tier == "t3",
            loop_heavy=tier == "t3",
            active_phase=active_phase,
            runtime_tier=tier,
            request_supplies_contract_override=request_supplies_contract,
        )
    task_contract = resolution.contract
    required_artifacts = resolution.required_artifacts
    acceptance_contract = resolution.acceptance_contract
    stop_conditions = resolution.stop_conditions
    next_actions = resolution.next_actions
    checkpoint_model = resolution.checkpoint_state or checkpoint_model
    project_context = resolution.project_context
    if project_context is None:
        raise RuntimeError("Contract resolution must provide project context for ctx.session.")
    read_hint_keep = int(tier_cfg.get("read_hint_keep", 2 if tier in {"t2", "t3"} else 4) or 0)
    validator_plan_keep = int(tier_cfg.get("validator_plan_keep", 2 if tier in {"t2", "t3"} else 4) or 0)
    literal_rule_keep = int(tier_cfg.get("literal_rule_keep", 2 if tier == "t3" else 0) or 0)
    emit_artifact_manifest = bool(tier_cfg.get("emit_artifact_manifest", tier not in {"t2", "t3"}))
    emit_validated_results = bool(tier_cfg.get("emit_validated_results", False))
    persist_generic_validator_results = bool(tier_cfg.get("persist_generic_validator_results", True))
    read_hints = list(project_context.read_hints)
    validator_plan = list(project_context.validator_plan)
    artifact_manifest = list(project_context.artifact_manifest or required_artifacts)
    resume_delta = project_context.resume_delta
    display_pending_artifacts = _display_paths(resume_delta.pending_artifacts, root=root)
    display_required_artifacts = _display_paths(required_artifacts, root=root)
    task_md_authoritative = tier == "t3" and _task_md_contract_source(task_contract)
    compact_t3_doc = _is_t3_generic_doc_compaction(
        tier=tier,
        task_md_authoritative=task_md_authoritative,
        required_artifacts=display_required_artifacts,
    )
    compiled_t3_doc_contract = _is_t3_compiled_doc_contract_complete(
        tier=tier,
        task_md_authoritative=task_md_authoritative,
        exactness_rules=list(task_contract.exactness_rules),
        required_artifacts=display_required_artifacts,
    )
    display_read_hints = _display_read_hints(
        read_hints,
        root=root,
        keep=read_hint_keep,
        task_description=task_description,
        validator_plan=validator_plan,
    )
    if tier == "t3" and task_md_authoritative and not compiled_t3_doc_contract:
        display_read_hints = _ensure_task_md_read_hint(display_read_hints, keep=read_hint_keep)
    if compact_t3_doc:
        display_read_hints = _compact_t3_read_hints(
            display_read_hints,
            required_artifacts=display_required_artifacts,
            compiled_authoritative=compiled_t3_doc_contract,
        )
        if compiled_t3_doc_contract:
            display_read_hints = _filter_compiled_t3_doc_preread_targets(
                display_read_hints,
                pending_artifacts=display_pending_artifacts,
            )
    display_validator_plan = _display_validator_plan(
        validator_plan,
        root=root,
        keep=validator_plan_keep,
        read_hints=display_read_hints,
        required_artifacts=display_required_artifacts,
        tier=tier,
        task_md_authoritative=task_md_authoritative,
        collapse_implied_targets=False,
        compact_doc_loop=compact_t3_doc,
    )
    display_literal_rules = _display_literal_rules(
        exactness_rules=list(task_contract.exactness_rules),
        acceptance_contract=acceptance_contract,
        keep=(
            min(8, max(1, literal_rule_keep + 6))
            if compact_t3_doc
            else literal_rule_keep
        ),
    )
    display_doc_shape_hint = (
        _compact_t3_doc_shape_hint(
            list(task_contract.exactness_rules),
            required_artifacts=display_required_artifacts,
        )
        if compact_t3_doc
        else ""
    )
    display_doc_roles = (
        _compact_role_anchors(list(task_contract.exactness_rules), keep=3)
        if compiled_t3_doc_contract
        else []
    )
    display_artifact_manifest = _display_artifact_manifest(
        artifact_manifest,
        display_required_artifacts,
        emit=emit_artifact_manifest,
        root=root,
    )
    validator_results = _collect_validator_results(tool_results or [], validator_plan, checkpoint_model)
    stored_validator_results = _checkpoint_validator_results(
        validator_results,
        persist_generic=persist_generic_validator_results,
    )
    display_resume_read_targets = _display_read_hints(
        resume_delta.read_targets,
        root=root,
        keep=read_hint_keep,
        task_description=task_description,
        validator_plan=resume_delta.pending_validations,
    )
    if compact_t3_doc and compiled_t3_doc_contract:
        display_resume_read_targets = _filter_compiled_t3_doc_preread_targets(
            display_resume_read_targets,
            pending_artifacts=display_pending_artifacts,
        )
    display_resume_delta = ResumeDelta(
        pending_artifacts=display_pending_artifacts,
        pending_validations=_display_validator_plan(
            resume_delta.pending_validations,
            root=root,
            keep=validator_plan_keep,
            read_hints=display_read_hints,
            required_artifacts=display_required_artifacts,
            tier=tier,
            task_md_authoritative=task_md_authoritative,
            compact_doc_loop=compact_t3_doc,
        ),
        read_targets=display_resume_read_targets,
        carryover_items=_normalize_items(resume_delta.carryover_items),
    )
    unresolved_items = _build_unresolved_items(
        stop_conditions=stop_conditions,
        resume_delta=resume_delta,
        checkpoint_mismatches=checkpoint_mismatches,
    )
    if runtime_bundle and active_phase == "resume" and bool(tier_cfg.get("compact_resume", False)) and tier == "t3":
        return _render_t3_resume_prompt(
            task_description=task_description,
            runtime_bundle=runtime_bundle,
            required_artifacts=display_required_artifacts,
            acceptance_contract=acceptance_contract,
            stop_conditions=stop_conditions,
            validator_plan=display_resume_delta.pending_validations,
            validator_results=_semantic_validator_results(validator_results),
            resume_delta=display_resume_delta,
            checkpoint_mismatches=checkpoint_mismatches,
            emit_header=emit_header,
            emit_validated_results=emit_validated_results,
            compact_doc_loop=compact_t3_doc,
            compiled_doc_contract=compiled_t3_doc_contract,
        )
    if runtime_bundle and use_aclx and not emit_header and not include_archive and not write_checkpoint and not write_policy:
        return runtime_bundle
    if not use_aclx:
        return task_description.strip()
    archive_keep = tier_cfg.get("archive_keep")
    layer0_budget = int(tier_cfg.get("layer0_budget", config.get("layer0_budget", 600)))
    layer1_budget = int(tier_cfg.get("layer1_budget", config.get("layer1_budget", 2500)))
    layer2_budget = int(tier_cfg.get("layer2_budget", config.get("layer2_budget", 800)))
    if write_checkpoint:
        checkpoint_root = checkpoints or (root / str(config["checkpoint_dir"]))
        checkpoint_root.mkdir(parents=True, exist_ok=True)
    snapshot_store = SnapshotStore(root, str(config["snapshot_dir"])) if include_archive else None
    if write_policy:
        generate_policy_file(root, DEFAULT_CONSTRAINTS, str(config["policy_file"]))
    summaries = _summarize_tool_results(tool_results or [], keep=keep) if keep > 0 else []
    adapter = ACLXAdapter()
    if runtime_bundle:
        active_bundle = runtime_bundle
    else:
        snapshot_count = _snapshot_count(snapshot_store)
        if tier == "t3":
            bundle_next_actions = next_actions or ["resume_loop" if active_phase == "resume" else "continue_loop"]
            evidence = [_summary_text(summary, compact=True) for summary in summaries]
        else:
            bundle_next_actions = next_actions or [summary.summary for summary in summaries] or ["continue current phase"]
            evidence = [_summary_text(summary, compact=False) for summary in summaries]
        active_bundle = adapter.handoff_obj_to_aclx(
            {
                "goal": [task_description],
                "current_state": [
                    f"phase={active_phase}",
                    f"snapshots={snapshot_count}",
                ],
                "next_actions": bundle_next_actions,
                "evidence": evidence,
                "priority": 1,
                "certainty": 0.9,
                "scope": active_phase,
                "source": "ctx.session",
            },
            mode="c",
        )
    if tier == "t2":
        payload = _render_t2_prompt(
            task_description=task_description,
            runtime_bundle=active_bundle,
            required_artifacts=display_required_artifacts,
            acceptance_contract=acceptance_contract,
            exactness_rules=list(task_contract.exactness_rules),
            stop_conditions=stop_conditions,
            next_actions=next_actions,
            read_hints=display_read_hints,
            validator_plan=display_validator_plan,
            artifact_manifest=display_artifact_manifest,
            emit_header=emit_header,
        )
    elif tier == "t3":
        if active_phase == "resume":
            payload = _render_t3_resume_prompt(
                task_description=task_description,
                runtime_bundle=active_bundle,
                required_artifacts=display_required_artifacts,
                acceptance_contract=acceptance_contract,
                stop_conditions=stop_conditions,
                validator_plan=display_resume_delta.pending_validations,
                validator_results=_semantic_validator_results(validator_results),
                resume_delta=display_resume_delta,
                checkpoint_mismatches=checkpoint_mismatches,
                emit_header=emit_header,
                emit_validated_results=emit_validated_results,
                compact_doc_loop=compact_t3_doc,
                compiled_doc_contract=compiled_t3_doc_contract,
            )
        else:
            payload = _render_t3_prompt(
                task_description=task_description,
                runtime_bundle=active_bundle,
                required_artifacts=display_required_artifacts,
                pending_artifacts=display_resume_delta.pending_artifacts,
                acceptance_contract=acceptance_contract,
                stop_conditions=stop_conditions,
                next_actions=next_actions,
                read_hints=display_read_hints,
                validator_plan=display_validator_plan,
                artifact_manifest=display_artifact_manifest,
                exactness_rules=display_literal_rules,
                doc_shape_hint=display_doc_shape_hint,
                doc_roles=display_doc_roles,
                task_md_authoritative=task_md_authoritative,
                emit_header=emit_header,
                compact_doc_loop=compact_t3_doc,
                compiled_doc_contract=compiled_t3_doc_contract,
            )
    elif not emit_header and not include_archive:
        payload = active_bundle
    else:
        context = build_context(
            active_phase=active_phase,
            active_content=active_bundle,
            project_root=root,
            hard_limit=int(hard_limit or config["hard_token_limit"]),
            include_archive=include_archive,
            layer0_budget=layer0_budget,
            layer1_budget=layer1_budget,
            layer2_budget=layer2_budget,
            archive_keep=int(archive_keep) if archive_keep is not None else None,
            policy_file=str(config["policy_file"]),
            snapshot_dir=str(config["snapshot_dir"]),
        )
        sections = [context]
        if emit_header:
            sections.insert(0, _prompt_header_for_tier(tier))
        payload = "\n\n".join(part for part in sections if part)
    if write_checkpoint:
        checkpoint_path = (checkpoints or (root / str(config["checkpoint_dir"]))) / f"{active_phase}.json"
        checkpoint_text = json.dumps(
            CheckpointState(
                active_phase=active_phase,
                task_description=task_description,
                runtime_bundle=active_bundle,
                required_artifacts=required_artifacts,
                acceptance_contract=acceptance_contract,
                stop_conditions=stop_conditions,
                next_actions=next_actions,
                tool_summaries=[summary.to_text() for summary in summaries],
                policy_hash=_file_sha256(root / str(config["policy_file"])),
                runtime_tier=tier,
                contract=task_contract,
                contract_hash=task_contract.contract_hash(),
                adapter_id=project_context.adapter_id,
                artifact_manifest=artifact_manifest,
                validator_plan=validator_plan,
                validator_results=stored_validator_results,
                unresolved_items=unresolved_items,
                resume_delta=resume_delta,
            ).to_dict(),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        if not checkpoint_path.exists() or checkpoint_path.read_text(encoding="utf-8") != checkpoint_text:
            checkpoint_path.write_text(checkpoint_text, encoding="utf-8")
    return payload


def record_gate(
    phase_name: str,
    phase_idx: int,
    gate_passed: bool,
    metrics: dict[str, Any] | None,
    next_phase: str | None,
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root) if project_root is not None else _repo_root()
    config = load_ctx_config(root)
    store = SnapshotStore(root, str(config["snapshot_dir"]))
    return store.write(phase_name, phase_idx, gate_passed, metrics, next_phase)


def check_constraint(target: str, action: str, project_root: str | Path | None = None) -> bool:
    root = Path(project_root) if project_root is not None else _repo_root()
    _ = load_ctx_config(root)
    spec = PolicySpec(list(DEFAULT_CONSTRAINTS))
    allowed, _reason = spec.validate_action(target, action)
    return allowed


def _summarize_tool_results(tool_results: list[dict[str, Any] | str], keep: int) -> list[ToolSummary]:
    if keep <= 0 or not tool_results:
        return []
    summaries = []
    for item in tool_results:
        if isinstance(item, str):
            summaries.append(ToolSummary(kind="generic", source="text", summary=item, reduction_ratio=1.0))
            continue
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or item.get("kind") or "")
        if item_type == "shell" or "command" in item:
            summaries.append(
                summarize_bash(
                    str(item.get("command") or ""),
                    str(item.get("stdout") or ""),
                    int(item.get("returncode", 0)),
                )
            )
            continue
        if "path" in item and "content" in item:
            summaries.append(summarize_file_read(str(item.get("path")), str(item.get("content") or "")))
            continue
    return summaries[:keep]


def _summary_text(summary: ToolSummary, *, compact: bool) -> str:
    if not compact:
        return summary.to_text()
    if summary.kind == "test" or summary.details.get("returncode", 0) != 0:
        return summary.to_text()
    return summary.summary


def _snapshot_count(snapshot_store: SnapshotStore | None) -> int:
    if snapshot_store is None:
        return 0
    return len(list(snapshot_store.snapshot_dir.glob("*.aclx")))


def _load_checkpoint_bundle(*, checkpoints: Path, tier: str, policy_path: Path) -> str | None:
    state = _load_checkpoint_state(checkpoints=checkpoints, tier=tier, policy_path=policy_path)
    if state is None:
        return None
    return str(state.get("runtime_bundle") or "").strip() or None


def _load_checkpoint_state(
    *,
    checkpoints: Path,
    tier: str,
    policy_path: Path,
) -> dict[str, Any] | None:
    checkpoint_roots = [checkpoints]
    root = policy_path.parent.parent if policy_path.parent != policy_path else _repo_root()
    legacy_checkpoints = root / "checkpoints"
    if legacy_checkpoints != checkpoints:
        checkpoint_roots.append(legacy_checkpoints)
    current_policy_hash = _file_sha256(policy_path)
    tier_mismatch_candidate: dict[str, Any] | None = None
    for checkpoint_root in checkpoint_roots:
        if not checkpoint_root.exists():
            continue
        rows = sorted(checkpoint_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not rows:
            continue
        for path in rows:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            bundle = str(data.get("runtime_bundle") or "").strip()
            if not bundle:
                continue
            stored_policy_hash = str(data.get("policy_hash") or "")
            if stored_policy_hash and current_policy_hash and stored_policy_hash != current_policy_hash:
                continue
            if str(data.get("runtime_tier") or "").lower() != tier:
                if tier_mismatch_candidate is None:
                    tier_mismatch_candidate = data
                continue
            return data
    return tier_mismatch_candidate


def _checkpoint_request_mismatches(
    checkpoint_state: CheckpointState,
    *,
    contract: TaskContract,
    adapter_id: str,
    runtime_tier: str,
) -> list[str]:
    mismatches: list[str] = []
    checkpoint_tier = str(checkpoint_state.runtime_tier or "").strip().lower()
    if checkpoint_tier and checkpoint_tier != str(runtime_tier or "").strip().lower():
        mismatches.append("runtime_tier")
    checkpoint_hash = str(checkpoint_state.contract_hash or (checkpoint_state.contract.contract_hash() if checkpoint_state.contract is not None else ""))
    if checkpoint_hash and checkpoint_hash != contract.contract_hash():
        mismatches.append("contract_hash")
    checkpoint_adapter_id = str(checkpoint_state.adapter_id or "").strip()
    if checkpoint_adapter_id and adapter_id and checkpoint_adapter_id != adapter_id:
        mismatches.append("adapter_id")
    return mismatches


def _resume_request_supplies_contract(
    *,
    task_description: str,
    contract: TaskContract | dict[str, Any] | None,
    required_artifacts: list[str],
    acceptance_contract: list[str],
    stop_conditions: list[str],
    next_actions: list[str],
) -> bool:
    if contract is not None:
        return True
    if any((required_artifacts, acceptance_contract, stop_conditions, next_actions)):
        return True
    text = " ".join(str(task_description or "").lower().split())
    if not text:
        return False
    semantic_tokens = ("`", "/", "\\", ".py", ".md", ".txt", ".rst", ".json", ".yaml", ".toml")
    if any(token in text for token in semantic_tokens):
        return True
    return not text.startswith(("resume", "continue"))


def _normalize_items(values: list[str] | None) -> list[str]:
    return normalize_items(values)


def _merge_contract_items(current: list[str], fallback: list[str] | None) -> list[str]:
    return merge_items(current, fallback or [])


def _resume_delta_unresolved_items(delta: ResumeDelta) -> list[str]:
    return [
        line
        for line in (
            _line("artifacts pending", delta.pending_artifacts),
            _line("validations pending", delta.pending_validations),
            _line("read before resume", delta.read_targets),
            _line("carry forward", delta.carryover_items),
        )
        if line
    ]


def _checkpoint_mismatch_items(checkpoint_mismatches: list[str] | None) -> list[str]:
    return [f"checkpoint mismatch: {item}" for item in _normalize_items(checkpoint_mismatches)]


def _collect_validator_results(
    tool_results: list[dict[str, Any] | str],
    validator_plan: list[str],
    checkpoint_state: CheckpointState | None,
) -> list[str]:
    persisted = _normalize_items(checkpoint_state.validator_results if checkpoint_state is not None else [])
    completed = _completed_validator_plans(persisted)
    observed = list(persisted)
    for plan in _normalize_items(validator_plan):
        if plan in completed:
            continue
        result = _match_validator_result(plan, tool_results)
        if not result:
            continue
        observed.append(result)
        if result.startswith("ok:"):
            completed.add(plan)
    observed = merge_items(observed, _generic_tool_validator_results(tool_results))
    return _normalize_items(observed)


def _build_unresolved_items(
    *,
    stop_conditions: list[str],
    resume_delta: ResumeDelta,
    checkpoint_mismatches: list[str] | None = None,
) -> list[str]:
    unresolved: list[str] = []
    unresolved = merge_items(unresolved, stop_conditions)
    unresolved = merge_items(unresolved, _resume_delta_unresolved_items(resume_delta))
    unresolved = merge_items(unresolved, _checkpoint_mismatch_items(checkpoint_mismatches))
    return unresolved


def _display_read_hints(
    read_hints: list[str],
    *,
    root: Path,
    keep: int,
    task_description: str = "",
    validator_plan: list[str] | None = None,
) -> list[str]:
    if keep <= 0:
        return []
    display = _display_paths(read_hints, root=root)
    if not display:
        return []
    named_paths = _task_named_paths(task_description, root=root)
    validator_targets = _validator_read_targets(validator_plan or [], root=root)
    ranked: list[tuple[int, int, str]] = []
    for index, item in enumerate(display):
        ranked.append(
            (
                _read_hint_display_priority(
                    item,
                    named_paths=named_paths,
                    validator_targets=validator_targets,
                ),
                index,
                item,
            )
        )
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [text for _priority, _index, text in ranked[:keep]]


def _ensure_task_md_read_hint(read_hints: list[str], *, keep: int) -> list[str]:
    if keep <= 0:
        return []
    items = _normalize_items(read_hints)
    task_md = next((item for item in items if _looks_like_task_md_path(item)), "")
    if task_md:
        ordered = [task_md] + [item for item in items if item != task_md]
    else:
        ordered = ["TASK.md"] + items
    return ordered[:keep]


def _display_validator_plan(
    validator_plan: list[str],
    *,
    root: Path,
    keep: int,
    read_hints: list[str] | None = None,
    required_artifacts: list[str] | None = None,
    tier: str = "",
    task_md_authoritative: bool = False,
    collapse_implied_targets: bool = False,
    compact_doc_loop: bool = False,
) -> list[str]:
    if keep <= 0:
        return []
    compacted: list[tuple[int, str]] = []
    for index, item in enumerate(_trim_items(validator_plan, len(validator_plan))):
        text = _compact_validator_plan_item(item, root=root)
        if text:
            compacted.append((index, text))
    has_concrete_wording = any(text.lower().startswith("check wording: ") for _index, text in compacted)
    has_concrete_acceptance = any(text.lower().startswith("check acceptance: ") for _index, text in compacted)
    has_concrete_files = any(text.lower().startswith("check files: ") for _index, text in compacted)
    has_docs_inspection = any(text.lower().startswith("inspect docs: ") for _index, text in compacted)
    has_test_validator = any(text.lower().startswith("run tests: ") for _index, text in compacted)
    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, text in compacted:
        if not text or text in seen:
            continue
        if _skip_abstract_validator_item(
            text,
            has_concrete_wording=has_concrete_wording,
            has_concrete_acceptance=has_concrete_acceptance,
            has_concrete_files=has_concrete_files,
            has_docs_inspection=has_docs_inspection,
        ):
            continue
        if _skip_tier_specific_validator_item(
            text,
            required_artifacts=required_artifacts or [],
            tier=tier,
            has_concrete_files=has_concrete_files,
            has_test_validator=has_test_validator,
        ):
            continue
        if _skip_display_validator_item(
            text,
            read_hints=read_hints or [],
            required_artifacts=required_artifacts or [],
            tier=tier,
            task_md_authoritative=task_md_authoritative,
        ):
            continue
        seen.add(text)
        ranked.append((_validator_display_priority(text), index, text))
    ranked.sort(key=lambda row: (row[0], row[1]))
    display = [text for _priority, _index, text in ranked[:keep]]
    if collapse_implied_targets:
        display = _collapse_doc_validator_targets(
            display,
            read_hints=read_hints or [],
            required_artifacts=required_artifacts or [],
        )
    if compact_doc_loop:
        display = _specialize_t3_doc_validators(display, required_artifacts=required_artifacts or [])
    return display


def _display_literal_rules(
    *,
    exactness_rules: list[str],
    acceptance_contract: list[str],
    keep: int,
) -> list[str]:
    if keep <= 0:
        return []
    items = _compact_literal_anchors(exactness_rules, keep=keep)
    if not items:
        items = _normalize_items(exactness_rules or acceptance_contract)
    return items[:keep]


def _collapse_doc_validator_targets(
    items: list[str],
    *,
    read_hints: list[str],
    required_artifacts: list[str],
) -> list[str]:
    named_targets = {item.replace("\\", "/").lower() for item in _normalize_items(read_hints + required_artifacts)}
    collapsed: list[str] = []
    seen: set[str] = set()
    for item in _normalize_items(items):
        replacement = item
        lowered = item.lower()
        if lowered.startswith("check wording: "):
            targets = _validator_display_targets(item)
            if targets and all(target in named_targets for target in targets):
                replacement = "check wording"
        elif lowered.startswith("inspect docs: "):
            targets = _validator_display_targets(item)
            if targets and all(target in named_targets for target in targets):
                replacement = "inspect docs"
        if replacement in seen:
            continue
        seen.add(replacement)
        collapsed.append(replacement)
    return collapsed


def _validator_display_targets(text: str) -> list[str]:
    _label, _sep, values = str(text or "").partition(":")
    if not values:
        return []
    targets: list[str] = []
    for value in values.split(";"):
        normalized = value.strip().replace("\\", "/").lower()
        if normalized:
            targets.append(normalized)
    return targets


def _compact_literal_anchors(exactness_rules: list[str], *, keep: int) -> list[str]:
    behavior_anchors: list[str] = []
    role_anchors: list[str] = []
    other_anchors: list[str] = []
    for rule in _normalize_items(exactness_rules):
        text = rule.lstrip("- ").strip()
        lowered = text.lower()
        if ": one of " in lowered:
            label, _sep, options = text.partition(": one of ")
            choice = next((item.strip(" `") for item in options.split(",") if item.strip()), "")
            if choice:
                normalized_label = label.strip().lower()
                if normalized_label.startswith("role_"):
                    role_anchors.append(choice)
                else:
                    behavior_anchors.append(choice)
                continue
        if lowered.startswith("keep heading `") and text.count("`") >= 2:
            other_anchors.append(text.split("`", 2)[1])
            continue
        include_match = re.search(r"include `([^`]+)`", text)
        if include_match:
            other_anchors.append(include_match.group(1).strip())
            continue
        if "output in markdown" in lowered or "keep the output in markdown" in lowered:
            other_anchors.append("Markdown")
            continue
        other_anchors.append(text)
    anchors = behavior_anchors or role_anchors[:1] or other_anchors
    return _normalize_items(anchors)[:keep]


def _compact_role_anchors(exactness_rules: list[str], *, keep: int) -> list[str]:
    roles: list[str] = []
    for rule in _normalize_items(exactness_rules):
        text = rule.lstrip("- ").strip()
        lowered = text.lower()
        if ": one of " not in lowered:
            continue
        label, _sep, options = text.partition(": one of ")
        if not label.strip().lower().startswith("role_"):
            continue
        choice = next((item.strip(" `") for item in options.split(",") if item.strip()), "")
        if choice:
            roles.append(choice)
    return _normalize_items(roles)[:keep]


def _t3_doc_contract_parts(
    exactness_rules: list[str],
    *,
    required_artifacts: list[str],
) -> tuple[list[str], list[str], dict[str, list[str]], str]:
    normalized_artifacts = [
        str(item).replace("\\", "/")
        for item in _normalize_items(required_artifacts)
        if str(item).lower().endswith((".md", ".txt", ".rst"))
    ]
    headings: list[str] = []
    sections_by_target: dict[str, list[str]] = {}
    for rule in _normalize_items(exactness_rules):
        text = rule.lstrip("- ").strip()
        lowered = text.lower()
        if lowered.startswith("keep heading `") and text.count("`") >= 2:
            heading = text.split("`", 2)[1].strip()
            headings.append(heading)
            continue
        include_match = re.search(r"include `([^`]+)` in `([^`]+)`", text)
        if not include_match:
            continue
        field = include_match.group(1).strip()
        target = include_match.group(2).strip().replace("\\", "/")
        canonical_target = next(
            (artifact for artifact in normalized_artifacts if artifact.lower() == target.lower()),
            "",
        )
        if canonical_target:
            sections_by_target.setdefault(canonical_target, []).append(field)
    include_targets = {target.lower() for target in sections_by_target}
    document_artifact = next(
        (artifact for artifact in normalized_artifacts if artifact.lower() not in include_targets),
        normalized_artifacts[0] if normalized_artifacts else "",
    )
    normalized_headings = _normalize_items(headings)
    normalized_sections = {
        artifact: _normalize_items(sections)
        for artifact, sections in sections_by_target.items()
        if _normalize_items(sections)
    }
    return normalized_artifacts, normalized_headings, normalized_sections, document_artifact


def _compact_t3_doc_shape_hint(exactness_rules: list[str], *, required_artifacts: list[str]) -> str:
    normalized_artifacts, normalized_headings, sections_by_target, _document_artifact = _t3_doc_contract_parts(
        exactness_rules,
        required_artifacts=required_artifacts,
    )
    if not normalized_artifacts:
        return ""
    parts: list[str] = []
    if normalized_headings:
        parts.append("doc headings [" + " | ".join(normalized_headings[:4]) + "]")
    for artifact in normalized_artifacts:
        sections = _normalize_items(sections_by_target.get(artifact, []))
        if sections:
            section_headings = [value if value.startswith("#") else f"## {value}" for value in sections[:4]]
            label = "checkpoint headings ["
            if len(sections_by_target) > 1:
                label = f"{Path(artifact).name} headings ["
            parts.append(label + " | ".join(section_headings) + "]")
    if parts:
        parts.append("no extra sections/examples")
    return "; ".join(parts)


def _display_artifact_manifest(
    artifact_manifest: list[str],
    required_artifacts: list[str],
    *,
    emit: bool,
    root: Path,
) -> list[str]:
    if not emit:
        return []
    normalized_manifest = _display_paths(artifact_manifest, root=root)
    normalized_required = _normalize_items(required_artifacts)
    if normalized_manifest == normalized_required:
        return []
    return normalized_manifest


def _t2_write_requirements_and_done_when(
    *,
    required_artifacts: list[str],
    acceptance_contract: list[str],
    validator_plan: list[str],
    exactness_rules: list[str],
) -> tuple[list[str], list[str], list[str]]:
    items = _normalize_items(acceptance_contract)
    if not items:
        return [], [], []
    artifact_specs = _t2_artifact_specs(
        required_artifacts=required_artifacts,
        exactness_rules=exactness_rules,
        acceptance_contract=acceptance_contract,
    )
    has_check_files = any(str(item or "").strip().lower().startswith("check files: ") for item in validator_plan)
    if not has_check_files:
        return artifact_specs, [], items
    write_requirements: list[str] = []
    done_when: list[str] = []
    for item in items:
        if _t2_is_validator_completion_clause(item):
            done_when.append(item)
            continue
        if _t2_is_artifact_write_requirement(item, required_artifacts=required_artifacts):
            if _t2_requirement_covered_by_artifact_specs(
                item,
                required_artifacts=required_artifacts,
                artifact_specs=artifact_specs,
            ):
                continue
            write_requirements.append(item)
            continue
        done_when.append(item)
    if write_requirements or artifact_specs:
        done_when = merge_items(done_when, ["required artifact files exist"])
    return artifact_specs, write_requirements, done_when or items


def _t2_align_validator_plan(
    *,
    validator_plan: list[str],
    acceptance_contract: list[str],
) -> list[str]:
    items = _normalize_items(validator_plan)
    explicit_test_commands = _t2_explicit_test_commands(acceptance_contract)
    if not items or len(explicit_test_commands) != 1:
        return items
    command = explicit_test_commands[0]
    aligned: list[str] = []
    replaced = False
    for item in items:
        lowered = item.strip().lower()
        if lowered.startswith("run tests: ") and not replaced:
            aligned.append(f"run tests: {command}")
            replaced = True
            continue
        aligned.append(item)
    return _normalize_items(aligned)


def _t2_is_validator_completion_clause(text: str) -> bool:
    lowered = " ".join(str(text or "").split()).lower()
    if not lowered:
        return False
    completion_tokens = (" passes", " passed", " succeeds", " succeeded", " complete", " completed")
    return any(token in lowered for token in completion_tokens)


def _t2_explicit_test_commands(acceptance_contract: list[str]) -> list[str]:
    commands: list[str] = []
    for item in _normalize_items(acceptance_contract):
        match = re.match(r"(?P<command>.+?)\s+(passes|passed|succeeds|succeeded)$", item.strip(), flags=re.IGNORECASE)
        if not match:
            continue
        command = match.group("command").strip().strip("`")
        lowered = command.lower()
        test_markers = ("pytest", "unittest", " test", "npm test", "pnpm test", "go test", "cargo test", "mvn test", "gradle test")
        if any(marker in lowered for marker in test_markers):
            commands.append(command)
    return _normalize_items(commands)


def _t2_is_artifact_write_requirement(text: str, *, required_artifacts: list[str]) -> bool:
    lowered = " ".join(str(text or "").replace("\\", "/").split()).lower()
    if not lowered:
        return False
    artifact_tokens: list[str] = []
    for artifact in _normalize_items(required_artifacts):
        normalized = artifact.replace("\\", "/").strip().lower()
        if normalized:
            artifact_tokens.append(normalized)
        name = Path(normalized).name.lower()
        if name:
            artifact_tokens.append(name)
    artifact_tokens = _normalize_items(artifact_tokens)
    if any(token and token in lowered for token in artifact_tokens):
        return True
    semantic_tokens = (
        " heading",
        " headings",
        " key",
        " keys",
        " section",
        " sections",
        " field",
        " fields",
        " handoff",
        " literal wording",
        " acl-x",
        " aclx",
    )
    return any(token in lowered for token in semantic_tokens)


def _t2_artifact_specs(
    *,
    required_artifacts: list[str],
    exactness_rules: list[str],
    acceptance_contract: list[str],
) -> list[str]:
    specs: list[str] = []
    for artifact in _normalize_items(required_artifacts):
        detail = _t2_exactness_artifact_detail(artifact, exactness_rules) or _t2_acceptance_artifact_detail(
            artifact,
            acceptance_contract,
        )
        if detail:
            specs.append(f"{artifact} -> {detail}")
    return _normalize_items(specs)


def _t2_exactness_artifact_detail(artifact: str, exactness_rules: list[str]) -> str:
    normalized_artifact = _normalize_artifact_path_text(artifact)
    artifact_name = Path(normalized_artifact).name.lower()
    for rule in _normalize_items(exactness_rules):
        normalized_rule = _normalize_artifact_path_text(rule)
        if normalized_artifact not in normalized_rule and artifact_name not in normalized_rule:
            continue
        if "must include keys:" in normalized_rule:
            match = re.search(r"keys:\s*(.+)$", rule, flags=re.IGNORECASE)
            if not match:
                continue
            keys = _t2_named_items(match.group(1))
            if keys:
                return "keys " + ", ".join(keys[:4])
        if "with headings" in normalized_rule:
            values = [item for item in re.findall(r"`([^`]+)`", rule) if _normalize_artifact_path_text(item) != normalized_artifact]
            if values:
                return "headings " + ", ".join(values[:4])
    return ""


def _t2_acceptance_artifact_detail(artifact: str, acceptance_contract: list[str]) -> str:
    normalized_artifact = _normalize_artifact_path_text(artifact)
    artifact_name = Path(normalized_artifact).name.lower()
    for rule in _normalize_items(acceptance_contract):
        normalized_rule = _normalize_artifact_path_text(rule)
        if normalized_artifact not in normalized_rule and artifact_name not in normalized_rule:
            continue
        if artifact_name.endswith(".aclx") and (
            "acl-x c-layer text" in normalized_rule
            or "aclx c-layer text" in normalized_rule
            or "machine-state artifact" in normalized_rule
        ):
            return "exact ACL-X bundle line"
        if " headings" in normalized_rule:
            match = re.search(r"keeps?\s+(.+?)\s+headings?$", rule, flags=re.IGNORECASE)
            if not match:
                return ""
            headings = _t2_named_items(match.group(1))
            if headings:
                return "headings " + ", ".join(headings[:4])
            return ""
    return ""


def _t2_named_items(text: str) -> list[str]:
    raw = str(text or "").strip().strip(".")
    if not raw:
        return []
    parts = re.split(r",|\band\b", raw, flags=re.IGNORECASE)
    items: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = part.strip().strip("`'\"")
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(value)
    return items


def _t2_requirement_covered_by_artifact_specs(
    text: str,
    *,
    required_artifacts: list[str],
    artifact_specs: list[str],
) -> bool:
    covered = {spec.partition(" -> ")[0].strip().replace("\\", "/").lower() for spec in _normalize_items(artifact_specs)}
    touched = _t2_requirement_artifacts(text, required_artifacts=required_artifacts)
    return bool(touched) and all(item in covered for item in touched)


def _t2_requirement_artifacts(text: str, *, required_artifacts: list[str]) -> list[str]:
    lowered = _normalize_artifact_path_text(text)
    touched: list[str] = []
    for artifact in _normalize_items(required_artifacts):
        normalized = _normalize_artifact_path_text(artifact)
        artifact_name = Path(normalized).name.lower()
        if normalized in lowered or artifact_name in lowered:
            touched.append(normalized)
    return _normalize_items(touched)


def _normalize_artifact_path_text(text: str) -> str:
    return " ".join(str(text or "").replace("\\", "/").split()).lower()


def _checkpoint_validator_results(results: list[str], *, persist_generic: bool) -> list[str]:
    if persist_generic:
        return _normalize_items(results)
    return _semantic_validator_results(results)


def _semantic_validator_results(results: list[str]) -> list[str]:
    semantic: list[str] = []
    for item in _normalize_items(results):
        if item.startswith(("ok:", "fail:")):
            semantic.append(item)
    return semantic


def _completed_validator_plans(results: list[str]) -> set[str]:
    completed: set[str] = set()
    for item in _normalize_items(results):
        prefix, separator, plan = item.partition(":")
        if separator and prefix == "ok" and plan.strip():
            completed.add(plan.strip())
    return completed


def _fallback_checkpoint_mismatches(
    checkpoint_mismatches: list[str],
    exc: ContractResumeMismatch,
) -> list[str]:
    if checkpoint_mismatches:
        return _normalize_items(checkpoint_mismatches)
    message = str(exc).lower()
    inferred: list[str] = []
    if "adapter mismatch" in message:
        inferred.append("adapter_id")
    if "tier mismatch" in message:
        inferred.append("runtime_tier")
    if "contract mismatch" in message:
        inferred.append("contract_hash")
    return inferred or ["contract_hash"]


def _match_validator_result(plan: str, tool_results: list[dict[str, Any] | str]) -> str:
    plan_text = str(plan or "").strip()
    if not plan_text:
        return ""
    plan_lower = plan_text.lower()
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or item.get("kind") or "").strip().lower()
        if item_type in {"validator", "validation"}:
            planned = str(item.get("plan") or item.get("validator_plan") or "").strip()
            if planned and planned != plan_text:
                continue
            status = str(item.get("status") or "").strip().lower()
            if not status:
                status = "ok" if bool(item.get("ok", True)) else "fail"
            if status not in {"ok", "fail"}:
                continue
            return f"{status}:{plan_text}"
        if item_type == "shell" or "command" in item:
            command = str(item.get("command") or "").strip()
            if not _validator_plan_matches_command(plan_lower, command):
                continue
            status = "ok" if int(item.get("returncode", 0)) == 0 else "fail"
            return f"{status}:{plan_text}"
        path = str(item.get("path") or "").strip()
        if path and _validator_plan_matches_path(plan_lower, path):
            return f"ok:{plan_text}"
    return ""


def _generic_tool_validator_results(tool_results: list[dict[str, Any] | str]) -> list[str]:
    results: list[str] = []
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or item.get("kind") or "").strip().lower()
        if item_type == "shell" or "command" in item:
            command = str(item.get("command") or "").strip()
            if command:
                results.append(f"shell:{command}:rc={int(item.get('returncode', 0))}")
            continue
        path = str(item.get("path") or "").strip()
        if path:
            results.append(f"file:{path}")
    return _normalize_items(results)


def _trim_items(values: list[str], keep: int) -> list[str]:
    if keep <= 0:
        return []
    return _normalize_items(values)[:keep]


def _display_paths(values: list[str], *, root: Path) -> list[str]:
    display: list[str] = []
    for item in _normalize_items(values):
        text = _compact_display_path(item, root=root)
        if text and text not in display:
            display.append(text)
    return display


def _compact_validator_plan_item(plan: str, *, root: Path) -> str:
    text = " ".join(str(plan or "").split())
    lowered = text.lower()
    if lowered.startswith("run python -m unittest "):
        return "run tests: " + _compact_path_list_text(text[len("run python -m unittest ") :], root=root)
    if lowered.startswith("run pytest "):
        return "run tests: " + _compact_path_list_text(text[len("run pytest ") :], root=root)
    prefix_map = {
        "verify artifacts exist: ": "check files: ",
        "inspect referenced artifacts: ": "inspect: ",
        "inspect comparison sources: ": "inspect: ",
        "inspect structured content requirements in ": "inspect: ",
        "inspect python target ": "inspect: ",
        "inspect filesystem target ": "inspect: ",
        "inspect docs outputs: ": "inspect docs: ",
        "check docs wording: ": "check wording: ",
        "check docs acceptance: ": "check acceptance: ",
    }
    for prefix, replacement in prefix_map.items():
        if lowered.startswith(prefix):
            return replacement + _compact_path_list_text(text[len(prefix):], root=root)
    if lowered.startswith("check outputs against named inputs: "):
        return "check refs"
    if lowered.startswith("check literal and structural rules on named artifacts"):
        return "check wording"
    if lowered.startswith("verify required headings and literal wording in docs outputs"):
        return "check wording"
    if "acceptance rules" in lowered:
        return "check acceptance"
    text = _compact_path_list_text(text, root=root)
    return text


def _compact_path_list_text(text: str, *, root: Path) -> str:
    parts = [part.strip() for part in str(text or "").split(";")]
    compacted: list[str] = []
    for part in parts:
        if not part:
            continue
        compacted.append(_compact_display_path(part, root=root) if _looks_like_path_text(part) else part)
    return "; ".join(compacted)


def _validator_display_priority(text: str) -> int:
    lowered = text.lower()
    if lowered.startswith("run tests: "):
        return 0
    if lowered.startswith("check wording: "):
        return 1
    if lowered.startswith("check files: "):
        return 2
    if lowered.startswith("inspect docs: "):
        return 3
    if lowered.startswith("inspect: "):
        return 4
    if lowered.startswith("check acceptance: "):
        return 5
    if lowered == "check acceptance":
        return 6
    if lowered == "check wording":
        return 7
    if lowered == "check refs":
        return 8
    return 9


def _skip_abstract_validator_item(
    text: str,
    *,
    has_concrete_wording: bool,
    has_concrete_acceptance: bool,
    has_concrete_files: bool,
    has_docs_inspection: bool,
) -> bool:
    lowered = text.lower()
    if lowered == "check wording":
        return has_concrete_wording
    if lowered == "check acceptance":
        return has_concrete_acceptance or has_concrete_files or has_docs_inspection
    return False


def _skip_display_validator_item(
    text: str,
    *,
    read_hints: list[str],
    required_artifacts: list[str],
    tier: str,
    task_md_authoritative: bool,
) -> bool:
    lowered = text.lower()
    read_set = {item.lower() for item in _normalize_items(read_hints)}
    artifact_set = {item.lower() for item in _normalize_items(required_artifacts)}
    if lowered.startswith("check files: "):
        if tier == "t2":
            return False
        values = _validator_item_targets(text[len("check files: ") :])
        return bool(values) and all(value in artifact_set for value in values)
    if lowered.startswith("inspect docs: "):
        values = _validator_item_targets(text[len("inspect docs: ") :], include_non_paths=False)
        if not values:
            return True
        if tier == "t3" and task_md_authoritative:
            return False
        return all(value in read_set or value in artifact_set for value in values)
    if lowered.startswith("inspect: "):
        prefix = "inspect: "
        values = _validator_item_targets(text[len(prefix) :], include_non_paths=False)
        if not values:
            return True
        return all(value in read_set or value in artifact_set for value in values)
    return False


def _skip_tier_specific_validator_item(
    text: str,
    *,
    required_artifacts: list[str],
    tier: str,
    has_concrete_files: bool,
    has_test_validator: bool,
) -> bool:
    if tier != "t2" or not has_concrete_files or not has_test_validator:
        return False
    lowered = text.lower()
    artifact_set = {item.lower() for item in _normalize_items(required_artifacts)}
    if lowered.startswith("check wording: "):
        values = _validator_item_targets(text[len("check wording: ") :], include_non_paths=False)
        return bool(values) and all(value in artifact_set for value in values)
    if lowered.startswith("inspect docs: "):
        values = _validator_item_targets(text[len("inspect docs: ") :], include_non_paths=False)
        return bool(values) and all(value in artifact_set for value in values)
    return False


def _validator_item_targets(text: str, *, include_non_paths: bool = True) -> list[str]:
    targets: list[str] = []
    for raw_part in str(text or "").split(";"):
        part = raw_part.strip()
        if not part:
            continue
        normalized = part.replace("\\", "/").strip().lower()
        if include_non_paths or _looks_like_path_text(normalized):
            targets.append(normalized)
    return targets


def _read_hint_display_priority(
    value: str,
    *,
    named_paths: set[str],
    validator_targets: set[str],
) -> int:
    lowered = str(value or "").strip().lower()
    if _looks_like_task_md_path(lowered):
        return 0
    if lowered in validator_targets:
        return 1 if _looks_like_test_path(lowered) else 2
    if lowered not in named_paths:
        return 3
    return 4


def _task_named_paths(task_description: str, *, root: Path) -> set[str]:
    named: set[str] = set()
    for value in _extract_pathish_tokens(task_description, root=root):
        named.add(value.lower())
    return named


def _validator_read_targets(validator_plan: list[str], *, root: Path) -> set[str]:
    targets: set[str] = set()
    for item in _normalize_items(validator_plan):
        text = _compact_validator_plan_item(item, root=root)
        lowered = text.lower()
        if lowered.startswith("run tests: "):
            values = _extract_pathish_tokens(text[len("run tests: "):], root=root)
        elif lowered.startswith("inspect docs: "):
            values = _extract_pathish_tokens(text[len("inspect docs: "):], root=root)
        elif lowered.startswith("inspect: "):
            values = _extract_pathish_tokens(text[len("inspect: "):], root=root)
        else:
            values = []
        for value in values:
            targets.add(value.lower())
    return targets


def _extract_pathish_tokens(text: str, *, root: Path) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_part in re.split(r"[\s;]+", str(text or "")):
        token = raw_part.strip().strip("`'\".,:;()[]{}")
        if not token or not _looks_like_path_text(token):
            continue
        compact = _compact_display_path(token, root=root)
        lowered = compact.lower()
        if not compact or lowered in seen:
            continue
        seen.add(lowered)
        values.append(compact)
    return values


def _looks_like_task_md_path(value: str) -> bool:
    lowered = str(value or "").replace("\\", "/").strip().lower()
    return lowered.endswith(("task.md", "task.txt", "task.rst"))


def _looks_like_test_path(value: str) -> bool:
    lowered = str(value or "").replace("\\", "/").strip().lower()
    name = Path(lowered).name.lower()
    return lowered.startswith("tests/") or "/tests/" in lowered or name.startswith("test_")


def _task_md_contract_source(contract: TaskContract | None) -> bool:
    if contract is None:
        return False
    sources = [
        str(item or "").replace("\\", "/").strip().lower()
        for item in contract.metadata.get("contract_sources", [])
    ]
    return any(_looks_like_task_md_path(item) for item in sources)


def _compact_display_path(value: str, *, root: Path) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    if not _looks_like_path_text(text):
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            return text
    return text


def _looks_like_path_text(value: str) -> bool:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return False
    if text.startswith("./") or text.startswith("../"):
        return True
    if ":/" in text or "/" in text:
        return True
    return Path(text).suffix.lower() in {".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv", ".aclx"}


def _validator_plan_matches_command(plan_lower: str, command: str) -> bool:
    command_lower = " ".join(str(command or "").lower().split())
    if not command_lower:
        return False
    if plan_lower.startswith("run "):
        planned = " ".join(plan_lower[4:].split())
        return planned in command_lower or command_lower in planned
    if "python -m unittest" in plan_lower:
        return "python -m unittest" in command_lower
    if "pytest" in plan_lower:
        return "pytest" in command_lower
    if any(token in plan_lower for token in ("lint", "ruff", "flake8", "mypy")):
        return any(token in command_lower for token in ("ruff", "flake8", "mypy", "lint"))
    return False


def _validator_plan_matches_path(plan_lower: str, path: str) -> bool:
    normalized_path = str(path or "").replace("\\", "/").strip().lower()
    if not normalized_path:
        return False
    name = Path(normalized_path).name.lower()
    return normalized_path in plan_lower or name in plan_lower


def _line(label: str, values: list[str]) -> str:
    items = _normalize_items(values)
    if not items:
        return ""
    return f"{label}: " + "; ".join(items)


def _resume_line(task_description: str) -> str:
    text = str(task_description or "").strip()
    if not text:
        return "Resume."
    if text.lower().startswith("resume"):
        return text
    return f"Resume: {text}"


def _is_t3_generic_doc_compaction(
    *,
    tier: str,
    task_md_authoritative: bool,
    required_artifacts: list[str],
) -> bool:
    if str(tier or "").lower() != "t3" or not task_md_authoritative:
        return False
    items = [item.replace("\\", "/").lower() for item in _normalize_items(required_artifacts)]
    if not items or any(item.endswith(".aclx") for item in items):
        return False
    return all(item.endswith((".md", ".txt", ".rst")) for item in items)


def _is_t3_compiled_doc_contract_complete(
    *,
    tier: str,
    task_md_authoritative: bool,
    exactness_rules: list[str],
    required_artifacts: list[str],
) -> bool:
    if not _is_t3_generic_doc_compaction(
        tier=tier,
        task_md_authoritative=task_md_authoritative,
        required_artifacts=required_artifacts,
    ):
        return False
    doc_targets, checkpoint_targets = _partition_t3_doc_targets(required_artifacts)
    if not doc_targets or not checkpoint_targets:
        return False
    _artifacts, headings, sections_by_target, _document_artifact = _t3_doc_contract_parts(
        exactness_rules,
        required_artifacts=required_artifacts,
    )
    has_doc_headings = len(headings) >= 2
    checkpoint_sections = any(
        sections
        for artifact, sections in sections_by_target.items()
        if _looks_like_checkpoint_doc_target(artifact)
    )
    has_literal_anchors = bool(_compact_literal_anchors(exactness_rules, keep=8))
    return has_doc_headings and checkpoint_sections and has_literal_anchors


def _compact_t3_read_hints(
    read_hints: list[str],
    *,
    required_artifacts: list[str],
    compiled_authoritative: bool = False,
) -> list[str]:
    items = _normalize_items(read_hints)
    preferred_doc = next(
        (
            item
            for item in _normalize_items(required_artifacts)
            if str(item).replace("\\", "/").lower().endswith((".md", ".rst", ".txt"))
            and not _looks_like_checkpoint_doc_target(str(item))
        ),
        "",
    )
    if compiled_authoritative:
        if preferred_doc:
            return [preferred_doc]
        fallback_doc = next(
            (
                item
                for item in items
                if not _looks_like_task_md_path(item)
            ),
            "",
        )
        return [fallback_doc] if fallback_doc else items[:1]
    if preferred_doc:
        task_md = next(
            (
                item
                for item in items
                if item.replace("\\", "/").lower().endswith("/task.md") or item.lower() == "task.md"
            ),
            "",
        )
        if task_md:
            return [task_md, preferred_doc]
        return [preferred_doc]
    task_md = next(
        (
            item
            for item in items
            if item.replace("\\", "/").lower().endswith("/task.md") or item.lower() == "task.md"
        ),
        "",
    )
    if task_md:
        return [task_md]
    return items[:1]


def _filter_compiled_t3_doc_preread_targets(
    read_hints: list[str],
    *,
    pending_artifacts: list[str],
) -> list[str]:
    pending_set = {
        str(item or "").replace("\\", "/").strip().lower()
        for item in _normalize_items(pending_artifacts)
    }
    filtered: list[str] = []
    for item in _normalize_items(read_hints):
        normalized = str(item or "").replace("\\", "/").strip()
        lowered = normalized.lower()
        if not normalized:
            continue
        if _looks_like_task_md_path(normalized):
            continue
        if lowered in pending_set:
            continue
        if _looks_like_checkpoint_doc_target(normalized):
            continue
        if not lowered.endswith((".md", ".rst", ".txt")):
            continue
        filtered.append(normalized)
    return _normalize_items(filtered)


def _specialize_t3_doc_validators(items: list[str], *, required_artifacts: list[str]) -> list[str]:
    doc_targets, checkpoint_targets = _partition_t3_doc_targets(required_artifacts)
    if not doc_targets and not checkpoint_targets:
        return _normalize_items(items)
    rewritten: list[str] = []
    for item in _normalize_items(items):
        lowered = item.lower()
        if lowered.startswith("check wording: ") and doc_targets:
            rewritten.append("check wording: " + "; ".join(doc_targets[:2]))
            continue
        if lowered.startswith("inspect docs: ") and checkpoint_targets:
            rewritten.append("inspect docs: " + "; ".join(checkpoint_targets[:2]))
            continue
        rewritten.append(item)
    return _normalize_items(rewritten)


def _partition_t3_doc_targets(required_artifacts: list[str]) -> tuple[list[str], list[str]]:
    doc_targets: list[str] = []
    checkpoint_targets: list[str] = []
    for item in _normalize_items(required_artifacts):
        normalized = str(item).replace("\\", "/").strip()
        if not normalized.lower().endswith((".md", ".rst", ".txt")):
            continue
        if _looks_like_checkpoint_doc_target(normalized):
            checkpoint_targets.append(normalized)
        else:
            doc_targets.append(normalized)
    if not doc_targets and checkpoint_targets:
        return checkpoint_targets[:], checkpoint_targets[:]
    if not checkpoint_targets and doc_targets:
        return doc_targets[:], doc_targets[:]
    return doc_targets, checkpoint_targets


def _compact_t3_write_targets(required_artifacts: list[str]) -> list[str]:
    doc_targets, checkpoint_targets = _partition_t3_doc_targets(required_artifacts)
    ordered = _normalize_items(doc_targets[:1] + checkpoint_targets[:2])
    if ordered:
        return ordered
    return _normalize_items(required_artifacts)


def _compact_t3_source_line(read_hints: list[str], *, compiled_authoritative: bool = False) -> str:
    items = _normalize_items(read_hints)
    if not items:
        return ""
    if compiled_authoritative and len(items) == 1:
        return f"Source: {items[0]}"
    return _line("Read first", items)


def _compact_t3_target_line(required_artifacts: list[str], *, pending_artifacts: list[str]) -> str:
    required = _compact_t3_write_targets(required_artifacts)
    if not required:
        return ""
    pending_set = {item.lower() for item in _normalize_items(pending_artifacts)}
    create_targets = [item for item in required if item.lower() in pending_set]
    update_targets = [item for item in required if item.lower() not in pending_set]
    parts: list[str] = []
    if update_targets:
        parts.extend([f"update {item}" for item in update_targets[:2]])
    if create_targets:
        parts.extend([f"create {item}" for item in create_targets[:2]])
    if not parts:
        parts.extend(required[:2])
    return "Targets: " + "; ".join(parts)


def _looks_like_checkpoint_doc_target(path_text: str) -> bool:
    normalized = str(path_text or "").replace("\\", "/").strip().lower()
    if not normalized:
        return False
    name = Path(normalized).name.lower()
    parent = Path(normalized).parent.name.lower()
    return parent == "reports" or "checkpoint" in name


def _render_t2_prompt(
    *,
    task_description: str,
    runtime_bundle: str,
    required_artifacts: list[str],
    acceptance_contract: list[str],
    exactness_rules: list[str],
    stop_conditions: list[str],
    next_actions: list[str],
    read_hints: list[str],
    validator_plan: list[str],
    artifact_manifest: list[str],
    emit_header: bool,
) -> str:
    artifact_specs, write_requirements, done_when = _t2_write_requirements_and_done_when(
        required_artifacts=required_artifacts,
        acceptance_contract=acceptance_contract,
        validator_plan=validator_plan,
        exactness_rules=exactness_rules,
    )
    aligned_validator_plan = _t2_align_validator_plan(
        validator_plan=validator_plan,
        acceptance_contract=acceptance_contract,
    )
    sections = [
        str(task_description or "").strip(),
        _line("Read first", read_hints),
        "Machine contract:",
        _line("Must write", required_artifacts),
        _line("Artifact spec", artifact_specs),
        _line("Write requirements", write_requirements),
        _line("Done when", done_when),
        _line("Validate", aligned_validator_plan),
        _line("Artifacts", artifact_manifest),
        _artifact_rule_line(required_artifacts, kind="shared"),
        T2_EXECUTION_RULE,
    ]
    if emit_header:
        sections.append(T2_PROMPT_HEADER)
    sections.append(runtime_bundle)
    return "\n".join(part for part in sections if part)


def _render_t3_prompt(
    *,
    task_description: str,
    runtime_bundle: str,
    required_artifacts: list[str],
    pending_artifacts: list[str],
    acceptance_contract: list[str],
    stop_conditions: list[str],
    next_actions: list[str],
    read_hints: list[str],
    validator_plan: list[str],
    artifact_manifest: list[str],
    exactness_rules: list[str],
    doc_shape_hint: str,
    doc_roles: list[str],
    task_md_authoritative: bool,
    emit_header: bool,
    compact_doc_loop: bool = False,
    compiled_doc_contract: bool = False,
) -> str:
    task_text = str(task_description or "").strip()
    has_embedded_contract_lines = "task contract lines:" in task_text.lower()
    has_aclx_artifact = _has_aclx_artifact(required_artifacts)
    read_first = _compact_t3_source_line(read_hints, compiled_authoritative=compiled_doc_contract and compact_doc_loop)
    if task_md_authoritative:
        contract_line = "Task contract: `TASK.md` is authoritative; read it once and keep explicit wording literal."
        direct_pass_line = "Direct pass: read TASK.md once, edit named targets, then reply with changed paths and verification only."
        wording_items = _normalize_items(exactness_rules or acceptance_contract)
    elif has_embedded_contract_lines:
        contract_line = "Task contract: use the task text above."
        direct_pass_line = "Direct pass: use the embedded contract, edit named targets, then reply with changed paths and verification only."
        wording_items = []
    else:
        contract_line = "Task contract: task text is authoritative for named files and required wording."
        direct_pass_line = (
            "Direct pass: use the contract, edit named targets and checkpoint files, then reply with changed paths and verification only."
            if has_aclx_artifact
            else "Direct pass: use the contract, edit named targets, then reply with changed paths and verification only."
        )
        wording_items = _normalize_items(exactness_rules or acceptance_contract)
    literal_anchor_label = "Literal anchors (exact casing)" if compact_doc_loop else "Literal wording"
    if compact_doc_loop:
        target_line = _compact_t3_target_line(required_artifacts, pending_artifacts=pending_artifacts)
        compact_rule = T3_DOC_COMPILED_OPERATING_RULE if compiled_doc_contract else T3_DOC_COMPACT_RULE
        compact_reply_rule = T3_DOC_COMPILED_REPLY_RULE if compiled_doc_contract else T3_DOC_COMPACT_REPLY_RULE
        validation_hint = "" if compiled_doc_contract else T3_DOC_VALIDATION_HINT
        sections = [
            task_text,
            read_first,
            target_line,
            T3_DOC_COMPILED_CONTRACT_LINE if compiled_doc_contract else contract_line,
            _line("Roles", doc_roles),
            _line(literal_anchor_label, wording_items),
            f"Shape: {doc_shape_hint}" if doc_shape_hint else "",
            _line("Stop if", stop_conditions),
            _line("Validate", validator_plan),
            validation_hint,
            compact_rule,
            compact_reply_rule,
            _artifact_rule_line(required_artifacts, kind="checkpoint"),
        ]
    else:
        sections = [
            task_text,
            read_first,
            contract_line,
            direct_pass_line,
            _line("Loop invariants", acceptance_contract),
            _line("Stop if", stop_conditions),
            _line(literal_anchor_label, wording_items),
            _line("Checkpoint", required_artifacts),
            _line("Validate", validator_plan),
            _line("Artifact manifest", artifact_manifest),
            _artifact_rule_line(required_artifacts, kind="checkpoint"),
        ]
    if emit_header:
        if compact_doc_loop:
            sections.append(T3_DOC_COMPILED_HEADER if compiled_doc_contract else T3_DOC_COMPACT_HEADER)
        else:
            sections.append(T3_PROMPT_HEADER)
    sections.append(runtime_bundle)
    return "\n".join(part for part in sections if part)


def _render_t3_resume_prompt(
    *,
    task_description: str,
    runtime_bundle: str,
    required_artifacts: list[str],
    acceptance_contract: list[str],
    stop_conditions: list[str],
    validator_plan: list[str],
    validator_results: list[str],
    resume_delta: ResumeDelta,
    checkpoint_mismatches: list[str],
    emit_header: bool,
    emit_validated_results: bool,
    compact_doc_loop: bool = False,
    compiled_doc_contract: bool = False,
) -> str:
    sections = [
        _resume_line(task_description),
        _line("Preserve", acceptance_contract),
        _line("Stop if", stop_conditions),
        _line("Artifacts", required_artifacts),
        _line("Validate", validator_plan),
        _line("Artifacts pending", resume_delta.pending_artifacts),
        _line("Read before resume", resume_delta.read_targets),
        _line("Carry forward", resume_delta.carryover_items),
        _line("Checkpoint mismatches", checkpoint_mismatches),
    ]
    if emit_validated_results:
        sections.insert(4, _line("Validated", validator_results))
    if compact_doc_loop:
        compact_rule = T3_DOC_COMPILED_RESUME_RULE if compiled_doc_contract else T3_DOC_COMPACT_RULE
        compact_reply_rule = T3_DOC_COMPILED_REPLY_RULE if compiled_doc_contract else T3_DOC_COMPACT_REPLY_RULE
        validation_hint = "" if compiled_doc_contract else T3_DOC_VALIDATION_HINT
        sections.extend(
            [
                validation_hint,
                compact_rule,
                compact_reply_rule,
            ]
        )
    if emit_header:
        if compact_doc_loop:
            sections.append(T3_DOC_COMPILED_HEADER if compiled_doc_contract else T3_DOC_COMPACT_HEADER)
        else:
            sections.append(T3_PROMPT_HEADER)
    sections.append(runtime_bundle)
    return "\n".join(part for part in sections if part)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
            continue
        base[key] = value
    return base


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _artifact_rule_line(required_artifacts: list[str], *, kind: str) -> str:
    aclx_path = next((item for item in _normalize_items(required_artifacts) if item.lower().endswith(".aclx")), "")
    if not aclx_path:
        return ""
    if kind == "checkpoint":
        return (
            f"Checkpoint rule: create parent dirs if needed, then copy the final ACL-X bundle line exactly into {aclx_path} as one raw line; "
            "do not add quotes or escapes, and do not reread or byte-compare it unless required."
        )
    return (
        f"Artifact rule: create parent dirs if needed, then copy the final ACL-X bundle line exactly into {aclx_path} as one raw line "
        "unless the task explicitly requires a different state line; do not add quotes or escapes, and do not reread it unless required."
    )


def _has_aclx_artifact(required_artifacts: list[str]) -> bool:
    return any(item.lower().endswith(".aclx") for item in _normalize_items(required_artifacts))
