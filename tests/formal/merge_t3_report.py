from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_ROOT = Path(__file__).resolve().parent
RUNS_ROOT = FORMAL_ROOT / "runs"
OUTPUT_PDF_ROOT = REPO_ROOT / "output" / "pdf"
TMP_PDF_ROOT = REPO_ROOT / "tmp" / "pdfs"

try:
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore
    from reportlab.lib.pagesizes import A4, landscape  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import mm  # type: ignore
    from reportlab.pdfbase import pdfmetrics  # type: ignore
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore
    from reportlab.pdfgen import canvas  # type: ignore
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


TIER_ZH = {
    "t0": "单表面",
    "t1": "单次交接",
    "t2": "平衡型",
    "t3": "循环重型",
}

GRADE_ZH = {
    "excellent": "优秀",
    "good": "良好",
    "partial": "部分达标",
    "poor": "较差",
}

TASK_ZH: dict[str, dict[str, str]] = {
    "t0_g1_release_summary": {"title": "发布说明摘要", "description": "纯单表面、只读的发布说明摘要任务，无交接、无 runtime bridge。"},
    "t0_g2_router_threshold_brief": {"title": "路由阈值简报", "description": "基于静态阈值文档的单表面路由简报任务。"},
    "t0_g3_operator_note_brief": {"title": "运维说明简报", "description": "聚焦 t0 边界的单表面运维说明提取任务。"},
    "t1_g1_empty_input_review": {"title": "空输入评审", "description": "对空输入会崩溃的列表清洗函数执行一次且仅一次评审交接。"},
    "t1_g2_zero_sample_review": {"title": "零样本评审", "description": "对零样本失败的延迟辅助函数执行一次且仅一次评审交接。"},
    "t1_g3_missing_route_review": {"title": "缺失路由评审", "description": "对未知 key 会崩溃的路由选择器执行一次且仅一次评审交接。"},
    "t2_g1_shared_pipeline_fix": {"title": "共享流水线修复", "description": "多步共享状态修复任务，修正保序去重流水线。"},
    "t2_g2_reviewer_queue_fix": {"title": "评审队列修复", "description": "多步共享状态修复任务，修正评审队列中的逆序归一化问题。"},
    "t2_g3_stage_plan_fix": {"title": "阶段计划修复", "description": "多步共享状态修复任务，恢复去重部署计划中丢失的首阶段。"},
    "t3_g1_verification_triad_skill": {"title": "验证三元组技能修复", "description": "重循环技能改写任务，需要保留 triad 角色并输出 checkpoint。"},
    "t3_g2_checkpoint_guard_skill": {"title": "Checkpoint 守卫技能修复", "description": "重循环技能改写任务，需要在最终外部结论之前保持 checkpoint 优先行为。"},
    "t3_g3_resume_bridge_skill": {"title": "恢复桥接技能修复", "description": "重循环技能改写任务，需要保留来自上一次 checkpoint 的恢复指引。"},
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_path(value: str) -> str:
    return str(value).replace("\\", "/")


def effective_tokens(row: dict[str, Any]) -> int:
    return int(row.get("reported_total_tokens") or row.get("estimated_total_tokens") or 0)


def improvement_pct(baseline: float | int, hybrid: float | int) -> float | None:
    baseline_value = float(baseline)
    if baseline_value <= 0:
        return None
    return round(((baseline_value - float(hybrid)) / baseline_value) * 100.0, 2)


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


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
    baseline_seconds = round(sum(float(row["baseline"]["elapsed_seconds"]) for row in rows), 3)
    hybrid_seconds = round(sum(float(row["hybrid"]["elapsed_seconds"]) for row in rows), 3)
    baseline_quality = round(sum(int(row["baseline"]["quality_score"]) for row in rows) / len(rows), 2)
    hybrid_quality = round(sum(int(row["hybrid"]["quality_score"]) for row in rows) / len(rows), 2)
    return {
        "baseline_total_tokens": baseline_tokens,
        "hybrid_total_tokens": hybrid_tokens,
        "token_optimization_pct": improvement_pct(baseline_tokens, hybrid_tokens),
        "baseline_total_seconds": baseline_seconds,
        "hybrid_total_seconds": hybrid_seconds,
        "time_optimization_pct": improvement_pct(baseline_seconds, hybrid_seconds),
        "baseline_avg_quality": baseline_quality,
        "hybrid_avg_quality": hybrid_quality,
        "quality_delta": round(hybrid_quality - baseline_quality, 2),
    }


def zh_title(task_name: str, fallback: str) -> str:
    return TASK_ZH.get(task_name, {}).get("title", fallback)


def zh_description(task_name: str, fallback: str) -> str:
    return TASK_ZH.get(task_name, {}).get("description", fallback)


def translate_note(note: str) -> str:
    if note.startswith("exactly ") and " non-empty lines" in note:
        match = re.search(r"exactly (\d+) non-empty lines", note)
        if match:
            return f"恰好输出 {match.group(1)} 行非空内容"
    if note == "tier line correct":
        return "Tier 行正确"
    if note.startswith("evidence names "):
        return f"Evidence 中包含 {note[len('evidence names '):]}"
    if note.startswith("required facts present: "):
        return f"必需事实命中 {note[len('required facts present: '):]}"
    if note == "review report written":
        return "已生成评审报告"
    if note == "required headings present":
        return "必需标题齐全"
    if note.startswith("report cites "):
        return f"报告引用了 {note[len('report cites '):]}"
    if note.startswith("bug explanation checks: "):
        return f"缺陷说明检查命中 {note[len('bug explanation checks: '):]}"
    if note == "unit tests passed":
        return "单元测试通过"
    if note == "unit tests failed":
        return "单元测试失败"
    if note == "shared state ACL-X artifact present":
        return "已生成共享状态 ACL-X 制品"
    if note == "shared state ACL-X artifact missing or invalid":
        return "共享状态 ACL-X 制品缺失或无效"
    if note == "review notes present":
        return "已生成 review notes"
    if note == "review notes missing or incomplete":
        return "review notes 缺失或不完整"
    if note.startswith("skill content checks: "):
        return f"技能内容检查命中 {note[len('skill content checks: '):]}"
    if note == "skill validator passed":
        return "技能校验器通过"
    if note == "skill validator failed":
        return "技能校验器失败"
    if note == "checkpoint ACL-X artifact present":
        return "已生成 checkpoint ACL-X 制品"
    if note == "checkpoint ACL-X artifact missing or invalid":
        return "checkpoint ACL-X 制品缺失或无效"
    return note


def paragraph_text(text: str) -> str:
    return escape(str(text)).replace("\n", "<br/>")


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(paragraph_text(text), style)


def make_style(base: ParagraphStyle, name: str, **overrides: Any) -> ParagraphStyle:
    style = ParagraphStyle(name=name, parent=base)
    for key, value in overrides.items():
        setattr(style, key, value)
    return style


def merge_summaries(
    full_summary: dict[str, Any],
    refreshed_t3_summary: dict[str, Any],
    *,
    run_id: str,
    run_root: Path,
    full_summary_path: Path,
    refreshed_t3_path: Path,
) -> dict[str, Any]:
    refreshed_t3_rows = {row["task_name"]: row for row in refreshed_t3_summary["tasks"]}
    full_t3_aggregate = next(tier["aggregate"] for tier in full_summary["tiers"] if tier["tier"] == "t3")
    refreshed_t3_aggregate = next(tier["aggregate"] for tier in refreshed_t3_summary["tiers"] if tier["tier"] == "t3")

    merged_tasks: list[dict[str, Any]] = []
    for row in full_summary["tasks"]:
        if row["tier"] == "t3":
            replacement = refreshed_t3_rows.get(row["task_name"])
            if replacement is None:
                raise ValueError(f"Missing refreshed t3 task for {row['task_name']}")
            merged_tasks.append(replacement)
        else:
            merged_tasks.append(row)

    merged_tiers: list[dict[str, Any]] = []
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
    refreshed_gate = refreshed_t3_summary.get("gate_tests", {})
    combined_gate_exit = 0 if int(full_gate.get("exit_code", 1)) == 0 and int(refreshed_gate.get("exit_code", 1)) == 0 else 1
    lock_mismatches = list(dict.fromkeys(list(full_summary.get("lock_mismatches", [])) + list(refreshed_t3_summary.get("lock_mismatches", []))))
    release_ready = (
        combined_gate_exit == 0
        and not lock_mismatches
        and all(row["route_matches_expected"] for row in merged_tasks)
        and all(int(row["baseline"]["exit_code"]) == 0 and int(row["hybrid"]["exit_code"]) == 0 for row in merged_tasks)
        and overall["hybrid_avg_quality"] >= overall["baseline_avg_quality"]
    )
    return {
        "kind": "hybrid_pre_release_heavy_merged_t3_refresh",
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_root": str(run_root),
        "timeout_seconds": full_summary.get("timeout_seconds", refreshed_t3_summary.get("timeout_seconds", 600)),
        "task_count": len(merged_tasks),
        "lock_mismatches": lock_mismatches,
        "gate_tests": {
            "exit_code": combined_gate_exit,
            "stdout": f"full summary:\n{full_gate.get('stdout', '')}\n\nrefreshed t3:\n{refreshed_gate.get('stdout', '')}".strip(),
            "stderr": f"full summary:\n{full_gate.get('stderr', '')}\n\nrefreshed t3:\n{refreshed_gate.get('stderr', '')}".strip(),
        },
        "source_reports": {
            "full_summary": str(full_summary_path),
            "refreshed_t3_summary": str(refreshed_t3_path),
        },
        "replacement_note": {
            "replaced_tier": "t3",
            "replaced_task_count": 3,
            "original_full_run_id": full_summary.get("run_id"),
            "refreshed_t3_run_id": refreshed_t3_summary.get("run_id"),
            "original_t3_aggregate": full_t3_aggregate,
            "refreshed_t3_aggregate": refreshed_t3_aggregate,
        },
        "tasks": merged_tasks,
        "tiers": merged_tiers,
        "overall": overall,
        "release_ready": release_ready,
    }


def write_markdown_report(summary: dict[str, Any], report_path: Path) -> None:
    note = summary["replacement_note"]
    old_t3 = note["original_t3_aggregate"]
    new_t3 = note["refreshed_t3_aggregate"]
    lines = [
        "# Hybrid Pre-Release Heavy Test Report - T3 Refreshed / 混合策略发布前重型测试报告 - T3 刷新版",
        "",
        f"- Run ID / 报告编号: `{summary['run_id']}`",
        f"- Generated at / 生成时间: `{summary['generated_at']}`",
        f"- Report root / 报告目录: `{normalize_path(summary['run_root'])}`",
        f"- Source full summary / 原完整报告: `{normalize_path(summary['source_reports']['full_summary'])}`",
        f"- Source refreshed t3 / 新 t3 复测报告: `{normalize_path(summary['source_reports']['refreshed_t3_summary'])}`",
        f"- Release recommendation / 发布建议: `{'GO' if summary['release_ready'] else 'HOLD'}`",
        "",
        "## Refresh Note / 更新说明",
        "",
        f"This merged report replaces only the `t3` section of full run `{note['original_full_run_id']}` with the latest local heavy `t3` rerun `{note['refreshed_t3_run_id']}`.",
        f"本报告仅替换完整运行 `{note['original_full_run_id']}` 中的 `t3` 章节，替换来源为最新本地重型 `t3` 复测 `{note['refreshed_t3_run_id']}`。",
        f"- Original t3 token optimization / 原 t3 token 优化: `{fmt_pct(old_t3['token_optimization_pct'])}`",
        f"- Refreshed t3 token optimization / 新 t3 token 优化: `{fmt_pct(new_t3['token_optimization_pct'])}`",
        f"- Original t3 time optimization / 原 t3 时间优化: `{fmt_pct(old_t3['time_optimization_pct'])}`",
        f"- Refreshed t3 time optimization / 新 t3 时间优化: `{fmt_pct(new_t3['time_optimization_pct'])}`",
        f"- Original t3 hybrid quality / 原 t3 hybrid 质量: `{old_t3['hybrid_avg_quality']:.2f}`",
        f"- Refreshed t3 hybrid quality / 新 t3 hybrid 质量: `{new_t3['hybrid_avg_quality']:.2f}`",
        "",
        "## Scope and Method / 范围与方法",
        "",
        "This document keeps the original t0-t2 results and replaces the previous t3 measurements with the latest refreshed local heavy t3 results.",
        "本报告保留原始 t0-t2 结果，仅将旧版 t3 测试数据替换为最新本地重型 t3 复测结果。",
        "Token consumption uses Codex-reported total tokens when available and falls back to estimated prompt plus visible output tokens only when the reported count is missing.",
        "Token 消耗优先使用 Codex 实报总 token；若缺失，则退回到 prompt 与可见输出 token 的估算值。",
        "Quality uses task-specific validators and is normalized to a 0-100 score.",
        "输出质量使用任务专属校验器，并统一归一到 0-100 分。",
        "",
        "## Task Selection / 任务选择",
        "",
        "| Tier / 档位 | Group / 组 | Title | 标题 | Task Description | 任务描述 |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in summary["tasks"]:
        lines.append(
            f"| {row['tier']} / {TIER_ZH.get(row['tier'], row['tier'])} | {row['group']} | {row['title']} | {zh_title(row['task_name'], row['title'])} | {row['description']} | {zh_description(row['task_name'], row['description'])} |"
        )
    lines.extend(
        [
            "",
            "## Per-Task Metrics / 单任务指标",
            "",
            "| Tier | Group | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Quality | Hybrid Quality | Quality Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary["tasks"]:
        lines.append(
            "| {tier} | {group} | {bt} | {ht} | {to} | {bsec:.2f} | {hsec:.2f} | {eo} | {bq} | {hq} | {qd} |".format(
                tier=row["tier"],
                group=row["group"],
                bt=effective_tokens(row["baseline"]),
                ht=effective_tokens(row["hybrid"]),
                to=fmt_pct(row["token_optimization_pct"]),
                bsec=float(row["baseline"]["elapsed_seconds"]),
                hsec=float(row["hybrid"]["elapsed_seconds"]),
                eo=fmt_pct(row["time_optimization_pct"]),
                bq=int(row["baseline"]["quality_score"]),
                hq=int(row["hybrid"]["quality_score"]),
                qd=int(row["quality_delta"]),
            )
        )
    lines.extend(
        [
            "",
            "## Tier Aggregates / 档位汇总",
            "",
            "| Tier | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for tier_row in summary["tiers"]:
        agg = tier_row["aggregate"]
        lines.append(
            "| {tier} | {count} | {bt} | {ht} | {to} | {bsec:.2f} | {hsec:.2f} | {eo} | {bq:.2f} | {hq:.2f} | {qd:.2f} |".format(
                tier=tier_row["tier"],
                count=tier_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                to=fmt_pct(agg["token_optimization_pct"]),
                bsec=float(agg["baseline_total_seconds"]),
                hsec=float(agg["hybrid_total_seconds"]),
                eo=fmt_pct(agg["time_optimization_pct"]),
                bq=float(agg["baseline_avg_quality"]),
                hq=float(agg["hybrid_avg_quality"]),
                qd=float(agg["quality_delta"]),
            )
        )
    overall = summary["overall"]
    lines.extend(
        [
            "",
            "## Overall Aggregate / 全量汇总",
            "",
            f"- Baseline total tokens / 基线总 token: `{overall['baseline_total_tokens']}`",
            f"- Hybrid total tokens / Hybrid 总 token: `{overall['hybrid_total_tokens']}`",
            f"- Token optimization pct / Token 优化比例: `{fmt_pct(overall['token_optimization_pct'])}`",
            f"- Baseline total seconds / 基线总耗时: `{overall['baseline_total_seconds']:.2f}`",
            f"- Hybrid total seconds / Hybrid 总耗时: `{overall['hybrid_total_seconds']:.2f}`",
            f"- Time optimization pct / 时间优化比例: `{fmt_pct(overall['time_optimization_pct'])}`",
            f"- Baseline average quality / 基线平均质量: `{overall['baseline_avg_quality']:.2f}`",
            f"- Hybrid average quality / Hybrid 平均质量: `{overall['hybrid_avg_quality']:.2f}`",
            f"- Quality delta / 质量差值: `{overall['quality_delta']:.2f}`",
            "",
            "## Detailed Findings / 详细结论",
            "",
        ]
    )
    for row in summary["tasks"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        lines.extend(
            [
                f"### {row['tier']} G{row['group']} - {row['title']} / {zh_title(row['task_name'], row['title'])}",
                "",
                f"- Task description / 任务描述: {row['description']} / {zh_description(row['task_name'], row['description'])}",
                f"- NL baseline tokens / NL baseline token 消耗: {effective_tokens(baseline)}",
                f"- Hybrid tokens / Hybrid token 消耗: {effective_tokens(hybrid)}",
                f"- Token optimization pct / Token 优化比例: {fmt_pct(row['token_optimization_pct'])}",
                f"- NL baseline runtime seconds / NL baseline 运行时间: {float(baseline['elapsed_seconds']):.2f}",
                f"- Hybrid runtime seconds / Hybrid 运行时间: {float(hybrid['elapsed_seconds']):.2f}",
                f"- Time optimization pct / 时间优化比例: {fmt_pct(row['time_optimization_pct'])}",
                f"- NL baseline quality / NL baseline 输出质量: {baseline['quality_score']} ({baseline['quality_grade']} / {GRADE_ZH.get(baseline['quality_grade'], baseline['quality_grade'])})",
                f"- Hybrid quality / Hybrid 输出质量: {hybrid['quality_score']} ({hybrid['quality_grade']} / {GRADE_ZH.get(hybrid['quality_grade'], hybrid['quality_grade'])})",
                f"- Quality delta / 质量差值: {row['quality_delta']}",
                f"- Baseline notes / 基线说明: {'; '.join(baseline['quality_notes'])}",
                f"- Baseline notes (ZH) / 基线说明中文: {'; '.join(translate_note(note) for note in baseline['quality_notes'])}",
                f"- Hybrid notes / Hybrid 说明: {'; '.join(hybrid['quality_notes'])}",
                f"- Hybrid notes (ZH) / Hybrid 说明中文: {'; '.join(translate_note(note) for note in hybrid['quality_notes'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Release Decision / 发布结论",
            "",
            (
                "Recommendation: GO. The merged report passes gates, keeps routing aligned, and preserves average hybrid quality at or above baseline."
                if summary["release_ready"]
                else "Recommendation: HOLD. The refreshed t3 section is release-ready, but the retained non-t3 portion of the original full run still contains failing or timed-out baseline rows."
            ),
            (
                "发布建议：GO。合并后的报告通过 gate，路由符合预期，且 hybrid 平均质量不低于 baseline。"
                if summary["release_ready"]
                else "发布建议：HOLD。刷新后的 t3 部分已达发布标准，但沿用的原始非 t3 完整测试仍包含失败或超时的 baseline 行。"
            ),
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def header_footer(title: str):
    def draw(canvas_obj: canvas.Canvas, doc) -> None:
        canvas_obj.saveState()
        canvas_obj.setFont("STSong-Light", 9)
        canvas_obj.drawString(doc.leftMargin, doc.height + doc.topMargin + 10, title)
        canvas_obj.drawRightString(doc.pagesize[0] - doc.rightMargin, 12, f"Page {doc.page}")
        canvas_obj.restoreState()

    return draw


def render_pdf(summary: dict[str, Any], pdf_path: Path) -> None:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is not installed")

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Hybrid Pre-Release Heavy Test Report - T3 Refreshed",
        author="OpenAI Codex",
    )
    styles = getSampleStyleSheet()
    title_style = make_style(styles["Title"], "BilingualTitle", fontName="STSong-Light", fontSize=19, leading=24, alignment=TA_CENTER, wordWrap="CJK")
    h1 = make_style(styles["Heading1"], "BilingualH1", fontName="STSong-Light", fontSize=14, leading=18, spaceAfter=8, wordWrap="CJK")
    h2 = make_style(styles["Heading2"], "BilingualH2", fontName="STSong-Light", fontSize=11, leading=14, spaceAfter=5, wordWrap="CJK")
    body = make_style(styles["BodyText"], "BilingualBody", fontName="STSong-Light", fontSize=8.8, leading=11.5, alignment=TA_LEFT, wordWrap="CJK")
    small = make_style(styles["BodyText"], "BilingualSmall", fontName="STSong-Light", fontSize=7.4, leading=9, alignment=TA_LEFT, wordWrap="CJK")

    note = summary["replacement_note"]
    old_t3 = note["original_t3_aggregate"]
    new_t3 = note["refreshed_t3_aggregate"]
    story: list[Any] = []

    story.append(Paragraph("Hybrid Pre-Release Heavy Test Report - T3 Refreshed / 混合策略发布前重型测试报告 - T3 刷新版", title_style))
    story.append(Spacer(1, 5 * mm))
    for line in [
        f"Run ID / 报告编号: {summary['run_id']}",
        f"Generated at / 生成时间: {summary['generated_at']}",
        f"Report root / 报告目录: {normalize_path(summary['run_root'])}",
        f"Source full summary / 原完整报告: {normalize_path(summary['source_reports']['full_summary'])}",
        f"Source refreshed t3 / 新 t3 复测报告: {normalize_path(summary['source_reports']['refreshed_t3_summary'])}",
        f"Release recommendation / 发布建议: {'GO' if summary['release_ready'] else 'HOLD'}",
    ]:
        story.append(paragraph(line, body))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Refresh Note / 更新说明", h1))
    for line in [
        f"This merged report replaces only the t3 section of full run {note['original_full_run_id']} with the latest local heavy t3 rerun {note['refreshed_t3_run_id']}.",
        f"本报告仅替换完整运行 {note['original_full_run_id']} 中的 t3 章节，替换来源为最新本地重型 t3 复测 {note['refreshed_t3_run_id']}。",
        f"Original t3 aggregate / 原 t3 汇总: token {fmt_pct(old_t3['token_optimization_pct'])}, time {fmt_pct(old_t3['time_optimization_pct'])}, hybrid quality {old_t3['hybrid_avg_quality']:.2f}.",
        f"Refreshed t3 aggregate / 新 t3 汇总: token {fmt_pct(new_t3['token_optimization_pct'])}, time {fmt_pct(new_t3['time_optimization_pct'])}, hybrid quality {new_t3['hybrid_avg_quality']:.2f}.",
    ]:
        story.append(paragraph(line, body))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Scope and Method / 范围与方法", h1))
    for line in [
        "This document keeps the original t0-t2 results and replaces the previous t3 measurements with the latest refreshed local heavy t3 results.",
        "本报告保留原始 t0-t2 结果，仅将旧版 t3 测试数据替换为最新本地重型 t3 复测结果。",
        "Token consumption uses Codex-reported total tokens when available and falls back to estimated prompt plus visible output tokens only when the reported count is missing.",
        "Token 消耗优先使用 Codex 实报总 token；若缺失，则退回到 prompt 与可见输出 token 的估算值。",
        "Quality uses task-specific validators and is normalized to a 0-100 score.",
        "输出质量使用任务专属校验器，并统一归一到 0-100 分。",
    ]:
        story.append(paragraph(line, body))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Task Selection / 任务选择", h1))
    task_rows: list[list[Any]] = [[paragraph("Tier / 档位", small), paragraph("Group / 组", small), paragraph("Title / 标题", small), paragraph("Task Description / 任务描述", small)]]
    for row in summary["tasks"]:
        task_rows.append(
            [
                paragraph(f"{row['tier']} / {TIER_ZH.get(row['tier'], row['tier'])}", small),
                paragraph(str(row["group"]), small),
                paragraph(f"{row['title']}\n{zh_title(row['task_name'], row['title'])}", small),
                paragraph(f"{row['description']}\n{zh_description(row['task_name'], row['description'])}", small),
            ]
        )
    task_table = Table(task_rows, colWidths=[26 * mm, 16 * mm, 54 * mm, 165 * mm], repeatRows=1)
    task_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(task_table)
    story.append(PageBreak())

    story.append(Paragraph("Per-Task Metrics / 单任务指标", h1))
    metric_rows: list[list[Any]] = [[paragraph("Tier\n档位", small), paragraph("Group\n组", small), paragraph("Baseline Tokens\n基线 Token", small), paragraph("Hybrid Tokens\nHybrid Token", small), paragraph("Token Opt %\nToken 优化", small), paragraph("Baseline Time (s)\n基线时间", small), paragraph("Hybrid Time (s)\nHybrid 时间", small), paragraph("Time Opt %\n时间优化", small), paragraph("Baseline Quality\n基线质量", small), paragraph("Hybrid Quality\nHybrid 质量", small)]]
    for row in summary["tasks"]:
        metric_rows.append(
            [
                paragraph(row["tier"], small),
                paragraph(str(row["group"]), small),
                paragraph(str(effective_tokens(row["baseline"])), small),
                paragraph(str(effective_tokens(row["hybrid"])), small),
                paragraph(fmt_pct(row["token_optimization_pct"]), small),
                paragraph(f"{float(row['baseline']['elapsed_seconds']):.2f}", small),
                paragraph(f"{float(row['hybrid']['elapsed_seconds']):.2f}", small),
                paragraph(fmt_pct(row["time_optimization_pct"]), small),
                paragraph(str(row["baseline"]["quality_score"]), small),
                paragraph(str(row["hybrid"]["quality_score"]), small),
            ]
        )
    metric_table = Table(metric_rows, colWidths=[16 * mm, 14 * mm, 26 * mm, 26 * mm, 22 * mm, 24 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm], repeatRows=1)
    metric_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(metric_table)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Tier Aggregates / 档位汇总", h1))
    aggregate_rows_pdf: list[list[Any]] = [[paragraph("Tier\n档位", small), paragraph("Task Count\n任务数", small), paragraph("Baseline Tokens\n基线 Token", small), paragraph("Hybrid Tokens\nHybrid Token", small), paragraph("Token Opt %\nToken 优化", small), paragraph("Baseline Time (s)\n基线时间", small), paragraph("Hybrid Time (s)\nHybrid 时间", small), paragraph("Time Opt %\n时间优化", small), paragraph("Baseline Avg Quality\n基线均分", small), paragraph("Hybrid Avg Quality\nHybrid 均分", small)]]
    for tier_row in summary["tiers"]:
        agg = tier_row["aggregate"]
        aggregate_rows_pdf.append(
            [
                paragraph(f"{tier_row['tier']} / {TIER_ZH.get(tier_row['tier'], tier_row['tier'])}", small),
                paragraph(str(tier_row["task_count"]), small),
                paragraph(str(agg["baseline_total_tokens"]), small),
                paragraph(str(agg["hybrid_total_tokens"]), small),
                paragraph(fmt_pct(agg["token_optimization_pct"]), small),
                paragraph(f"{float(agg['baseline_total_seconds']):.2f}", small),
                paragraph(f"{float(agg['hybrid_total_seconds']):.2f}", small),
                paragraph(fmt_pct(agg["time_optimization_pct"]), small),
                paragraph(f"{float(agg['baseline_avg_quality']):.2f}", small),
                paragraph(f"{float(agg['hybrid_avg_quality']):.2f}", small),
            ]
        )
    aggregate_table = Table(aggregate_rows_pdf, colWidths=[20 * mm, 19 * mm, 26 * mm, 26 * mm, 22 * mm, 24 * mm, 24 * mm, 22 * mm, 24 * mm, 24 * mm], repeatRows=1)
    aggregate_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c2d12")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(aggregate_table)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("T3 Replacement Summary / T3 替换摘要", h1))
    replacement_table = Table(
        [
            [paragraph("Version / 版本", small), paragraph("Token Opt % / Token 优化", small), paragraph("Time Opt % / 时间优化", small), paragraph("Hybrid Avg Quality / Hybrid 平均质量", small)],
            [paragraph("Original full report t3 / 原完整报告 t3", small), paragraph(fmt_pct(old_t3["token_optimization_pct"]), small), paragraph(fmt_pct(old_t3["time_optimization_pct"]), small), paragraph(f"{old_t3['hybrid_avg_quality']:.2f}", small)],
            [paragraph("Refreshed latest t3 / 最新刷新 t3", small), paragraph(fmt_pct(new_t3["token_optimization_pct"]), small), paragraph(fmt_pct(new_t3["time_optimization_pct"]), small), paragraph(f"{new_t3['hybrid_avg_quality']:.2f}", small)],
        ],
        colWidths=[70 * mm, 40 * mm, 40 * mm, 50 * mm],
        repeatRows=1,
    )
    replacement_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eff6ff")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(replacement_table)
    story.append(PageBreak())

    story.append(Paragraph("Detailed Findings / 详细结论", h1))
    for row in summary["tasks"]:
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        story.append(Paragraph(f"{row['tier']} G{row['group']} - {row['title']} / {zh_title(row['task_name'], row['title'])}", h2))
        for line in [
            f"Task description / 任务描述: {row['description']} / {zh_description(row['task_name'], row['description'])}",
            f"NL baseline tokens / NL baseline token 消耗: {effective_tokens(baseline)}",
            f"Hybrid tokens / Hybrid token 消耗: {effective_tokens(hybrid)}",
            f"Token optimization pct / Token 优化比例: {fmt_pct(row['token_optimization_pct'])}",
            f"NL baseline runtime seconds / NL baseline 运行时间: {float(baseline['elapsed_seconds']):.2f}",
            f"Hybrid runtime seconds / Hybrid 运行时间: {float(hybrid['elapsed_seconds']):.2f}",
            f"Time optimization pct / 时间优化比例: {fmt_pct(row['time_optimization_pct'])}",
            f"NL baseline quality / NL baseline 输出质量: {baseline['quality_score']} ({baseline['quality_grade']} / {GRADE_ZH.get(baseline['quality_grade'], baseline['quality_grade'])})",
            f"Hybrid quality / Hybrid 输出质量: {hybrid['quality_score']} ({hybrid['quality_grade']} / {GRADE_ZH.get(hybrid['quality_grade'], hybrid['quality_grade'])})",
            f"Quality delta / 质量差值: {row['quality_delta']}",
            f"Baseline notes / 基线说明: {'; '.join(baseline['quality_notes'])}",
            f"Baseline notes (ZH) / 基线说明中文: {'; '.join(translate_note(note_text) for note_text in baseline['quality_notes'])}",
            f"Hybrid notes / Hybrid 说明: {'; '.join(hybrid['quality_notes'])}",
            f"Hybrid notes (ZH) / Hybrid 说明中文: {'; '.join(translate_note(note_text) for note_text in hybrid['quality_notes'])}",
        ]:
            story.append(paragraph(line, body))
        story.append(Spacer(1, 2.5 * mm))

    overall = summary["overall"]
    story.append(Paragraph("Release Decision / 发布结论", h1))
    for line in [
        f"Baseline total tokens / 基线总 token: {overall['baseline_total_tokens']}",
        f"Hybrid total tokens / Hybrid 总 token: {overall['hybrid_total_tokens']}",
        f"Token optimization pct / Token 优化比例: {fmt_pct(overall['token_optimization_pct'])}",
        f"Baseline total seconds / 基线总耗时: {overall['baseline_total_seconds']:.2f}",
        f"Hybrid total seconds / Hybrid 总耗时: {overall['hybrid_total_seconds']:.2f}",
        f"Time optimization pct / 时间优化比例: {fmt_pct(overall['time_optimization_pct'])}",
        f"Baseline average quality / 基线平均质量: {overall['baseline_avg_quality']:.2f}",
        f"Hybrid average quality / Hybrid 平均质量: {overall['hybrid_avg_quality']:.2f}",
        f"Quality delta / 质量差值: {overall['quality_delta']:.2f}",
        (
            "Recommendation: GO. The merged report passes gates, keeps routing aligned, and preserves average hybrid quality at or above baseline."
            if summary["release_ready"]
            else "Recommendation: HOLD. The refreshed t3 section is release-ready, but the retained non-t3 portion of the original full run still contains failing or timed-out baseline rows."
        ),
        (
            "发布建议：GO。合并后的报告通过 gate，路由符合预期，且 hybrid 平均质量不低于 baseline。"
            if summary["release_ready"]
            else "发布建议：HOLD。刷新后的 t3 部分已达发布标准，但沿用的原始非 t3 完整测试仍包含失败或超时的 baseline 行。"
        ),
    ]:
        story.append(paragraph(line, body))

    doc.build(
        story,
        onFirstPage=header_footer("Hybrid Pre-Release Heavy Test Report - T3 Refreshed / 混合策略发布前重型测试报告 - T3 刷新版"),
        onLaterPages=header_footer("Hybrid Pre-Release Heavy Test Report - T3 Refreshed / 混合策略发布前重型测试报告 - T3 刷新版"),
    )


def maybe_render_preview(pdf_path: Path) -> list[Path]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return []
    TMP_PDF_ROOT.mkdir(parents=True, exist_ok=True)
    prefix = TMP_PDF_ROOT / pdf_path.stem
    subprocess.run([pdftoppm, "-f", "1", "-l", "3", "-png", str(pdf_path), str(prefix)], capture_output=True, text=True, encoding="utf-8", check=False)
    return sorted(TMP_PDF_ROOT.glob(f"{pdf_path.stem}-*.png"))


def copy_distribution_files(paths: list[Path]) -> None:
    OUTPUT_PDF_ROOT.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, OUTPUT_PDF_ROOT / path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge the latest t3 heavy rerun into the previous full heavy report and render a bilingual PDF.")
    parser.add_argument("--full-summary", required=True, help="Path to the previous full 12-task summary JSON.")
    parser.add_argument("--t3-summary", required=True, help="Path to the latest refreshed t3 summary JSON.")
    parser.add_argument("--output-dir", help="Optional explicit output directory.")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF generation.")
    args = parser.parse_args()

    full_summary_path = Path(args.full_summary).resolve()
    refreshed_t3_path = Path(args.t3_summary).resolve()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_root = Path(args.output_dir).resolve() if args.output_dir else RUNS_ROOT / f"hybrid_pre_release_heavy_merged_t3_refresh_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)

    full_summary = load_json(full_summary_path)
    refreshed_t3_summary = load_json(refreshed_t3_path)
    merged_summary = merge_summaries(
        full_summary,
        refreshed_t3_summary,
        run_id=run_id,
        run_root=run_root,
        full_summary_path=full_summary_path,
        refreshed_t3_path=refreshed_t3_path,
    )

    json_path = run_root / f"hybrid_pre_release_heavy_merged_t3_refresh_{run_id}.json"
    markdown_path = run_root / f"hybrid_pre_release_heavy_merged_t3_refresh_{run_id}.md"
    pdf_path = run_root / f"hybrid_pre_release_heavy_merged_t3_refresh_{run_id}.pdf"
    json_path.write_text(json.dumps(merged_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(merged_summary, markdown_path)
    generated_paths = [json_path, markdown_path]
    preview_paths: list[Path] = []
    if not args.skip_pdf:
        render_pdf(merged_summary, pdf_path)
        preview_paths = maybe_render_preview(pdf_path)
        generated_paths.insert(0, pdf_path)
    copy_distribution_files(generated_paths)

    print(str(run_root))
    if preview_paths:
        print(json.dumps({"preview_images": [str(path) for path in preview_paths]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
