from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from functools import lru_cache
import ntpath
from pathlib import Path
import posixpath
import re
from typing import Any

import yaml

from .adapters import ACLXAdapter
from .codec import ACLXCodec
from .contract import RuntimeNeeds, TaskContract
from .contract_normalizer import normalize_task_to_contract
from .contract_pipeline import resolve_task_contract
from .metrics import model_token_count
from .tier_projector import project_tier


DEFAULT_HYBRID_MAP: dict[str, Any] = {
    "rules": {
        "H0": "ACLX machine-state; NL final.",
        "H1": "Stack-first, smallest useful set.",
        "H2": "Single lane; no overlap.",
        "H3": "Cache-first; avoid rereads.",
        "H4": "Minimal commands only.",
        "H5": "Verify risky claims before handoff.",
        "H6": "Stop on missing facts or scope drift.",
    },
    "profiles": {
        "default": ["H0", "H1", "H2", "H3", "H6"],
        "inspect": ["H0", "H2", "H3", "H6"],
        "implement": ["H0", "H1", "H2", "H3", "H4", "H5", "H6"],
        "review": ["H0", "H1", "H2", "H3", "H5", "H6"],
        "benchmark": ["H0", "H2", "H3", "H4", "H5", "H6"],
        "debug": ["H0", "H1", "H2", "H3", "H4", "H5", "H6"],
        "research": ["H0", "H1", "H2", "H3", "H6"],
    },
    "max_items_per_list": 4,
    "task_shapes": {
        "single_surface": "t0",
        "delegated_once": "t1",
        "shared_state": "t2",
        "multi_step": "t2",
        "loop": "t3",
    },
    "tiers": {
        "t0": {
            "label": "nl-lean",
            "nl_ratio": 1.0,
            "aclx_ratio": 0.0,
            "bridge_mode": "none",
            "reasoning_effort": "medium",
            "guard_mode": "selective",
            "max_guard_lines": 1,
            "generic_reasoning_effort": "low",
            "exact_output_reasoning_effort": "low",
            "use_aclx": False,
            "max_items": 0,
            "max_state_items": 0,
            "max_evidence_items": 0,
            "max_risk_items": 0,
            "max_next_actions": 0,
            "include_completed": False,
        },
        "t1": {
            "label": "handoff-lite",
            "nl_ratio": 0.18,
            "aclx_ratio": 0.82,
            "bridge_mode": "bundle",
            "reasoning_effort": "low",
            "use_aclx": True,
            "include_transport_meta": False,
            "include_profile_state": False,
            "include_task_ref_state": False,
            "emit_machine_hint": False,
            "support_label": "Single handoff contract:",
            "include_cwd": False,
            "include_constraints": True,
            "include_next_hint": True,
            "include_avoid_hint": False,
            "max_items": 1,
            "max_state_items": 0,
            "max_evidence_items": 2,
            "max_risk_items": 1,
            "max_next_actions": 2,
            "include_completed": False,
        },
        "t2": {
            "label": "balanced",
            "nl_ratio": 0.34,
            "aclx_ratio": 0.66,
            "bridge_mode": "session",
            "reasoning_effort": "",
            "use_aclx": True,
            "include_transport_meta": False,
            "include_profile_state": False,
            "include_task_ref_state": False,
            "emit_machine_hint": False,
            "support_label": "Machine contract:",
            "include_cwd": False,
            "include_constraints": True,
            "include_next_hint": True,
            "include_avoid_hint": True,
            "max_items": 2,
            "max_state_items": 1,
            "max_evidence_items": 1,
            "max_risk_items": 0,
            "max_next_actions": 0,
            "include_completed": False,
        },
        "t3": {
            "label": "loop-heavy",
            "nl_ratio": 0.2,
            "aclx_ratio": 0.75,
            "bridge_mode": "session",
            "reasoning_effort": "",
            "use_aclx": True,
            "include_transport_meta": False,
            "include_profile_state": False,
            "include_task_ref_state": False,
            "emit_machine_hint": False,
            "support_label": "Machine contract:",
            "include_cwd": False,
            "include_constraints": True,
            "include_next_hint": True,
            "include_avoid_hint": True,
            "max_items": 3,
            "max_state_items": 1,
            "max_evidence_items": 1,
            "max_risk_items": 1,
            "max_next_actions": 0,
            "include_completed": True,
            "doc_loop_low_task_contract_max_lines": 6,
            "doc_loop_low_task_contract_max_chars": 600,
            "task_contract_max_lines": 14,
            "task_contract_max_chars": 900,
        },
    },
}
DEFAULT_HYBRID_MAP_PATH = Path(__file__).resolve().parents[2] / "configs" / "hybrid_router_map.yaml"
HYBRID_ROUTER_TIER_FILES_KEY = "tier_files"


