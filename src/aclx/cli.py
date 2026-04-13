from __future__ import annotations

import argparse
import json
import sys

from .adapters import ACLXAdapter
from .delegation import ACLXDelegation, DEFAULT_HEADER
from .hybrid import ACLXHybridPromptBuilder, HybridTaskSpec, infer_hybrid_profile
from .ir import frame_to_dict
from .metrics import run_benchmark, run_tokenizer_benchmark
from .supervisor import main as supervisor_main
from .transcoder import ACLXTranscoder
from .webui import DEFAULT_UI_HOST, DEFAULT_UI_PORT, default_codex_home, main as webui_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACL-X CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_nl = subparsers.add_parser("encode-nl", help="Transcode natural language into ACL-X")
    encode_nl.add_argument("text", nargs="?", help="Input natural language text")
    encode_nl.add_argument("--mode", choices=["c", "t"], default="c")

    gloss = subparsers.add_parser("gloss", help="Render an ACL-X payload into a readable gloss")
    gloss.add_argument("text", nargs="?", help="ACL-X payload")

    json_cmd = subparsers.add_parser("json", help="Render an ACL-X payload as JSON IR")
    json_cmd.add_argument("text", nargs="?", help="ACL-X payload")

    tool_json = subparsers.add_parser("tool-json", help="Convert ACL-X into compact tool-facing JSON")
    tool_json.add_argument("text", nargs="?", help="ACL-X payload")
    tool_json.add_argument("--pretty", action="store_true")

    from_tool_json = subparsers.add_parser("from-tool-json", help="Convert compact tool-facing JSON into ACL-X")
    from_tool_json.add_argument("text", nargs="?", help="Tool JSON payload")

    handoff = subparsers.add_parser("handoff", help="Convert a compact handoff JSON object into ACL-X")
    handoff.add_argument("text", nargs="?", help="Handoff JSON payload")
    handoff.add_argument("--mode", choices=["c", "t"], default="c")

    handoff_json = subparsers.add_parser("handoff-json", help="Extract a compact handoff JSON object from ACL-X")
    handoff_json.add_argument("text", nargs="?", help="ACL-X payload")
    handoff_json.add_argument("--pretty", action="store_true")

    delegate = subparsers.add_parser("delegate", help="Build a minimal child-agent payload from compact handoff JSON")
    delegate.add_argument("text", nargs="?", help="Compact handoff JSON")
    delegate.add_argument("--task", default=DEFAULT_HEADER)
    delegate.add_argument("--mode", choices=["c", "t"], default="c")
    delegate.add_argument("--aclx-only", action="store_true")
    delegate.add_argument("--json", action="store_true", help="Emit compact delegation JSON instead of rendered text")

    delegate_aclx = subparsers.add_parser("delegate-aclx", help="Wrap an ACL-X bundle for child-agent delivery")
    delegate_aclx.add_argument("text", nargs="?", help="ACL-X payload")
    delegate_aclx.add_argument("--task", default=DEFAULT_HEADER)
    delegate_aclx.add_argument("--aclx-only", action="store_true")
    delegate_aclx.add_argument("--json", action="store_true", help="Emit compact delegation JSON instead of rendered text")
    hybrid_prompt = subparsers.add_parser("hybrid-prompt", help="Build a compact ACL-X+NL hybrid prompt")
    hybrid_prompt.add_argument("text", nargs="?", help="Task text")
    hybrid_prompt.add_argument("--profile", help="Optional task profile")
    hybrid_prompt.add_argument("--lane", default="main")
    hybrid_prompt.add_argument("--cwd")
    hybrid_prompt.add_argument("--json", action="store_true", help="Emit prompt metadata as JSON")

    demo = subparsers.add_parser("demo", help="Show a small ACL-X demo")
    demo.add_argument("--mode", choices=["c", "t"], default="c")

    subparsers.add_parser("benchmark", help="Run a small compression benchmark")
    subparsers.add_parser("tokenizer-benchmark", help="Compare natural text, ACL-X, and JSON using the best available tokenizer")
    adapter_benchmark = subparsers.add_parser("adapter-benchmark", help="Run a tight adapter benchmark")
    adapter_benchmark.add_argument("--iterations", type=int, default=1000)
    supervisor = subparsers.add_parser("supervisor", help="ACL-X-first Codex CLI supervisor")
    supervisor.add_argument("args", nargs=argparse.REMAINDER)
    ui = subparsers.add_parser("ui", help="Launch the ACL-X supervisor session viewer")
    ui.add_argument("--host", default=DEFAULT_UI_HOST)
    ui.add_argument("--port", type=int, default=DEFAULT_UI_PORT)
    ui.add_argument("--codex-home", default=str(default_codex_home()))
    ui.add_argument("--open", action="store_true")
    return parser


