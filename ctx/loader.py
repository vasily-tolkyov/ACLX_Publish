from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None


ACLX_SCHEMA_BLOCK = (
    "h|c|c0|1\n"
    "records=h,a,n,e,f,d,r,p,m,k\n"
    "default-visible-runtime=aclx\n"
    "human-boundary=natural-language\n"
    "tool-boundary=native-schema-or-compact-json"
)
TOKEN_RE = re.compile(r"[A-Za-z0-9_.$%@!]+|[^\s]")
_ENCODING = None


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    encoding = _load_encoding()
    if encoding is not None:
        return len(encoding.encode(text))
    return len(TOKEN_RE.findall(text))


def truncate_text(text: str, token_limit: int, *, prefer_acl_separator: bool = False) -> str:
    if token_limit <= 0 or not text:
        return ""
    if estimate_tokens(text) <= token_limit:
        return text
    if prefer_acl_separator and "~" in text:
        parts = [part for part in text.split("~") if part]
        kept = []
        for part in parts:
            candidate = "~".join(kept + [part])
            if estimate_tokens(candidate) > token_limit:
                break
            kept.append(part)
        if kept:
            return "~".join(kept)
    lines = [line for line in text.splitlines() if line.strip()]
    kept_lines = []
    for line in lines:
        candidate = "\n".join(kept_lines + [line])
        if estimate_tokens(candidate) > token_limit:
            break
        kept_lines.append(line)
    if kept_lines:
        return "\n".join(kept_lines)
    chars = []
    for ch in text:
        chars.append(ch)
        if estimate_tokens("".join(chars)) > token_limit:
            chars.pop()
            break
    return "".join(chars)


@dataclass(slots=True)
class ContextLayer:
    name: str
    content: str
    token_budget: int
    priority: int = 0
    required: bool = False
    drop_policy: str = "over_budget"
    header: str | None = None

    def render(self, *, budget: int | None = None) -> str:
        header = self.header or f"[{self.name}]"
        content_budget = self.token_budget if budget is None else max(0, min(self.token_budget, budget))
        content = self._clip_content(content_budget)
        if not content:
            return header if self.required or self.drop_policy == "header_only" else ""
        return f"{header}\n{content}"

    def _clip_content(self, budget: int) -> str:
        if budget <= 0:
            return ""
        if self.drop_policy == "header_only":
            first_line = self.content.splitlines()[0] if self.content else ""
            return truncate_text(first_line, budget, prefer_acl_separator=True)
        return truncate_text(self.content, budget, prefer_acl_separator=True)


@dataclass(slots=True)
class ContextBundle:
    layers: list[ContextLayer] = field(default_factory=list)

    def assemble(self, hard_limit: int) -> str:
        ordered = list(self.layers)
        total = 0
        rendered = []
        for layer in ordered:
            remaining = max(0, hard_limit - total)
            if remaining <= 0 and not layer.required:
                continue
            block = layer.render(budget=remaining)
            if not block:
                continue
            block_tokens = estimate_tokens(block)
            if block_tokens > remaining and remaining > 0:
                block = truncate_text(block, remaining, prefer_acl_separator=True)
                block_tokens = estimate_tokens(block)
            if not block:
                continue
            rendered.append(block)
            total += block_tokens
            if total >= hard_limit:
                break
        assembled = "\n\n".join(part for part in rendered if part)
        if estimate_tokens(assembled) <= hard_limit:
            return assembled
        return truncate_text(assembled, hard_limit, prefer_acl_separator=True)

    @classmethod
    def from_layers(cls, layers: Iterable[ContextLayer]) -> "ContextBundle":
        return cls(layers=list(layers))


def _load_encoding():
    global _ENCODING
    if _ENCODING is not None:
        return _ENCODING
    if tiktoken is None:
        return None
    try:
        _ENCODING = tiktoken.get_encoding("o200k_base")
    except Exception:  # pragma: no cover - fallback path
        _ENCODING = None
    return _ENCODING
