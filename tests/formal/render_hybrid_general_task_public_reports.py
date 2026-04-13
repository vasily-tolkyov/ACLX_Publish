from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import fitz  # type: ignore
from reportlab.lib import colors  # type: ignore
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore
from reportlab.lib.pagesizes import A4, landscape  # type: ignore
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
from reportlab.lib.units import mm  # type: ignore
from reportlab.pdfbase import pdfmetrics  # type: ignore
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PDF_ROOT = REPO_ROOT / "output" / "pdf"
TMP_PDF_ROOT = REPO_ROOT / "tmp" / "pdfs"
DEFAULT_LOCK_PATH = REPO_ROOT / "configs" / "strategy_lock.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def effective_tokens(row: dict[str, Any]) -> int:
    reported = row.get("reported_total_tokens")
    if isinstance(reported, int) and reported > 0:
        return reported
    return int(row.get("estimated_total_tokens") or 0)


def fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}%"


def fmt_secs(value: Any) -> str:
    return f"{float(value):.2f}s"


def short_grade(score: Any) -> str:
    numeric = int(score)
    if numeric >= 90:
        return "excellent"
    if numeric >= 75:
        return "good"
    if numeric >= 60:
        return "partial"
    return "poor"


def load_lock_name(lock_path: Path) -> str:
    if not lock_path.exists():
        return "unknown"
    return str(load_json(lock_path).get("lock_name") or "unknown")


def compute_public_verdict(summary: dict[str, Any]) -> dict[str, Any]:
    overall = summary["overall"]
    tasks = list(summary["tasks"])
    all_hybrid_runs_ok = all(int(row["hybrid"]["exit_code"]) == 0 for row in tasks)
    baseline_failures = sum(1 for row in tasks if int(row["baseline"]["exit_code"]) != 0)
    all_routes_ok = all(bool(row["route_matches_expected"]) for row in tasks)
    all_adapters_ok = all(bool(row["adapter_matches_expected"]) for row in tasks)
    quality_ok = float(overall["quality_delta"]) >= 0.0
    token_ok = overall["token_optimization_pct"] is not None and float(overall["token_optimization_pct"]) > 0.0
    time_ok = overall["time_optimization_pct"] is not None and float(overall["time_optimization_pct"]) > 0.0
    status = "GO" if (
        int(summary["gate_tests"]["exit_code"]) == 0
        and not summary["lock_mismatches"]
        and all_hybrid_runs_ok
        and all_routes_ok
        and all_adapters_ok
        and quality_ok
        and token_ok
        and time_ok
    ) else "HOLD"
    return {
        "status": status,
        "all_hybrid_runs_ok": all_hybrid_runs_ok,
        "baseline_failures": baseline_failures,
        "all_routes_ok": all_routes_ok,
        "all_adapters_ok": all_adapters_ok,
        "quality_ok": quality_ok,
        "token_ok": token_ok,
        "time_ok": time_ok,
    }


def task_matrix_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in summary["tasks"]:
        rows.append(
            {
                "tier": row["tier"],
                "group": row["group"],
                "title": row["title"],
                "baseline_tokens": effective_tokens(row["baseline"]),
                "hybrid_tokens": effective_tokens(row["hybrid"]),
                "token_pct": row["token_optimization_pct"],
                "baseline_time": row["baseline"]["elapsed_seconds"],
                "hybrid_time": row["hybrid"]["elapsed_seconds"],
                "time_pct": row["time_optimization_pct"],
                "baseline_quality": row["baseline"]["quality_score"],
                "hybrid_quality": row["hybrid"]["quality_score"],
                "quality_delta": row["quality_delta"],
            }
        )
    return rows