def read_text(value: str | None) -> str:
    if value is not None:
        return value
    data = sys.stdin.read().strip()
    if not data:
        raise SystemExit("Missing input text")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    transcoder = ACLXTranscoder()
    adapter = ACLXAdapter(transcoder=transcoder)
    delegation = ACLXDelegation(adapter=adapter)
    hybrid = ACLXHybridPromptBuilder(adapter=adapter)

    if args.command == "encode-nl":
        print(transcoder.nl_to_aclx(read_text(args.text), mode=args.mode))
        return 0

    if args.command == "gloss":
        print(transcoder.aclx_to_nl_gloss(read_text(args.text)))
        return 0

    if args.command == "json":
        frame = transcoder.aclx_to_frame(read_text(args.text))
        print(json.dumps(frame_to_dict(frame), indent=2, ensure_ascii=True, sort_keys=True))
        return 0

    if args.command == "tool-json":
        print(adapter.aclx_to_tool_json(read_text(args.text), pretty=args.pretty))
        return 0

    if args.command == "from-tool-json":
        print(adapter.tool_json_to_aclx(read_text(args.text)))
        return 0

    if args.command == "handoff":
        print(adapter.handoff_json_to_aclx(read_text(args.text), mode=args.mode))
        return 0

    if args.command == "handoff-json":
        print(adapter.aclx_to_handoff_json(read_text(args.text), pretty=args.pretty))
        return 0

    if args.command == "delegate":
        payload = delegation.from_handoff_json(
            read_text(args.text),
            task=None if args.task == "-" else args.task,
            mode=args.mode,
            aclx_only=args.aclx_only,
        )
        print(delegation.payload_json(payload) if args.json else payload.render())
        return 0

    if args.command == "delegate-aclx":
        payload = delegation.from_aclx(
            read_text(args.text),
            task=None if args.task == "-" else args.task,
            aclx_only=args.aclx_only,
        )
        print(delegation.payload_json(payload) if args.json else payload.render())
        return 0

    if args.command == "hybrid-prompt":
        task_text = read_text(args.text)
        payload = hybrid.build_prompt(
            HybridTaskSpec(
                task=task_text,
                profile=args.profile or infer_hybrid_profile(task_text),
                lane=args.lane,
                cwd=args.cwd,
            )
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "profile": payload.profile,
                        "lane": payload.lane,
                        "codes": payload.codes,
                        "prompt_tokens": payload.prompt_tokens,
                        "aclx_tokens": payload.aclx_tokens,
                        "prompt": payload.prompt,
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )
            return 0
        print(payload.prompt)
        return 0

    if args.command == "demo":
        samples = [
            "Plan the task and report the result.",
            "If the tool fails, explain the error.",
        ]
        for sample in samples:
            encoded = transcoder.nl_to_aclx(sample, mode=args.mode)
            gloss = transcoder.aclx_to_nl_gloss(encoded)
            print(f"NL   : {sample}")
            print(f"ACLX : {encoded}")
            print(f"Gloss: {gloss}")
            print()
        return 0

    if args.command == "benchmark":
        rows = run_benchmark(transcoder)
        print("name                  natural_t  aclx_t  json_t  natural_c  aclx_c  json_c  parse_ms")
        for row in rows:
            print(
                f"{row['name']:<21} {row['natural_tokens']:>9} {row['aclx_tokens']:>7} {row['json_tokens']:>7}"
                f" {row['natural_chars']:>10} {row['aclx_chars']:>7} {row['json_chars']:>7} {row['parse_ms']:>8}"
            )
        return 0

    if args.command == "tokenizer-benchmark":
        rows = run_tokenizer_benchmark(transcoder)
        print("name                  tokenizer   natural  aclx  tool_json  json_ir  gloss")
        for row in rows:
            print(
                f"{row['name']:<21} {row['tokenizer']:<10} {row['natural_tokens']:>8}"
                f" {row['aclx_tokens']:>5} {row['tool_json_tokens']:>10}"
                f" {row['json_ir_tokens']:>8} {row['gloss_tokens']:>6}"
            )
        return 0

    if args.command == "adapter-benchmark":
        rows = adapter.adapter_benchmark(iterations=args.iterations)
        print("sample  iterations    avg_ms  aclx_c  tool_json_c")
        for row in rows:
            print(
                f"{row['sample']:<6} {row['iterations']:>10} {row['avg_ms']:>9}"
                f" {row['aclx_chars']:>7} {row['tool_json_chars']:>12}"
            )
        return 0

    if args.command == "supervisor":
        forwarded = args.args[1:] if args.args and args.args[0] == "--" else args.args
        return supervisor_main(forwarded)

    if args.command == "ui":
        forwarded = ["--host", args.host, "--port", str(args.port), "--codex-home", args.codex_home]
        if args.open:
            forwarded.append("--open")
        return webui_main(forwarded)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
