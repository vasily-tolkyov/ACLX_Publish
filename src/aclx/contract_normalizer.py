from __future__ import annotations

import ntpath
import posixpath
import re
from pathlib import Path
from typing import Any

from .contract import RuntimeNeeds, TaskContract


_EXACTNESS_PATTERNS = (
    "exactly",
    "verbatim",
    "literal",
    "must include",
    "must keep",
    "keep heading",
    "keep the output in markdown",
    "output in markdown",
    "one of ",
)
_SOURCE_REF_PATTERN = re.compile(r"`([^`]+)`|(?P<path>(?:[A-Za-z]:)?[A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9]{1,8})")


def normalize_task_to_contract(
    task_description: str,
    *,
    project_root: str | Path | None = None,
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
    shared_state: bool = False,
    checkpointable: bool | None = None,
    resumable: bool | None = None,
    loop_heavy: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> TaskContract:
    goal = _goal_from_task(task_description)
    source_root = Path(project_root) if project_root is not None else None
    exactness_rules = extract_exactness_rules(task_description)
    source_refs = _normalize_project_paths(extract_source_refs(task_description), source_root)
    source_refs = _inject_workspace_contract_sources(source_refs, source_root, task_description)
    contract_source_data = _load_contract_sources(source_root, source_refs)
    if contract_source_data["exactness_rules"]:
        exactness_rules = _clean_list(exactness_rules + list(contract_source_data["exactness_rules"]))
    if contract_source_data["source_refs"]:
        source_refs = _normalize_project_paths(source_refs + list(contract_source_data["source_refs"]), source_root)
    output_artifacts = _normalize_project_paths(required_artifacts, source_root)
    input_artifacts = _normalize_project_paths(inputs, source_root)
    normalized_scope_in = _normalize_project_paths(scope_in, source_root)
    normalized_scope_out = _normalize_project_paths(scope_out, source_root)
    runtime_needs = infer_runtime_needs(
        task_description,
        expected_handoffs=expected_handoffs,
        expected_rounds=expected_rounds,
        child_agents=child_agents,
        shared_state=shared_state,
        checkpointable=checkpointable,
        resumable=resumable,
        loop_heavy=loop_heavy,
        source_refs=source_refs,
        output_artifacts=output_artifacts,
    )
    validator_kinds = infer_validator_kinds(task_description, acceptance_contract)
    validator_targets = infer_validator_targets(
        task_description,
        required_artifacts=output_artifacts,
        inputs=input_artifacts,
        scope_in=normalized_scope_in,
    )
    return TaskContract(
        goal=goal,
        operation=infer_operation(task_description),
        scope_in=normalized_scope_in,
        scope_out=normalized_scope_out,
        input_artifacts=input_artifacts,
        output_artifacts=output_artifacts,
        exactness_rules=exactness_rules,
        acceptance_rules=_clean_list(acceptance_contract),
        stop_conditions=_clean_list(stop_conditions),
        next_actions=_clean_list(next_actions),
        validator_kinds=validator_kinds,
        validator_targets=validator_targets,
        runtime_needs=runtime_needs,
        source_refs=source_refs,
        metadata=_merge_metadata(
            metadata,
            {
                "contract_sources": list(contract_source_data["contract_sources"]),
                "contract_source_count": len(contract_source_data["contract_sources"]),
            },
        ),
    )


def infer_operation(task_description: str) -> str:
    lowered = str(task_description or "").lower()
    if any(token in lowered for token in ("review", "audit", "finding", "risk")):
        return "review"
    if any(token in lowered for token in ("fix", "repair", "debug", "bug")):
        return "fix"
    if any(token in lowered for token in ("rewrite", "reword", "revise")):
        return "rewrite"
    if any(token in lowered for token in ("implement", "wire", "modify", "patch", "build")):
        return "implement"
    if any(token in lowered for token in ("summarize", "summary", "synthesize")):
        return "summarize"
    if any(token in lowered for token in ("compare", "contrast")):
        return "compare"
    return "inspect"


def infer_runtime_needs(
    task_description: str,
    *,
    expected_handoffs: int,
    expected_rounds: int,
    child_agents: int,
    shared_state: bool,
    checkpointable: bool | None,
    resumable: bool | None,
    loop_heavy: bool | None,
    source_refs: list[str] | None = None,
    output_artifacts: list[str] | None = None,
) -> RuntimeNeeds:
    refs = _clean_list(source_refs)
    outputs = _clean_list(output_artifacts)
    wants_checkpoint = bool(
        checkpointable
        if checkpointable is not None
        else any(item.lower().endswith(".aclx") for item in outputs)
    )
    wants_resume = bool(resumable if resumable is not None else False)
    wants_loop = bool(
        loop_heavy
        if loop_heavy is not None
        else expected_handoffs >= 5 or expected_rounds >= 4
    )
    surface_count = 1
    if refs:
        surface_count += 1
    if outputs:
        surface_count += 1
    coordinated_runtime = bool(
        shared_state
        or wants_checkpoint
        or wants_resume
        or wants_loop
        or expected_handoffs > 0
        or expected_rounds > 1
        or child_agents > 0
    )
    return RuntimeNeeds(
        surface_count=max(1, surface_count),
        expected_handoffs=max(0, int(expected_handoffs)),
        expected_rounds=max(1, int(expected_rounds or 1)),
        child_agents=max(0, int(child_agents)),
        shared_state=coordinated_runtime,
        checkpointable=bool(wants_checkpoint),
        resumable=bool(wants_resume),
        loop_heavy=bool(wants_loop or wants_resume),
    )


def extract_exactness_rules(text: str) -> list[str]:
    rules: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        bullet_line = line[2:].strip() if line.startswith("- ") else line
        lowered = line.lower()
        bullet_lowered = bullet_line.lower()
        if not line:
            continue
        if any(pattern in bullet_lowered for pattern in _EXACTNESS_PATTERNS):
            if line not in seen:
                seen.add(line)
                rules.append(line)
        elif bullet_lowered.startswith(("return ", "keep ", "include ", "preserve ")):
            if " heading " in lowered or "`" in line:
                if line not in seen:
                    seen.add(line)
                    rules.append(line)
    return rules


def extract_source_refs(text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in _SOURCE_REF_PATTERN.finditer(str(text or "")):
        candidate = match.group(1) or match.group("path") or ""
        cleaned = str(candidate).strip().strip(".,")
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        refs.append(cleaned.replace("\\", "/"))
    return refs


def infer_validator_kinds(task_description: str, acceptance_contract: list[str] | None) -> list[str]:
    lowered = str(task_description or "").lower()
    validators: list[str] = []
    if any(token in lowered for token in ("pytest", "unittest", "test", "failing")):
        validators.append("tests")
    if any(token in lowered for token in ("lint", "ruff", "flake8", "mypy")):
        validators.append("static")
    if any(token in lowered for token in ("review", "audit", "finding")):
        validators.append("inspection")
    if any("heading" in item.lower() or "markdown" in item.lower() for item in _clean_list(acceptance_contract)):
        validators.append("content")
    if not validators and _clean_list(acceptance_contract):
        validators.append("acceptance")
    return _clean_list(validators)


def infer_validator_targets(
    task_description: str,
    *,
    required_artifacts: list[str] | None,
    inputs: list[str] | None,
    scope_in: list[str] | None,
) -> list[str]:
    targets = _clean_list(required_artifacts) + _clean_list(inputs) + _clean_list(scope_in)
    if targets:
        return _clean_list(targets)
    return extract_source_refs(task_description)


def contract_hash(contract: TaskContract) -> str:
    return contract.contract_hash()


def load_contract_sources(project_root: str | Path | None, source_refs: list[str] | None) -> dict[str, list[str]]:
    return _load_contract_sources(Path(project_root) if project_root is not None else None, _clean_list(source_refs))


def _goal_from_task(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def _load_contract_sources(root: Path | None, source_refs: list[str]) -> dict[str, list[str]]:
    if root is None or not root.exists():
        return {"contract_sources": [], "exactness_rules": [], "source_refs": []}
    loaded_paths: list[str] = []
    exactness_rules: list[str] = []
    discovered_refs: list[str] = []
    for ref in source_refs:
        normalized = str(ref or "").replace("\\", "/").strip()
        if not normalized:
            continue
        if not _looks_like_contract_source(normalized):
            continue
        path = root / normalized
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        loaded_paths.append(normalized)
        exactness_rules.extend(extract_exactness_rules(text))
        discovered_refs.extend(extract_source_refs(text))
    return {
        "contract_sources": _clean_list(loaded_paths),
        "exactness_rules": _clean_list(exactness_rules),
        "source_refs": _clean_list(discovered_refs),
    }


def _looks_like_contract_source(path_text: str) -> bool:
    lowered = str(path_text or "").lower()
    if lowered.endswith(("task.md", "task.txt", "task.rst")):
        return True
    return lowered.endswith((".md", ".txt", ".rst"))


def _normalize_project_paths(values: list[str] | None, root: Path | None) -> list[str]:
    return _clean_list([_project_relative_path(value, root) for value in list(values or [])])


def _inject_workspace_contract_sources(source_refs: list[str], root: Path | None, task_description: str) -> list[str]:
    refs = list(source_refs or [])
    if root is None or not root.exists():
        return _clean_list(refs)
    lowered = str(task_description or "").replace("\\", "/").lower()
    for candidate in ("TASK.md", "TASK.txt", "TASK.rst"):
        if candidate.lower() not in lowered:
            continue
        path = root / candidate
        if path.exists():
            refs.append(candidate)
    return _clean_list(refs)


def _project_relative_path(value: str, root: Path | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    if root is None:
        return normalized
    base = str(root).strip().replace("\\", "/")
    if not base:
        return normalized
    relative = _relative_under_base(normalized, base, windows=True)
    if relative is not None:
        return relative
    relative = _relative_under_base(normalized, base, windows=False)
    if relative is not None:
        return relative
    return normalized


def _relative_under_base(target: str, base: str, *, windows: bool) -> str | None:
    if windows:
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
    if not (_looks_like_posix_absolute_path(target) and _looks_like_posix_absolute_path(base)):
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


def _looks_like_posix_absolute_path(value: str) -> bool:
    return str(value or "").strip().startswith("/")


def _merge_metadata(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    for key, value in dict(right or {}).items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _clean_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = text.replace("\\", "/") if "/" in text or "\\" in text else text
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned
