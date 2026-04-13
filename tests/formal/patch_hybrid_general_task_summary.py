from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any


def effective_tokens(result: dict[str, Any]) -> int:
    reported = result.get("reported_total_tokens")
    if isinstance(reported, int) and reported > 0:
        return reported
    return int(result.get("estimated_total_tokens") or 0)


def improvement_pct(baseline: float, hybrid: float) -> float | None:
    if baseline == 0:
        return None
    return round(((baseline - hybrid) / baseline) * 100.0, 2)


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "baseline_total_tokens": 0,
            "hybrid_total_tokens": 0,
            "token_optimization_pct": None,
            "baseline_total_seconds": 0.0,
            "hybrid_total_seconds": 0.0,
            "time_optimization_pct": None,
            "baseline_avg_quality": 0.0,
            "hybrid_avg_quality": 0.0,
            "quality_delta": 0.0,
        }
    baseline_tokens = sum(effective_tokens(row["baseline"]) for row in rows)
    hybrid_tokens = sum(effective_tokens(row["hybrid"]) for row in rows)
    baseline_seconds = sum(float(row["baseline"]["elapsed_seconds"]) for row in rows)
    hybrid_seconds = sum(float(row["hybrid"]["elapsed_seconds"]) for row in rows)
    baseline_quality = round(sum(int(row["baseline"]["quality_score"]) for row in rows) / len(rows), 2)
    hybrid_quality = round(sum(int(row["hybrid"]["quality_score"]) for row in rows) / len(rows), 2)
    return {
        "baseline_total_tokens": baseline_tokens,
        "hybrid_total_tokens": hybrid_tokens,
        "token_optimization_pct": improvement_pct(baseline_tokens, hybrid_tokens),
        "baseline_total_seconds": round(baseline_seconds, 3),
        "hybrid_total_seconds": round(hybrid_seconds, 3),
        "time_optimization_pct": improvement_pct(baseline_seconds, hybrid_seconds),
        "baseline_avg_quality": baseline_quality,
        "hybrid_avg_quality": hybrid_quality,
        "quality_delta": round(hybrid_quality - baseline_quality, 2),
    }


def aggregate_dimension(rows: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    values = sorted({str(row.get(key) or "") for row in rows if str(row.get(key) or "")})
    aggregates: list[dict[str, Any]] = []
    for value in values:
        matching = [row for row in rows if str(row.get(key) or "") == value]
        aggregates.append(
            {
                label: value,
                "task_count": len(matching),
                "tasks": matching,
                "aggregate": aggregate_rows(matching),
            }
        )
    return aggregates


def coverage_summary(rows: list[dict[str, Any]], *, expected_key: str, covered_key: str) -> dict[str, Any]:
    expected_rows = [row for row in rows if bool(row.get(expected_key))]
    if not expected_rows:
        return {"expected_tasks": 0, "covered_tasks": 0, "coverage_pct": None}
    covered_rows = [row for row in expected_rows if bool(row.get(covered_key))]
    return {
        "expected_tasks": len(expected_rows),
        "covered_tasks": len(covered_rows),
        "coverage_pct": round((len(covered_rows) / len(expected_rows)) * 100.0, 2),
    }


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("hybrid_general_task_heavy_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch a full generic-heavy summary with a rerun task result.")
    parser.add_argument("target_summary", help="Path to the original full-run summary JSON.")
    parser.add_argument("rerun_summary", help="Path to the rerun single-task summary JSON.")
    parser.add_argument("--report-script", default=str(Path(__file__).with_name("run_hybrid_general_task_heavy.py")))
    args = parser.parse_args()

    target_summary_path = Path(args.target_summary).resolve()
    rerun_summary_path = Path(args.rerun_summary).resolve()
    report_script_path = Path(args.report_script).resolve()

    target_summary = json.loads(target_summary_path.read_text(encoding="utf-8"))
    rerun_summary = json.loads(rerun_summary_path.read_text(encoding="utf-8"))
    replacement = rerun_summary["tasks"][0]

    for index, row in enumerate(target_summary["tasks"]):
        if row["task_name"] == replacement["task_name"]:
            target_summary["tasks"][index] = replacement
            break
    else:
        raise SystemExit(f"Task not found in target summary: {replacement['task_name']}")

    target_summary["tasks"] = sorted(
        target_summary["tasks"],
        key=lambda row: (str(row["tier"]), int(row["group"]), str(row["task_name"])),
    )
    target_summary["tiers"] = []
    for tier in ("t0", "t1", "t2", "t3"):
        tier_rows = [row for row in target_summary["tasks"] if row["tier"] == tier]
        target_summary["tiers"].append(
            {
                "tier": tier,
                "task_count": len(tier_rows),
                "tasks": tier_rows,
                "aggregate": aggregate_rows(tier_rows),
            }
        )

    target_summary["contract_families"] = aggregate_dimension(target_summary["tasks"], "contract_family", "contract_family")
    target_summary["adapter_families"] = aggregate_dimension(target_summary["tasks"], "adapter_family", "adapter_family")
    target_summary["validator_types"] = aggregate_dimension(target_summary["tasks"], "validator_type", "validator_type")
    target_summary["coverage"] = {
        "resumability": coverage_summary(
            target_summary["tasks"],
            expected_key="resumability_expected",
            covered_key="resumability_covered",
        ),
        "exactness_preservation": coverage_summary(
            target_summary["tasks"],
            expected_key="exactness_expected",
            covered_key="exactness_preserved",
        ),
    }
    target_summary["overall"] = aggregate_rows(target_summary["tasks"])
    target_summary["task_count"] = len(target_summary["tasks"])
    target_summary["release_ready"] = (
        int(target_summary["gate_tests"]["exit_code"]) == 0
        and not target_summary["lock_mismatches"]
        and all(bool(row["route_matches_expected"]) for row in target_summary["tasks"])
        and all(bool(row["adapter_matches_expected"]) for row in target_summary["tasks"])
        and all(
            int(row["baseline"]["exit_code"]) == 0 and int(row["hybrid"]["exit_code"]) == 0
            for row in target_summary["tasks"]
        )
        and float(target_summary["overall"]["hybrid_avg_quality"]) >= float(target_summary["overall"]["baseline_avg_quality"])
    )
    target_summary["patched_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    target_summary["rerun_overrides"] = [
        {
            "task_name": replacement["task_name"],
            "source_run_id": rerun_summary["run_id"],
            "source_run_root": rerun_summary["run_root"],
        }
    ]
    target_summary_path.write_text(json.dumps(target_summary, ensure_ascii=True, indent=2), encoding="utf-8")

    report_module = load_module(report_script_path)
    report_path = target_summary_path.with_name(f"{target_summary_path.stem}_formal_report.md")
    report_module.write_formal_report(target_summary, report_path)

    print(
        json.dumps(
            {
                "updated_summary": str(target_summary_path),
                "updated_report": str(report_path),
                "patched_task": replacement["task_name"],
                "source_run_id": rerun_summary["run_id"],
                "overall": target_summary["overall"],
                "release_ready": target_summary["release_ready"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
