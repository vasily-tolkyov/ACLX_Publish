from __future__ import annotations

import json
import re
import time

from .adapters import ACLXAdapter
from .ir import frame_to_dict
from .transcoder import ACLXTranscoder

TOKEN_RE = re.compile(r"[A-Za-z0-9_.$%@!]+|[^\s]")
_ENCODING = None
_TOKENIZER = None


def approx_token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def benchmark_samples() -> list[dict[str, str]]:
    return [
        {
            "name": "english_structured",
            "text": "Plan the task, report the result, and attach evidence.",
        },
        {
            "name": "english_conditional",
            "text": "If the tool fails, explain the error and update the plan.",
        },
        {
            "name": "chinese_request",
            "text": "\u8bf7\u8bbe\u8ba1\u4e00\u79cd\u9762\u5411 agent \u7684\u6c9f\u901a\u8bed\u8a00\uff0c\u5e76\u8f93\u51fa\u7ed3\u679c\u3002",
        },
    ]


def run_benchmark(transcoder: ACLXTranscoder | None = None) -> list[dict[str, object]]:
    transcoder = transcoder or ACLXTranscoder()
    results = []
    for sample in benchmark_samples():
        text = sample["text"]
        start = time.perf_counter()
        encoded = transcoder.nl_to_aclx(text)
        parsed = transcoder.aclx_to_frame(encoded)
        elapsed_ms = (time.perf_counter() - start) * 1000
        json_ir = json.dumps(frame_to_dict(parsed), ensure_ascii=True, separators=(",", ":"))
        results.append(
            {
                "name": sample["name"],
                "natural_chars": len(text),
                "aclx_chars": len(encoded),
                "json_chars": len(json_ir),
                "natural_tokens": approx_token_count(text),
                "aclx_tokens": approx_token_count(encoded),
                "json_tokens": approx_token_count(json_ir),
                "parse_ms": round(elapsed_ms, 3),
            }
        )
    return results


def tokenizer_name() -> str:
    _load_encoding()
    return _TOKENIZER or "approx"


def model_token_count(text: str) -> int:
    encoding = _load_encoding()
    if encoding is None:
        return approx_token_count(text)
    return len(encoding.encode(text))


def run_tokenizer_benchmark(transcoder: ACLXTranscoder | None = None) -> list[dict[str, object]]:
    transcoder = transcoder or ACLXTranscoder()
    adapter = ACLXAdapter(transcoder=transcoder)
    results = []
    for sample in benchmark_samples():
        text = sample["text"]
        aclx = transcoder.nl_to_aclx(text)
        frame = transcoder.aclx_to_frame(aclx)
        json_ir = json.dumps(frame_to_dict(frame), ensure_ascii=True, separators=(",", ":"))
        tool_json = adapter.aclx_to_tool_json(aclx)
        gloss = transcoder.aclx_to_nl_gloss(aclx)
        results.append(
            {
                "name": sample["name"],
                "tokenizer": tokenizer_name(),
                "natural_tokens": model_token_count(text),
                "aclx_tokens": model_token_count(aclx),
                "tool_json_tokens": model_token_count(tool_json),
                "json_ir_tokens": model_token_count(json_ir),
                "gloss_tokens": model_token_count(gloss),
            }
        )
    return results


def _load_encoding():
    global _ENCODING, _TOKENIZER
    if _TOKENIZER is not None:
        return _ENCODING
    try:
        import tiktoken  # type: ignore
    except Exception:
        _TOKENIZER = "approx"
        _ENCODING = None
        return None
    try:
        _ENCODING = tiktoken.get_encoding("o200k_base")
        _TOKENIZER = "o200k_base"
    except Exception:
        _TOKENIZER = "approx"
        _ENCODING = None
    return _ENCODING