@dataclass(slots=True)
class HybridTaskSpec:
    task: str
    profile: str = "default"
    lane: str = ""
    tier: str | None = None
    contract: TaskContract | None = None
    task_shape: str | None = None
    goal: str | None = None
    cwd: str | None = None
    expected_handoffs: int = 0
    expected_rounds: int = 1
    child_agents: int = 0
    shared_state: bool = False
    real_handoff_started: bool = False
    real_loop_started: bool = False
    resume_depth: int = 0
    completed: list[str] = field(default_factory=list)
    current_state: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HybridPromptPayload:
    prompt: str
    aclx_bundle: str
    profile: str
    lane: str
    tier: str
    bridge_mode: str
    codes: list[str]
    legend: dict[str, str]
    _prompt_tokens: int | None = None
    _aclx_tokens: int | None = None

    @property
    def prompt_tokens(self) -> int:
        if self._prompt_tokens is None:
            self._prompt_tokens = model_token_count(self.prompt)
        return self._prompt_tokens

    @property
    def aclx_tokens(self) -> int:
        if self._aclx_tokens is None:
            self._aclx_tokens = model_token_count(self.aclx_bundle)
        return self._aclx_tokens


@dataclass(slots=True)
class HybridRouteDecision:
    task_shape: str
    tier: str
    bridge_mode: str
    expected_handoffs: int
    expected_rounds: int
    child_agents: int
    shared_state: bool
    signals: list[str] = field(default_factory=list)