def english_markdown(summary: dict[str, Any], *, lock_name: str, verdict: dict[str, Any]) -> str:
    overall = summary["overall"]
    tiers = summary["tiers"]
    task_rows = task_matrix_rows(summary)
    positive_token = sum(1 for row in task_rows if row["token_pct"] is not None and float(row["token_pct"]) > 0.0)
    positive_time = sum(1 for row in task_rows if row["time_pct"] is not None and float(row["time_pct"]) > 0.0)
    lines = [
        "# Hybrid General Task Heavy A/B Public Report",
        "",
        "## Executive Summary",
        "",
        "This report evaluates the locked hybrid strategy on a fresh 4-tier x 3-task general-purpose benchmark.",
        "The benchmark is intentionally not ACL-X-centric: it covers policy extraction, bug review, repair with reusable artifacts, and loop-heavy document rewrite.",
        f"Public release recommendation: **{verdict['status']}**.",
        "",
        "## Benchmark Basis",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- Strategy lock: `{lock_name}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Matrix size: `{summary['task_count']}` tasks across `t0/t1/t2/t3`",
        f"- Gate tests passed: `{int(summary['gate_tests']['exit_code']) == 0}`",
        f"- Strategy lock clean: `{not summary['lock_mismatches']}`",
        f"- Baseline failed tasks: `{verdict['baseline_failures']}`",
        "",
        "## Aggregate Outcome",
        "",
        f"- Baseline total tokens: `{overall['baseline_total_tokens']}`",
        f"- Hybrid total tokens: `{overall['hybrid_total_tokens']}`",
        f"- Aggregate token improvement: `{fmt_pct(overall['token_optimization_pct'])}`",
        f"- Baseline total time: `{fmt_secs(overall['baseline_total_seconds'])}`",
        f"- Hybrid total time: `{fmt_secs(overall['hybrid_total_seconds'])}`",
        f"- Aggregate time improvement: `{fmt_pct(overall['time_optimization_pct'])}`",
        f"- Baseline average quality: `{overall['baseline_avg_quality']:.2f}`",
        f"- Hybrid average quality: `{overall['hybrid_avg_quality']:.2f}`",
        f"- Quality delta: `{overall['quality_delta']:.2f}`",
        "",
        "## Release Interpretation",
        "",
        f"- Tasks with positive token improvement: `{positive_token}/{summary['task_count']}`",
        f"- Tasks with positive time improvement: `{positive_time}/{summary['task_count']}`",
        f"- Resumability coverage: `{summary['coverage']['resumability']['covered_tasks']}/{summary['coverage']['resumability']['expected_tasks']}`",
        f"- Exactness preservation coverage: `{summary['coverage']['exactness_preservation']['covered_tasks']}/{summary['coverage']['exactness_preservation']['expected_tasks']}`",
        "- The validated claim is bounded: hybrid is faster and cheaper on aggregate for structured general tasks in this matrix, without average quality regression.",
        "- This is not a guarantee for arbitrary open-ended work. It is evidence for structured tasks with explicit artifacts, validators, and closure conditions.",
        "",
        "## Tier Aggregates",
        "",
        "| Tier | Tasks | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Avg Quality | Hybrid Avg Quality |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tier_row in tiers:
        agg = tier_row["aggregate"]
        lines.append(
            "| {tier} | {count} | {bt} | {ht} | {tok} | {bs} | {hs} | {tim} | {bq:.2f} | {hq:.2f} |".format(
                tier=tier_row["tier"],
                count=tier_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                tok=fmt_pct(agg["token_optimization_pct"]),
                bs=fmt_secs(agg["baseline_total_seconds"]),
                hs=fmt_secs(agg["hybrid_total_seconds"]),
                tim=fmt_pct(agg["time_optimization_pct"]),
                bq=agg["baseline_avg_quality"],
                hq=agg["hybrid_avg_quality"],
            )
        )
    lines.extend(
        [
            "",
            "## Task Matrix",
            "",
            "| Tier | Group | Task | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Quality | Hybrid Quality |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in task_rows:
        lines.append(
            "| {tier} | {group} | {title} | {bt} | {ht} | {tok} | {bs} | {hs} | {tim} | {bq} | {hq} |".format(
                tier=row["tier"],
                group=row["group"],
                title=row["title"],
                bt=row["baseline_tokens"],
                ht=row["hybrid_tokens"],
                tok=fmt_pct(row["token_pct"]),
                bs=fmt_secs(row["baseline_time"]),
                hs=fmt_secs(row["hybrid_time"]),
                tim=fmt_pct(row["time_pct"]),
                bq=row["baseline_quality"],
                hq=row["hybrid_quality"],
            )
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            (
                "Hybrid is ready for public release within the validated structured-task range covered by this benchmark. The current locked strategy improved aggregate token and time cost while preserving average output quality."
                if verdict["status"] == "GO"
                else "Hybrid should remain on HOLD for public release under this benchmark because at least one aggregate gate failed."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def chinese_markdown(summary: dict[str, Any], *, lock_name: str, verdict: dict[str, Any]) -> str:
    overall = summary["overall"]
    tiers = summary["tiers"]
    task_rows = task_matrix_rows(summary)
    positive_token = sum(1 for row in task_rows if row["token_pct"] is not None and float(row["token_pct"]) > 0.0)
    positive_time = sum(1 for row in task_rows if row["time_pct"] is not None and float(row["time_pct"]) > 0.0)
    lines = [
        "# Hybrid 通用任务重型 A/B 测试正式报告",
        "",
        "## 执行摘要",
        "",
        "本报告基于一轮新的 4 层级 x 3 任务通用重型矩阵，对当前锁定版 hybrid 策略进行公开发布前评估。",
        "测试任务刻意避免 ACL-X 强相关语义，覆盖政策提取、缺陷审查、带复用工件的修复任务，以及带循环/恢复特征的文档改写。",
        f"公开发布结论：**{verdict['status']}**。",
        "",
        "## 测试基线",
        "",
        f"- Run ID：`{summary['run_id']}`",
        f"- 策略锁名称：`{lock_name}`",
        f"- 生成时间：`{summary['generated_at']}`",
        f"- 矩阵规模：`{summary['task_count']}` 个任务，覆盖 `t0/t1/t2/t3`",
        f"- Gate 测试通过：`{int(summary['gate_tests']['exit_code']) == 0}`",
        f"- 策略锁一致：`{not summary['lock_mismatches']}`",
        f"- Baseline 失败任务数：`{verdict['baseline_failures']}`",
        "",
        "## 总体结果",
        "",
        f"- 基线总 token：`{overall['baseline_total_tokens']}`",
        f"- Hybrid 总 token：`{overall['hybrid_total_tokens']}`",
        f"- 聚合 token 优化：`{fmt_pct(overall['token_optimization_pct'])}`",
        f"- 基线总耗时：`{fmt_secs(overall['baseline_total_seconds'])}`",
        f"- Hybrid 总耗时：`{fmt_secs(overall['hybrid_total_seconds'])}`",
        f"- 聚合时间优化：`{fmt_pct(overall['time_optimization_pct'])}`",
        f"- 基线平均质量：`{overall['baseline_avg_quality']:.2f}`",
        f"- Hybrid 平均质量：`{overall['hybrid_avg_quality']:.2f}`",
        f"- 质量差值：`{overall['quality_delta']:.2f}`",
        "",
        "## 发布解读",
        "",
        f"- token 正向优化任务数：`{positive_token}/{summary['task_count']}`",
        f"- 时间正向优化任务数：`{positive_time}/{summary['task_count']}`",
        f"- 可恢复性覆盖：`{summary['coverage']['resumability']['covered_tasks']}/{summary['coverage']['resumability']['expected_tasks']}`",
        f"- 精确性保持覆盖：`{summary['coverage']['exactness_preservation']['covered_tasks']}/{summary['coverage']['exactness_preservation']['expected_tasks']}`",
        "- 本报告支持的是有边界的结论：对于这类结构化通用任务，hybrid 在聚合 token 和聚合时间上优于原生 NL，且平均输出质量不退化。",
        "- 这不是对任意开放式任务的普遍保证，而是对“任务可结构化、可验证、可闭环”的通用任务范围给出的正式证据。",
        "",
        "## 分层汇总",
        "",
        "| 层级 | 任务数 | 基线 Tokens | Hybrid Tokens | Token 优化 | 基线耗时 | Hybrid 耗时 | 时间优化 | 基线平均质量 | Hybrid 平均质量 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tier_row in tiers:
        agg = tier_row["aggregate"]
        lines.append(
            "| {tier} | {count} | {bt} | {ht} | {tok} | {bs} | {hs} | {tim} | {bq:.2f} | {hq:.2f} |".format(
                tier=tier_row["tier"],
                count=tier_row["task_count"],
                bt=agg["baseline_total_tokens"],
                ht=agg["hybrid_total_tokens"],
                tok=fmt_pct(agg["token_optimization_pct"]),
                bs=fmt_secs(agg["baseline_total_seconds"]),
                hs=fmt_secs(agg["hybrid_total_seconds"]),
                tim=fmt_pct(agg["time_optimization_pct"]),
                bq=agg["baseline_avg_quality"],
                hq=agg["hybrid_avg_quality"],
            )
        )
    lines.extend(
        [
            "",
            "## 任务矩阵",
            "",
            "| 层级 | 组别 | 任务 | 基线 Tokens | Hybrid Tokens | Token 优化 | 基线耗时 | Hybrid 耗时 | 时间优化 | 基线质量 | Hybrid 质量 |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in task_rows:
        lines.append(
            "| {tier} | {group} | {title} | {bt} | {ht} | {tok} | {bs} | {hs} | {tim} | {bq} | {hq} |".format(
                tier=row["tier"],
                group=row["group"],
                title=row["title"],
                bt=row["baseline_tokens"],
                ht=row["hybrid_tokens"],
                tok=fmt_pct(row["token_pct"]),
                bs=fmt_secs(row["baseline_time"]),
                hs=fmt_secs(row["hybrid_time"]),
                tim=fmt_pct(row["time_pct"]),
                bq=row["baseline_quality"],
                hq=row["hybrid_quality"],
            )
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            (
                "在本次正式矩阵覆盖的结构化通用任务范围内，当前锁定版 hybrid 已达到公开发布条件：聚合 token 更低、聚合时间更短、平均输出质量不下降。"
                if verdict["status"] == "GO"
                else "在本次正式矩阵下，当前 hybrid 暂不满足公开发布条件，因为至少有一项聚合门槛未通过。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def ensure_fonts() -> dict[str, str]:
    fonts = {
        "en_regular": "Helvetica",
        "en_bold": "Helvetica-Bold",
        "zh_regular": "Helvetica",
        "zh_bold": "Helvetica-Bold",
    }
    regular_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    bold_path = Path(r"C:\Windows\Fonts\msyhbd.ttc")
    if regular_path.exists():
        pdfmetrics.registerFont(TTFont("MSYH", str(regular_path), subfontIndex=0))
        fonts["zh_regular"] = "MSYH"
    if bold_path.exists():
        pdfmetrics.registerFont(TTFont("MSYH-Bold", str(bold_path), subfontIndex=0))
        fonts["zh_bold"] = "MSYH-Bold"
    elif fonts["zh_regular"] == "MSYH":
        fonts["zh_bold"] = "MSYH"
    return fonts


def make_style(base: ParagraphStyle, name: str, **overrides: Any) -> ParagraphStyle:
    style = ParagraphStyle(name=name, parent=base)
    for key, value in overrides.items():
        setattr(style, key, value)
    return style


def pdf_story(
    *,
    summary: dict[str, Any],
    lock_name: str,
    verdict: dict[str, Any],
    language: str,
    fonts: dict[str, str],
) -> tuple[str, list[Any]]:
    styles = getSampleStyleSheet()
    if language == "zh":
        regular_font = fonts["zh_regular"]
        bold_font = fonts["zh_bold"]
        title_text = "Hybrid 通用任务重型 A/B 测试正式报告"
        section_exec = "执行摘要"
        section_basis = "测试基线"
        section_result = "总体结果"
        section_tier = "分层汇总"
        section_matrix = "任务矩阵"
        section_notes = "解读与边界"
        section_conclusion = "结论"
        intro_lines = [
            "本报告面向公开发布，使用新的 4x3 通用任务重型矩阵评估当前锁定版 hybrid 策略。",
            "测试对象覆盖结构化通用任务，而不是 ACL-X 专项任务。",
            f"发布结论：{verdict['status']}。",
        ]
        basis_lines = [
            f"Run ID：{summary['run_id']}",
            f"策略锁名称：{lock_name}",
            f"生成时间：{summary['generated_at']}",
            f"矩阵规模：{summary['task_count']} 个任务，覆盖 t0/t1/t2/t3。",
            f"Baseline 失败任务数：{verdict['baseline_failures']}。",
        ]
        overall_lines = [
            f"基线总 token：{summary['overall']['baseline_total_tokens']}",
            f"Hybrid 总 token：{summary['overall']['hybrid_total_tokens']}",
            f"聚合 token 优化：{fmt_pct(summary['overall']['token_optimization_pct'])}",
            f"基线总耗时：{fmt_secs(summary['overall']['baseline_total_seconds'])}",
            f"Hybrid 总耗时：{fmt_secs(summary['overall']['hybrid_total_seconds'])}",
            f"聚合时间优化：{fmt_pct(summary['overall']['time_optimization_pct'])}",
            f"基线平均质量：{summary['overall']['baseline_avg_quality']:.2f}",
            f"Hybrid 平均质量：{summary['overall']['hybrid_avg_quality']:.2f}",
            f"质量差值：{summary['overall']['quality_delta']:.2f}",
        ]
        note_lines = [
            "结论仅适用于可结构化、可验证、可闭环的通用任务范围。",
            "这不是对任意开放式任务或无限复杂任务的普遍保证。",
            "聚合维度优于基线且平均质量不退化，才构成公开发布证据。",
        ]
        conclusion_line = (
            "在本次重型矩阵覆盖范围内，当前锁定版 hybrid 具备公开发布条件。"
            if verdict["status"] == "GO"
            else "当前结果不支持公开发布，需要继续修正后再复测。"
        )
        tier_headers = ["层级", "任务数", "基线 Tokens", "Hybrid Tokens", "Token 优化", "基线耗时", "Hybrid 耗时", "时间优化", "基线质量", "Hybrid 质量"]
        matrix_headers = ["层级", "组别", "任务", "基线 Tokens", "Hybrid Tokens", "Token 优化", "基线耗时", "Hybrid 耗时", "时间优化", "基线质量", "Hybrid 质量"]
    else:
        regular_font = fonts["en_regular"]
        bold_font = fonts["en_bold"]
        title_text = "Hybrid General Task Heavy A/B Public Report"
        section_exec = "Executive Summary"
        section_basis = "Benchmark Basis"
        section_result = "Aggregate Outcome"
        section_tier = "Tier Aggregates"
        section_matrix = "Task Matrix"
        section_notes = "Interpretation and Limits"
        section_conclusion = "Conclusion"
        intro_lines = [
            "This public report evaluates the locked hybrid strategy on a fresh 4x3 heavy benchmark of general-purpose tasks.",
            "The matrix is intentionally non-ACL-X-centric and measures structured task execution across all four tiers.",
            f"Release recommendation: {verdict['status']}.",
        ]
        basis_lines = [
            f"Run ID: {summary['run_id']}",
            f"Strategy lock: {lock_name}",
            f"Generated at: {summary['generated_at']}",
            f"Matrix size: {summary['task_count']} tasks across t0/t1/t2/t3.",
            f"Baseline failed tasks: {verdict['baseline_failures']}.",
        ]
        overall_lines = [
            f"Baseline total tokens: {summary['overall']['baseline_total_tokens']}",
            f"Hybrid total tokens: {summary['overall']['hybrid_total_tokens']}",
            f"Aggregate token improvement: {fmt_pct(summary['overall']['token_optimization_pct'])}",
            f"Baseline total time: {fmt_secs(summary['overall']['baseline_total_seconds'])}",
            f"Hybrid total time: {fmt_secs(summary['overall']['hybrid_total_seconds'])}",
            f"Aggregate time improvement: {fmt_pct(summary['overall']['time_optimization_pct'])}",
            f"Baseline average quality: {summary['overall']['baseline_avg_quality']:.2f}",
            f"Hybrid average quality: {summary['overall']['hybrid_avg_quality']:.2f}",
            f"Quality delta: {summary['overall']['quality_delta']:.2f}",
        ]
        note_lines = [
            "The validated claim is bounded to structured general tasks with explicit artifacts, validators, and closure conditions.",
            "This is not a blanket guarantee for arbitrary open-ended work.",
            "Public release evidence requires aggregate token and time advantage with no average quality regression.",
        ]
        conclusion_line = (
            "Within the validated benchmark scope, the locked hybrid strategy is suitable for public release."
            if verdict["status"] == "GO"
            else "Within this benchmark scope, the current result is not sufficient for public release."
        )
        tier_headers = ["Tier", "Tasks", "Baseline Tokens", "Hybrid Tokens", "Token Improvement", "Baseline Time", "Hybrid Time", "Time Improvement", "Baseline Quality", "Hybrid Quality"]
        matrix_headers = ["Tier", "Group", "Task", "Baseline Tokens", "Hybrid Tokens", "Token Improvement", "Baseline Time", "Hybrid Time", "Time Improvement", "Baseline Quality", "Hybrid Quality"]

    title_style = make_style(styles["Title"], f"{language}_title", fontName=bold_font, fontSize=21, leading=24, alignment=TA_CENTER)
    h1 = make_style(styles["Heading1"], f"{language}_h1", fontName=bold_font, fontSize=15, leading=18, spaceAfter=6)
    body = make_style(styles["BodyText"], f"{language}_body", fontName=regular_font, fontSize=9, leading=12, alignment=TA_LEFT)
    small = make_style(styles["BodyText"], f"{language}_small", fontName=regular_font, fontSize=7.5, leading=9)

    story: list[Any] = []
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 6 * mm))

    for heading, lines in (
        (section_exec, intro_lines),
        (section_basis, basis_lines),
        (section_result, overall_lines),
    ):
        story.append(Paragraph(heading, h1))
        for line in lines:
            story.append(Paragraph(line, body))
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(section_tier, h1))
    tier_rows: list[list[Any]] = [[Paragraph(text, small) for text in tier_headers]]
    for tier_row in summary["tiers"]:
        agg = tier_row["aggregate"]
        tier_rows.append(
            [
                Paragraph(str(tier_row["tier"]), small),
                Paragraph(str(tier_row["task_count"]), small),
                Paragraph(str(agg["baseline_total_tokens"]), small),
                Paragraph(str(agg["hybrid_total_tokens"]), small),
                Paragraph(fmt_pct(agg["token_optimization_pct"]), small),
                Paragraph(fmt_secs(agg["baseline_total_seconds"]), small),
                Paragraph(fmt_secs(agg["hybrid_total_seconds"]), small),
                Paragraph(fmt_pct(agg["time_optimization_pct"]), small),
                Paragraph(f"{agg['baseline_avg_quality']:.2f}", small),
                Paragraph(f"{agg['hybrid_avg_quality']:.2f}", small),
            ]
        )
    tier_table = Table(
        tier_rows,
        colWidths=[18 * mm, 16 * mm, 28 * mm, 28 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm, 25 * mm, 25 * mm],
        repeatRows=1,
    )
    tier_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tier_table)
    story.append(PageBreak())

    story.append(Paragraph(section_matrix, h1))
    matrix_rows: list[list[Any]] = [[Paragraph(text, small) for text in matrix_headers]]
    for row in task_matrix_rows(summary):
        matrix_rows.append(
            [
                Paragraph(str(row["tier"]), small),
                Paragraph(str(row["group"]), small),
                Paragraph(str(row["title"]), small),
                Paragraph(str(row["baseline_tokens"]), small),
                Paragraph(str(row["hybrid_tokens"]), small),
                Paragraph(fmt_pct(row["token_pct"]), small),
                Paragraph(fmt_secs(row["baseline_time"]), small),
                Paragraph(fmt_secs(row["hybrid_time"]), small),
                Paragraph(fmt_pct(row["time_pct"]), small),
                Paragraph(str(row["baseline_quality"]), small),
                Paragraph(str(row["hybrid_quality"]), small),
            ]
        )
    matrix_table = Table(
        matrix_rows,
        colWidths=[14 * mm, 14 * mm, 56 * mm, 24 * mm, 24 * mm, 22 * mm, 20 * mm, 20 * mm, 22 * mm, 18 * mm, 18 * mm],
        repeatRows=1,
    )
    matrix_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(matrix_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(section_notes, h1))
    for line in note_lines:
        story.append(Paragraph(line, body))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(section_conclusion, h1))
    story.append(Paragraph(conclusion_line, body))
    return title_text, story


def render_pdf(
    *,
    summary: dict[str, Any],
    lock_name: str,
    verdict: dict[str, Any],
    language: str,
    output_path: Path,
) -> None:
    fonts = ensure_fonts()
    title, story = pdf_story(summary=summary, lock_name=lock_name, verdict=verdict, language=language, fonts=fonts)
    header_font = fonts["zh_regular"] if language == "zh" else fonts["en_regular"]
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="OpenAI Codex",
    )

    def header_footer(canvas_obj, doc_obj) -> None:
        canvas_obj.saveState()
        canvas_obj.setFont(header_font, 9)
        canvas_obj.drawString(doc_obj.leftMargin, doc_obj.height + doc_obj.topMargin + 10, title)
        canvas_obj.drawRightString(doc_obj.pagesize[0] - doc_obj.rightMargin, 12, f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def render_preview(pdf_path: Path, *, pages: int = 2) -> list[Path]:
    target_dir = TMP_PDF_ROOT / pdf_path.stem
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    with fitz.open(pdf_path) as document:
        max_pages = min(pages, document.page_count)
        for index in range(max_pages):
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            image_path = target_dir / f"page-{index + 1}.png"
            pixmap.save(image_path)
            output_paths.append(image_path)
    return output_paths


def distribute(paths: list[Path]) -> None:
    OUTPUT_PDF_ROOT.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, OUTPUT_PDF_ROOT / path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render bilingual public-facing reports from a hybrid general heavy summary.")
    parser.add_argument("summary_json", help="Path to the heavy summary JSON.")
    parser.add_argument("--lock-path", default=str(DEFAULT_LOCK_PATH), help="Optional strategy lock JSON path.")
    args = parser.parse_args()

    summary_path = Path(args.summary_json).resolve()
    if not summary_path.exists():
        raise SystemExit(f"Summary JSON not found: {summary_path}")

    summary = load_json(summary_path)
    run_id = str(summary["run_id"])
    lock_name = load_lock_name(Path(args.lock_path))
    verdict = compute_public_verdict(summary)

    en_md_path = summary_path.with_name(f"hybrid_general_task_public_report_en_{run_id}.md")
    zh_md_path = summary_path.with_name(f"hybrid_general_task_public_report_zh_{run_id}.md")
    en_pdf_path = summary_path.with_name(f"hybrid_general_task_public_report_en_{run_id}.pdf")
    zh_pdf_path = summary_path.with_name(f"hybrid_general_task_public_report_zh_{run_id}.pdf")

    en_md_path.write_text(english_markdown(summary, lock_name=lock_name, verdict=verdict), encoding="utf-8")
    zh_md_path.write_text(chinese_markdown(summary, lock_name=lock_name, verdict=verdict), encoding="utf-8")
    render_pdf(summary=summary, lock_name=lock_name, verdict=verdict, language="en", output_path=en_pdf_path)
    render_pdf(summary=summary, lock_name=lock_name, verdict=verdict, language="zh", output_path=zh_pdf_path)
    preview_paths = render_preview(en_pdf_path) + render_preview(zh_pdf_path)
    distribute([summary_path, en_md_path, zh_md_path, en_pdf_path, zh_pdf_path])

    print(json.dumps(
        {
            "summary_json": str(summary_path),
            "en_markdown": str(en_md_path),
            "zh_markdown": str(zh_md_path),
            "en_pdf": str(en_pdf_path),
            "zh_pdf": str(zh_pdf_path),
            "preview_images": [str(path) for path in preview_paths],
            "verdict": verdict["status"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
