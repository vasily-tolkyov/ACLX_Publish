from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .loader import estimate_tokens


@dataclass(slots=True)
class ToolSummary:
    kind: str
    source: str
    summary: str
    reduction_ratio: float
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.to_text())

    def to_text(self) -> str:
        suffix = ""
        if self.details:
            compact = json.dumps(self.details, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            suffix = f" details={compact}"
        return (
            f"tool_summary kind={self.kind} source={self.source} reduction={self.reduction_ratio:.2f} "
            f"summary={self.summary}{suffix}"
        )


def summarize_bash(command: str, stdout: str, returncode: int) -> ToolSummary:
    kind = _classify_command(command)
    interesting = _select_interesting_output(stdout, returncode)
    summary = f"cmd={_compact(command, 80)} rc={returncode} note={_compact(interesting, 120)}"
    raw_size = max(1, estimate_tokens(command) + estimate_tokens(stdout))
    reduction = max(1.0, raw_size / max(1, estimate_tokens(summary)))
    return ToolSummary(
        kind=kind,
        source="shell",
        summary=summary,
        reduction_ratio=round(reduction, 2),
        details={
            "command": _compact(command, 120),
            "returncode": returncode,
        },
    )


def summarize_file_read(path: str, content: str) -> ToolSummary:
    suffix = Path(path).suffix.lower()
    kind = _classify_suffix(suffix)
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    preview = " | ".join(lines[:3])
    summary = f"path={Path(path).name} lines={len(content.splitlines())} preview={_compact(preview, 120)}"
    raw_size = max(1, estimate_tokens(path) + estimate_tokens(content))
    reduction = max(1.0, raw_size / max(1, estimate_tokens(summary)))
    return ToolSummary(
        kind=kind,
        source="file",
        summary=summary,
        reduction_ratio=round(reduction, 2),
        details={
            "path": str(path),
            "suffix": suffix or "none",
        },
    )


def _classify_command(command: str) -> str:
    text = (command or "").lower()
    if any(token in text for token in ("pytest", "unittest", "npm test", "go test", "cargo test")):
        return "test"
    if any(token in text for token in ("benchmark", "perf", "hyperfine")):
        return "benchmark"
    if any(token in text for token in ("convert", "transcode", "migrate")):
        return "convert"
    if any(token in text for token in ("train", "finetune", "fit ")):
        return "train"
    return "generic"


def _classify_suffix(suffix: str) -> str:
    if suffix == ".py":
        return "py"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".jsonl":
        return "jsonl"
    return "other"


def _select_interesting_output(stdout: str, returncode: int) -> str:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return "no-output"
    if returncode != 0:
        return lines[-1]
    return lines[0] if len(lines) == 1 else lines[-1]


def _compact(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3] + "..."