class ACLXHybridPromptBuilder:
    _T1_PATH_CITATION_RE = re.compile(
        r"^(?P<prefix>.+?)\s+"
        r"(?P<verb>names|cites|references|mentions)\s+"
        r"`?(?P<path>(?:[A-Za-z]:[\\/]|(?:\.\.?[\\/])|(?:[\w.-]+[\\/]))[^`;,\s]+(?:[\\/][^`;,\s]+)*)`?\s*$",
        re.IGNORECASE,
    )
    _T1_TASK_PATH_RE = re.compile(
        r"`?(?P<path>(?:[A-Za-z]:[\\/]|(?:\.\.?[\\/])|(?:[\w.-]+[\\/]))[^`;,\s]+(?:[\\/][^`;,\s]+)*)`?",
        re.IGNORECASE,
    )

    def __init__(self, adapter: ACLXAdapter | None = None, config_path: str | Path | None = None) -> None:
        self.adapter = adapter or ACLXAdapter()
        self.config_path = str(Path(config_path)) if config_path is not None else None

    def build_prompt(
        self,
        spec: HybridTaskSpec,
        *,
        aclx_bundle: str | None = None,
    ) -> HybridPromptPayload:
        contract = _contract_for_spec(spec)
        spec = _spec_with_runtime_defaults(spec, contract)
        profile = spec.profile or infer_hybrid_profile(spec.task)
        rule_map = load_hybrid_router_map(self.config_path)
        if spec.tier:
            tier = str(spec.tier)
            bridge_mode = str(self._tier_config(rule_map, tier).get("bridge_mode", "none"))
        else:
            route = classify_hybrid_route(
                spec.task,
                contract=contract,
                profile=profile,
                task_shape=spec.task_shape,
                expected_handoffs=spec.expected_handoffs,
                expected_rounds=spec.expected_rounds,
                child_agents=spec.child_agents,
                shared_state=spec.shared_state,
                real_handoff_started=spec.real_handoff_started,
                real_loop_started=spec.real_loop_started,
                resume_depth=spec.resume_depth,
                rule_map=rule_map,
            )
            tier = route.tier
            bridge_mode = route.bridge_mode
        tier_config = self._tier_config(rule_map, tier)
        max_items = int(tier_config.get("max_items", rule_map.get("max_items_per_list", 4)))
        bundle = ""
        if tier_config.get("use_aclx", True):
            bundle = aclx_bundle or self._build_transport_bundle(
                spec,
                contract,
                profile,
                task_ref="nl",
                max_items=max_items,
                tier_config=tier_config,
                tier=tier,
            )
        prompt = self._compose_prompt(spec, contract=contract, bundle=bundle, tier_config=tier_config, tier=tier)
        return HybridPromptPayload(
            prompt=prompt,
            aclx_bundle=bundle,
            profile=profile,
            lane=spec.lane,
            tier=tier,
            bridge_mode=bridge_mode,
            codes=[],
            legend={},
        )

    def build_resume_prompt(
        self,
        *,
        task_code: str,
        profile: str,
        lane: str,
        round_label: str,
        snapshot_code: str,
        issue_codes: list[str] | None = None,
        next_actions: list[str] | None = None,
        delta_items: list[str] | None = None,
        required_artifacts: list[str] | None = None,
        acceptance_contract: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        aclx_bundle: str | None = None,
    ) -> HybridPromptPayload:
        bundle = aclx_bundle or self._build_handle_bundle(
            task_code=task_code,
            snapshot_code=snapshot_code,
            finding_codes=list(issue_codes or []),
            delta_codes=list(delta_items or []),
        )
        resume_line = self._resume_line(task_code, snapshot_code, list(next_actions or []))
        preserve_line = self._hint_line("Preserve", list(acceptance_contract or []))
        artifact_line = self._hint_line("Artifacts", list(required_artifacts or []))
        avoid_line = self._hint_line("Avoid", list(stop_conditions or []))
        prompt = "\n".join(
            line
            for line in [
                resume_line,
                preserve_line,
                artifact_line,
                avoid_line,
                bundle,
            ]
            if line
        )
        return HybridPromptPayload(
            prompt=prompt,
            aclx_bundle=bundle,
            profile=profile,
            lane=lane,
            tier="t3",
            bridge_mode="session",
            codes=[],
            legend={},
        )

    def build_handle_bundle(
        self,
        *,
        task_code: str,
        snapshot_code: str,
        finding_codes: list[str] | None = None,
        delta_codes: list[str] | None = None,
    ) -> str:
        return self._build_handle_bundle(
            task_code=task_code,
            snapshot_code=snapshot_code,
            finding_codes=list(finding_codes or []),
            delta_codes=list(delta_codes or []),
        )

    def _build_transport_bundle(
        self,
        spec: HybridTaskSpec,
        contract: TaskContract,
        profile: str,
        *,
        task_ref: str,
        snapshot_code: str | None = None,
        max_items: int,
        tier_config: dict[str, Any],
        tier: str,
    ) -> str:
        state_parts: list[str] = []
        if tier_config.get("include_profile_state", True):
            state_parts.append(f"p={profile}")
        if spec.lane:
            state_parts.append(f"l={self._slug(spec.lane)}")
        if tier_config.get("include_task_ref_state", True) and task_ref:
            state_parts.append(f"t={task_ref}")
        if snapshot_code:
            state_parts.append(f"s={self._slug(snapshot_code)}")
        state_parts.extend(
            self._trim(
                [self._slug(value) for value in spec.current_state],
                int(tier_config.get("max_state_items", max_items)),
            )
        )
        evidence = self._transport_evidence(spec, contract, max_items, tier_config)
        risks = self._transport_risks(spec, contract, max_items, tier_config)
        next_actions = self._transport_next_actions(contract, max_items, tier_config, tier)
        handoff = {
            "current_state": [";".join(state_parts)] if state_parts else [],
            "completed": self._transport_completed(spec, max_items, tier_config),
            "next_actions": next_actions,
            "risks": risks,
            "evidence": evidence,
        }
        if tier_config.get("include_transport_meta", True):
            handoff.update(
                {
                    "priority": 1,
                    "certainty": 0.92,
                    "scope": profile,
                    "source": "aclx.hybrid",
                }
            )
        compact_handoff = {key: value for key, value in handoff.items() if value not in (None, [], "")}
        return self.adapter.handoff_obj_to_aclx(compact_handoff, mode="c")

    def _build_handle_bundle(
        self,
        *,
        task_code: str,
        snapshot_code: str,
        finding_codes: list[str],
        delta_codes: list[str],
    ) -> str:
        # The NL resume line already names the task; keep the machine handle to the minimal resume cursor.
        records = ["h|c|c0|1", f"p|s.{self._slug(snapshot_code)}"]
        records.extend(f"p|f.{self._slug(code)}" for code in self._trim(finding_codes, 4))
        records.extend(f"p|d.{self._slug(code)}" for code in self._trim(delta_codes, 4))
        payload = "~".join(records)
        checksum = ACLXCodec.checksum(payload)
        return payload + f"~k|{checksum}"

    def _transport_evidence(
        self,
        spec: HybridTaskSpec,
        contract: TaskContract,
        max_items: int,
        tier_config: dict[str, Any],
    ) -> list[str]:
        evidence: list[str] = []
        keep = int(tier_config.get("max_evidence_items", max_items))
        if keep <= 0:
            return evidence
        scope_items = self._trim([self._compact_path(value, spec.cwd) for value in contract.scope_in], keep)
        prefer_scope_first = str(spec.tier or "").lower() == "t2" and str(tier_config.get("bridge_mode", "")).lower() == "session"
        if prefer_scope_first and scope_items:
            evidence.append("in=" + ",".join(scope_items))
        output_items = self._trim([self._slug(value) for value in _contract_outputs(contract)], keep)
        if output_items:
            evidence.append("out=" + ",".join(output_items))
        delta_items: list[str] = []
        if tier_config.get("include_constraints", True):
            delta_items = self._trim([self._slug(value) for value in _contract_constraints(contract)], keep)
        if delta_items:
            evidence.append("d=" + ",".join(delta_items))
        if not prefer_scope_first and scope_items:
            evidence.append("in=" + ",".join(scope_items))
        input_items = self._trim([self._slug(value) for value in contract.input_artifacts], keep)
        if input_items:
            evidence.append("rd=" + ",".join(input_items))
        if spec.cwd and tier_config.get("include_cwd", False):
            compact_cwd = self._compact_path(spec.cwd, spec.cwd)
            if compact_cwd and compact_cwd != ".":
                evidence.append("cwd=" + compact_cwd)
        return evidence[:keep]

    def _transport_risks(
        self,
        spec: HybridTaskSpec,
        contract: TaskContract,
        max_items: int,
        tier_config: dict[str, Any],
    ) -> list[str]:
        risks: list[str] = []
        keep = int(tier_config.get("max_risk_items", max_items))
        if keep <= 0:
            return risks
        scope_out = self._trim([self._slug(value) for value in contract.scope_out], keep)
        if scope_out:
            risks.append("av=" + ",".join(scope_out))
        stop_items = self._trim([self._slug(value) for value in contract.stop_conditions], keep)
        if stop_items:
            risks.append("stop=" + ",".join(stop_items))
        issue_items = self._trim([self._slug(value) for value in spec.risks], keep)
        if issue_items:
            risks.append("iss=" + ",".join(issue_items))
        return risks[:keep]

    def _transport_next_actions(
        self,
        contract: TaskContract,
        max_items: int,
        tier_config: dict[str, Any],
        tier: str,
    ) -> list[str]:
        keep = int(tier_config.get("max_next_actions", max_items))
        values = contract.next_actions
        if tier == "t1":
            values = self._filter_t1_next_actions(values)
        items = self._trim([self._slug(value) for value in values], keep)
        return ["nx=" + ",".join(items)] if items else []

    def _transport_completed(self, spec: HybridTaskSpec, max_items: int, tier_config: dict[str, Any]) -> list[str]:
        if not tier_config.get("include_completed", True):
            return []
        items = self._trim([self._slug(value) for value in spec.completed], max_items)
        return ["done=" + ",".join(items)] if items else []

    def _compose_prompt(
        self,
        spec: HybridTaskSpec,
        *,
        contract: TaskContract,
        bundle: str,
        tier_config: dict[str, Any],
        tier: str,
    ) -> str:
        task_text = spec.task.strip()
        if not bundle:
            return task_text
        lines = [task_text]
        lines.extend(self._nl_support_lines(spec, contract, tier_config, tier=tier))
        lines.append(bundle)
        return "\n".join(line for line in lines if line)

    def _nl_support_lines(
        self,
        spec: HybridTaskSpec,
        contract: TaskContract,
        tier_config: dict[str, Any],
        *,
        tier: str,
    ) -> list[str]:
        if tier == "t1":
            return self._t1_support_lines(spec, contract, tier_config)
        if tier == "t2":
            return self._t2_support_lines(spec, contract, tier_config)
        if tier == "t3":
            return self._t3_support_lines(spec, contract, tier_config)
        try:
            nl_ratio = float(tier_config.get("nl_ratio", 0.0))
        except (TypeError, ValueError):
            nl_ratio = 0.0
        try:
            aclx_ratio = float(tier_config.get("aclx_ratio", 0.0))
        except (TypeError, ValueError):
            aclx_ratio = 0.0
        if nl_ratio <= 0.0 and aclx_ratio >= 1.0:
            return []
        lines: list[str] = []
        support_label = str(tier_config.get("support_label", "") or "").strip()
        if support_label:
            lines.append(support_label)
        elif tier_config.get("emit_machine_hint", True) and (aclx_ratio > 0.0 or nl_ratio > 0.0):
            lines.append("ACL-X state:")
        if tier_config.get("include_next_hint", nl_ratio >= 0.85):
            next_hint = self._hint_line("Next", contract.next_actions)
            if next_hint:
                lines.append(next_hint)
        if tier_config.get("include_avoid_hint", nl_ratio >= 0.95):
            avoid_hint = self._hint_line("Avoid", contract.scope_out + contract.stop_conditions)
            if avoid_hint:
                lines.append(avoid_hint)
        return lines

    def _t1_support_lines(self, spec: HybridTaskSpec, contract: TaskContract, tier_config: dict[str, Any]) -> list[str]:
        try:
            nl_ratio = float(tier_config.get("nl_ratio", 0.0))
        except (TypeError, ValueError):
            nl_ratio = 0.0
        try:
            aclx_ratio = float(tier_config.get("aclx_ratio", 0.0))
        except (TypeError, ValueError):
            aclx_ratio = 0.0
        if nl_ratio <= 0.0 and aclx_ratio >= 1.0:
            return []

        lines = [str(tier_config.get("support_label", "") or "").strip() or "Single handoff contract:"]
        lines.append(
            "One reviewer pass only. Use it only if direct inspection still leaves a material ambiguity or missing fact for the required result, and that reviewer can inspect the same named inputs directly in the current workspace without extra setup or policy changes."
        )
        lines.append("Do not use the reviewer pass to reconfirm a conclusion already clear from direct inspection.")
        lines.append("Do not read skill/router docs or probe commands to discover delegation.")
        must_write = self._hint_line("Must write", _display_outputs(spec, contract), max_items=2, max_chars=120)
        if must_write:
            lines.append(must_write)
        if tier_config.get("include_constraints", False):
            done_when = self._hint_line(
                "Done when",
                self._filter_t1_done_when(spec.task, _display_outputs(spec, contract), _contract_constraints(contract)),
                max_items=3,
                max_chars=160,
            )
            if done_when:
                lines.append(done_when)
        if tier_config.get("include_next_hint", False):
            next_hint = self._hint_line(
                "Next",
                self._filter_t1_next_actions(contract.next_actions),
                max_items=max(1, int(tier_config.get("max_next_actions", 2))),
                max_chars=96,
            )
            if next_hint:
                lines.append(next_hint)
        if tier_config.get("include_avoid_hint", False):
            avoid_hint = self._hint_line("Avoid", contract.scope_out + contract.stop_conditions, max_items=2, max_chars=96)
            if avoid_hint:
                lines.append(avoid_hint)
        lines.append(
            "If the required conclusion is already clear from direct inspection, or no such reviewer is immediately readable, use named inputs as working evidence, create required outputs directly, and skip output-path probes, artifact rereads, extra line-number extraction, workspace listings, and code excerpts unless explicitly required or a fact remains ambiguous."
        )
        return [line for line in lines if line]

    @classmethod
    def _filter_t1_next_actions(cls, values: list[str]) -> list[str]:
        return [value for value in values if not cls._is_t1_delegation_boilerplate(value)]

    @classmethod
    def _filter_t1_constraints(cls, values: list[str]) -> list[str]:
        return [value for value in values if not cls._is_t1_delegation_boilerplate(value)]

    @classmethod
    def _filter_t1_done_when(cls, task: str, outputs: list[str], values: list[str]) -> list[str]:
        filtered = cls._filter_t1_constraints(values)
        if not filtered:
            return filtered
        task_paths = cls._extract_t1_task_paths(task)
        output_paths = {cls._normalize_t1_path_text(value) for value in outputs if cls._normalize_t1_path_text(value)}
        deduped = [
            value
            for value in filtered
            if not cls._is_redundant_t1_path_citation(value, task_paths=task_paths, output_paths=output_paths)
        ]
        return deduped or filtered

    @staticmethod
    def _is_t1_delegation_boilerplate(value: str) -> bool:
        text = " ".join(str(value or "").strip().lower().split())
        if text in {
            "delegate once",
            "delegate exactly once",
            "delegate one pass",
            "delegate exactly one pass",
            "delegate a single pass",
            "delegate single pass",
            "delegate one handoff",
            "delegate single handoff",
            "one reviewer pass",
            "exactly one reviewer pass",
            "single reviewer pass",
        }:
            return True
        if text.startswith("delegate ") and any(token in text for token in (" once", "single", "one pass", "one handoff")):
            return True
        return "reviewer pass" in text and any(token in text for token in ("once", "single", "exactly one", "one "))

    @classmethod
    def _is_redundant_t1_path_citation(cls, value: str, *, task_paths: set[str], output_paths: set[str]) -> bool:
        match = cls._T1_PATH_CITATION_RE.match(str(value or "").strip())
        if match is None:
            return False
        cited_path = cls._normalize_t1_path_text(match.group("path"))
        if not cited_path or cited_path in output_paths:
            return False
        return cited_path in task_paths

    @classmethod
    def _extract_t1_task_paths(cls, task: str) -> set[str]:
        return {
            cls._normalize_t1_path_text(match.group("path"))
            for match in cls._T1_TASK_PATH_RE.finditer(str(task or ""))
            if cls._normalize_t1_path_text(match.group("path"))
        }

    @staticmethod
    def _normalize_t1_path_text(value: str) -> str:
        return str(value or "").strip().replace("\\", "/").replace("`", "").lower()

    def _t2_support_lines(self, spec: HybridTaskSpec, contract: TaskContract, tier_config: dict[str, Any]) -> list[str]:
        lines = [str(tier_config.get("support_label", "") or "").strip() or "Machine contract:"]
        must_write = self._hint_line("Must write", _display_outputs(spec, contract))
        if must_write:
            lines.append(must_write)
        done_when = self._hint_line("Done when", _contract_constraints(contract))
        if done_when:
            lines.append(done_when)
        return [line for line in lines if line]

    def _t3_support_lines(self, spec: HybridTaskSpec, contract: TaskContract, tier_config: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        invariants = self._hint_line("Loop invariants", _contract_constraints(contract))
        if invariants:
            lines.append(invariants)
        checkpoint = self._hint_line("Checkpoint", _display_outputs(spec, contract))
        if checkpoint:
            lines.append(checkpoint)
        return lines

    @staticmethod
    def _hint_line(prefix: str, values: list[str], *, max_items: int = 2, max_chars: int = 84) -> str:
        cleaned = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not cleaned:
            return ""
        text = "; ".join(cleaned[:max_items])
        if len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."
        return f"{prefix}: {text}"

    @staticmethod
    def _resume_action_hint(next_actions: list[str]) -> str:
        actions = [value.strip().lower() for value in next_actions if str(value).strip()]
        if not actions:
            return ""
        if any(
            any(token in value for token in ("apply", "fix", "revise", "update", "repair"))
            for value in actions
        ):
            return "Revise."
        if any(
            any(token in value for token in ("reply", "respond", "return"))
            for value in actions
        ):
            return "Reply."
        return "Resume."

    @classmethod
    def _resume_line(cls, task_code: str, snapshot_code: str, next_actions: list[str]) -> str:
        action = cls._resume_action_hint(next_actions)
        if action and action != "Resume.":
            return f"{action[:-1]} {task_code} {snapshot_code}."
        return f"Resume {task_code} {snapshot_code}."

    def _codes_for_profile(self, rule_map: dict[str, Any], profile: str) -> list[str]:
        profiles = rule_map.get("profiles", {})
        selected = profiles.get(profile) or profiles.get("default") or []
        return [str(code) for code in selected if code in rule_map.get("rules", {})]

    @staticmethod
    def _tier_config(rule_map: dict[str, Any], tier: str) -> dict[str, Any]:
        tiers = rule_map.get("tiers", {})
        selected = tiers.get(tier) or tiers.get("t2") or {}
        return dict(selected)

    @staticmethod
    def _legend_line(legend: dict[str, str]) -> str:
        parts = [f"{code}={text}" for code, text in legend.items()]
        return "Legend: " + " ".join(parts)

    @staticmethod
    def _trim(values: list[str], max_items: int) -> list[str]:
        if max_items <= 0:
            return []
        cleaned = []
        for value in values:
            text = str(value or "").strip()
            if text:
                cleaned.append(text)
            if len(cleaned) >= max_items:
                break
        return cleaned

    @staticmethod
    def _compact_path(value: str, cwd: str | None) -> str:
        text = str(value or "").strip().replace("\\", "/")
        if not text:
            return ""
        if cwd:
            base = str(cwd or "").strip().replace("\\", "/")
            relative = _relative_path_text(text, base)
            if relative is not None:
                return relative
            try:
                rel = Path(text).resolve().relative_to(Path(cwd).resolve())
            except Exception:
                return text
            return rel.as_posix() or "."
        return text

    @staticmethod
    def _slug(value: str) -> str:
        return str(value or "").strip().replace("\\", "/").replace(" ", "_")

    @classmethod
    def _atom(cls, prefix: str, value: str) -> str:
        text = cls._slug(value).replace("_", "-")
        if "/" in text:
            parts = [part for part in text.split("/") if part]
            if len(parts) > 2:
                text = "/".join(parts[-2:])
        if len(text) > 18:
            text = text[:9] + "-" + text[-8:]
        atom = f"{prefix}.{text}" if text else prefix
        return atom[:24]


def _relative_path_text(target: str, base: str) -> str | None:
    relative = _relative_windows_path(target, base)
    if relative is not None:
        return relative
    return _relative_posix_path(target, base)


def _relative_windows_path(target: str, base: str) -> str | None:
    if not (_looks_like_windows_absolute_path(target) and _looks_like_windows_absolute_path(base)):
        return None
    target_raw = target.replace("/", "\\")
    base_raw = base.replace("/", "\\")
    target_norm = ntpath.normcase(ntpath.normpath(target_raw))
    base_norm = ntpath.normcase(ntpath.normpath(base_raw))
    prefix = base_norm.rstrip("\\")
    if target_norm == base_norm:
        return "."
    if not target_norm.startswith(prefix + "\\"):
        return None
    return ntpath.relpath(target_raw, base_raw).replace("\\", "/")


def _relative_posix_path(target: str, base: str) -> str | None:
    if not (target.startswith("/") and base.startswith("/")):
        return None
    target_norm = posixpath.normpath(target)
    base_norm = posixpath.normpath(base)
    prefix = base_norm.rstrip("/")
    if target_norm == base_norm:
        return "."
    if not target_norm.startswith(prefix + "/"):
        return None
    return posixpath.relpath(target_norm, base_norm)


def _looks_like_windows_absolute_path(value: str) -> bool:
    text = str(value or "").strip()
    return bool(re.match(r"^[A-Za-z]:[\\/]", text)) or text.startswith("\\\\")


@lru_cache(maxsize=1024)
def infer_hybrid_profile(task: str) -> str:
    lowered = (task or "").lower()
    if any(token in lowered for token in ("review", "audit", "risk", "finding")):
        return "review"
    if any(token in lowered for token in ("bench", "metric", "token", "latency", "perf")):
        return "benchmark"
    if any(token in lowered for token in ("debug", "fix", "failure", "trace", "bug")):
        return "debug"
    if any(token in lowered for token in ("implement", "rewrite", "wire", "patch", "modify")):
        return "implement"
    if any(token in lowered for token in ("inspect", "map", "locate", "trace", "read-only")):
        return "inspect"
    if any(token in lowered for token in ("research", "investigate", "compare", "synthesize")):
        return "research"
    return "default"


def classify_hybrid_route(
    task: str,
    *,
    contract: TaskContract | None = None,
    profile: str | None = None,
    task_shape: str | None = None,
    expected_handoffs: int = 0,
    expected_rounds: int = 1,
    child_agents: int = 0,
    shared_state: bool = False,
    real_handoff_started: bool = False,
    real_loop_started: bool = False,
    resume_depth: int = 0,
    rule_map: dict[str, Any] | None = None,
) -> HybridRouteDecision:
    if contract is None:
        effective_contract = normalize_task_to_contract(
            task,
            expected_handoffs=expected_handoffs,
            expected_rounds=expected_rounds,
            child_agents=child_agents,
            shared_state=shared_state,
        )
    else:
        effective_contract = _overlay_route_runtime(
            contract,
            expected_handoffs=expected_handoffs,
            expected_rounds=expected_rounds,
            child_agents=child_agents,
            shared_state=shared_state,
        )
    projection = project_tier(
        task,
        contract=effective_contract,
        task_shape=task_shape,
        real_handoff_started=real_handoff_started,
        real_loop_started=real_loop_started,
        resume_depth=resume_depth,
        rule_map=rule_map or DEFAULT_HYBRID_MAP,
    )
    return HybridRouteDecision(
        task_shape=projection.task_shape,
        tier=projection.tier,
        bridge_mode=projection.bridge_mode,
        expected_handoffs=projection.expected_handoffs,
        expected_rounds=projection.expected_rounds,
        child_agents=projection.child_agents,
        shared_state=projection.shared_state,
        signals=list(projection.signals),
    )


def infer_hybrid_task_shape(
    task: str,
    *,
    contract: TaskContract | None = None,
    profile: str | None = None,
    task_shape: str | None = None,
    expected_handoffs: int = 0,
    expected_rounds: int = 1,
    child_agents: int = 0,
    shared_state: bool = False,
    real_handoff_started: bool = False,
    real_loop_started: bool = False,
    resume_depth: int = 0,
    rule_map: dict[str, Any] | None = None,
) -> str:
    decision = classify_hybrid_route(
        task,
        contract=contract,
        profile=profile,
        task_shape=task_shape,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=shared_state,
        real_handoff_started=real_handoff_started,
        real_loop_started=real_loop_started,
        resume_depth=resume_depth,
        rule_map=rule_map,
    )
    return decision.task_shape


def infer_hybrid_tier(
    task: str,
    *,
    contract: TaskContract | None = None,
    profile: str | None = None,
    task_shape: str | None = None,
    expected_handoffs: int = 0,
    expected_rounds: int = 1,
    child_agents: int = 0,
    shared_state: bool = False,
    real_handoff_started: bool = False,
    real_loop_started: bool = False,
    resume_depth: int = 0,
    rule_map: dict[str, Any] | None = None,
) -> str:
    return classify_hybrid_route(
        task,
        contract=contract,
        profile=profile,
        task_shape=task_shape,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=shared_state,
        real_handoff_started=real_handoff_started,
        real_loop_started=real_loop_started,
        resume_depth=resume_depth,
        rule_map=rule_map,
    ).tier


def _contract_for_spec(spec: HybridTaskSpec) -> TaskContract:
    if spec.contract is not None:
        return spec.contract
    return resolve_task_contract(
        spec.task,
        project_root=spec.cwd,
        required_artifacts=spec.outputs,
        acceptance_contract=spec.constraints,
        stop_conditions=spec.stop_conditions,
        next_actions=spec.next_actions,
        scope_in=spec.scope_in,
        scope_out=spec.scope_out,
        inputs=spec.inputs,
        expected_handoffs=spec.expected_handoffs,
        expected_rounds=spec.expected_rounds,
        child_agents=spec.child_agents,
        shared_state=spec.shared_state,
        metadata={"lane": spec.lane, "cwd": spec.cwd or ""},
        build_context=False,
    ).contract


def _spec_with_runtime_defaults(spec: HybridTaskSpec, contract: TaskContract) -> HybridTaskSpec:
    runtime = contract.runtime_needs
    return replace(
        spec,
        contract=contract,
        goal=spec.goal or contract.goal,
        expected_handoffs=max(int(spec.expected_handoffs), int(runtime.expected_handoffs)),
        expected_rounds=max(int(spec.expected_rounds or 1), int(runtime.expected_rounds)),
        child_agents=max(int(spec.child_agents), int(runtime.child_agents)),
        shared_state=bool(spec.shared_state or runtime.shared_state),
    )


def _contract_outputs(contract: TaskContract) -> list[str]:
    return list(contract.output_artifacts)


def _contract_constraints(contract: TaskContract) -> list[str]:
    return list(contract.acceptance_rules or contract.exactness_rules)


def _display_outputs(spec: HybridTaskSpec, contract: TaskContract) -> list[str]:
    if not spec.outputs:
        return _contract_outputs(contract)
    normalized_spec = [str(value).replace("\\", "/").strip() for value in spec.outputs]
    if normalized_spec == _contract_outputs(contract):
        return list(spec.outputs)
    return _contract_outputs(contract)


def _overlay_route_runtime(
    contract: TaskContract,
    *,
    expected_handoffs: int,
    expected_rounds: int,
    child_agents: int,
    shared_state: bool,
) -> TaskContract:
    runtime = RuntimeNeeds.from_dict(contract.runtime_needs.to_dict())
    runtime.expected_handoffs = max(int(runtime.expected_handoffs), int(expected_handoffs))
    runtime.expected_rounds = max(int(runtime.expected_rounds), int(expected_rounds or 1))
    runtime.child_agents = max(int(runtime.child_agents), int(child_agents))
    runtime.shared_state = bool(runtime.shared_state or shared_state)
    if runtime.to_dict() == contract.runtime_needs.to_dict():
        return contract
    return contract.with_updates(runtime_needs=runtime.to_dict())


@lru_cache(maxsize=4)
def load_hybrid_router_map(config_path: str | None = None) -> dict[str, Any]:
    data = deepcopy(DEFAULT_HYBRID_MAP)
    path = Path(config_path) if config_path is not None else DEFAULT_HYBRID_MAP_PATH
    if not path.exists():
        return data
    _load_hybrid_router_config(data, path, seen_paths=set())
    return data


def reset_hybrid_router_map_cache() -> None:
    load_hybrid_router_map.cache_clear()


def _load_hybrid_router_config(base: dict[str, Any], path: Path, *, seen_paths: set[Path]) -> None:
    resolved = path.resolve()
    if resolved in seen_paths:
        return
    seen_paths.add(resolved)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return
    tier_files = loaded.pop(HYBRID_ROUTER_TIER_FILES_KEY, {})
    _deep_merge(base, loaded)
    if not isinstance(tier_files, dict):
        return
    for tier_name, relative_path in sorted(tier_files.items()):
        if not relative_path:
            continue
        tier_path = (path.parent / str(relative_path)).resolve()
        if not tier_path.exists():
            continue
        _load_hybrid_router_config(base, tier_path, seen_paths=seen_paths)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
            continue
        base[key] = value
    return base
