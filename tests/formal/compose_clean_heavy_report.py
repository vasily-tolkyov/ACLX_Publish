from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from run_hybrid_pre_release_heavy import (
    RUNS_ROOT,
    aggregate_rows,
    copy_distribution_files,
    render_pdf,
    write_markdown_report,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_summaries(full_summary: dict, refreshed_t3_summary: dict, *, run_id: str, run_root: Path) -> dict:
    refreshed_t3_rows = {
        int(row["group"]): row
        for row in refreshed_t3_summary["tasks"]
        if str(row.get("tier", "")).lower() == "t3"
    }
    if len(refreshed_t3_rows) != 3:
        raise ValueError("Expected exactly three refreshed t3 tasks.")

    merged_tasks: list[dict] = []
    for row in full_summary["tasks"]:
        if str(row.get("tier", "")).lower() == "t3":
            group = int(row["group"])
            if group not in refreshed_t3_rows:
                raise ValueError(f"Missing refreshed t3 row for group {group}.")
            merged_tasks.append(refreshed_t3_rows[group])
        else:
            merged_tasks.append(row)

    merged_tiers: list[dict] = []
    for tier_name in ("t0", "t1", "t2", "t3"):
        tier_rows = [row for row in merged_tasks if row["tier"] == tier_name]
        merged_tiers.append(
            {
                "tier": tier_name,
                "task_count": len(tier_rows),
                "tasks": tier_rows,
                "aggregate": aggregate_rows(tier_rows),
            }
        )

    overall = aggregate_rows(merged_tasks)
    full_gate = full_summary.get("gate_tests", {})
    gate_exit = int(full_gate.get("exit_code", 1))
    lock_mismatches = list(full_summary.get("lock_mismatches", []))
    release_ready = (
        gate_exit == 0
        and not lock_mismatches
        and all(bool(row["route_matches_expected"]) for row in merged_tasks)
        and all(int(row["baseline"]["exit_code"]) == 0 and int(row["hybrid"]["exit_code"]) == 0 for row in merged_tasks)
        and float(overall["hybrid_avg_quality"]) >= float(overall["baseline_avg_quality"])
    )
    return {
        "kind": "hybrid_pre_release_heavy",
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_root": str(run_root),
        "timeout_seconds": full_summary.get("timeout_seconds", refreshed_t3_summary.get("timeout_seconds", 600)),
        "task_count": len(merged_tasks),
        "lock_mismatches": lock_mismatches,
        "gate_tests": {
            "exit_code": gate_exit,
            "stdout": str(full_gate.get("stdout", "")),
            "stderr": str(full_gate.get("stderr", "")),
        },
        "source_reports": {
            "full_summary": str(full_summary.get("run_root", "")),
            "refreshed_t3_summary": str(refreshed_t3_summary.get("run_root", "")),
        },
        "tasks": merged_tasks,
        "tiers": merged_tiers,
        "overall": overall,
        "release_ready": release_ready,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose a clean full heavy report by replacing t3 rows without replacement annotations.")
    parser.add_argument("--full-summary", required=True, help="Path to the original 12-task summary JSON.")
    parser.add_argument("--t3-summary", required=True, help="Path to the refreshed t3-only summary JSON.")
    parser.add_argument("--output-dir", help="Optional explicit output directory.")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip the default English PDF render.")
    args = parser.parse_args()

    full_summary_path = Path(args.full_summary).resolve()
    refreshed_t3_path = Path(args.t3_summary).resolve()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_root = Path(args.output_dir).resolve() if args.output_dir else RUNS_ROOT / f"hybrid_pre_release_heavy_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)

    merged_summary = merge_summaries(
        load_json(full_summary_path),
        load_json(refreshed_t3_path),
        run_id=run_id,
        run_root=run_root,
    )

    summary_path = run_root / f"hybrid_pre_release_heavy_{run_id}.json"
    markdown_path = run_root / f"hybrid_pre_release_heavy_{run_id}.md"
    pdf_path = run_root / f"hybrid_pre_release_heavy_{run_id}.pdf"
    summary_path.write_text(json.dumps(merged_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(merged_summary, markdown_path)
    generated_files = [summary_path, markdown_path]
    if not args.skip_pdf:
        render_pdf(merged_summary, pdf_path)
        generated_files.insert(0, pdf_path)
    copy_distribution_files(generated_files)
    print(summary_path)
    if not args.skip_pdf:
        print(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
