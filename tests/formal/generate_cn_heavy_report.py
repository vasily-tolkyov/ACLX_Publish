from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PDF_ROOT = REPO_ROOT / "output" / "pdf"
FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")
FONT_NAME = "MSYH"
FONT_NAME_BOLD = "MSYH-Bold"

TIER_ZH = {
    "t0": "t0 单表面",
    "t1": "t1 单次交接",
    "t2": "t2 平衡共享态",
    "t3": "t3 循环重型",
}

GRADE_ZH = {
    "excellent": "优秀",
    "good": "良好",
    "partial": "部分达标",
    "poor": "较差",
}

TASK_ZH = {
    "t0_g1_release_summary": (
        "三行发布说明摘要",
        "读取一份简短的发布说明，按固定三行格式输出摘要，答案必须写出源文件路径并包含两个指定事实。它代表的是体量很小、但格式和字面保真要求很严格的只读提取任务。",
    ),
    "t0_g2_router_threshold_brief": (
        "路由阈值简报",
        "读取一份简短的路由阈值说明，按固定格式产出简报，要求写出源文件路径和关键阈值事实。它代表体量很小的配置查询任务，重点在格式稳定和事实保真。",
    ),
    "t0_g3_operator_note_brief": (
        "运维说明简报",
        "读取一份简短的运维说明，输出固定三行摘要，并包含源文件路径与两个显式事实。它代表超小型、只读、强调证据字段的提取任务。",
    ),
    "t1_g1_empty_input_review": (
        "空输入缺陷评审",
        "检查一个在空输入时会报错的小函数，只允许进行一次评审交接，然后输出带有结论和证据的结构化评审报告。它代表轻量的一次性交接评审任务。",
    ),
    "t1_g2_zero_sample_review": (
        "零样本缺陷评审",
        "检查一个在样本数为零时会失败的延迟辅助函数，只允许进行一次评审交接，并交付结构化评审结果。它代表没有共享状态的单次协作任务。",
    ),
    "t1_g3_missing_route_review": (
        "缺失路由评审",
        "检查一个遇到未知 key 会崩溃的路由选择器，只允许进行一次评审交接，并写出结构化评审结论。它代表带有明确证据要求的一次性交接任务。",
    ),
    "t2_g1_shared_pipeline_fix": (
        "共享流水线修复",
        "修复一个本地去重流水线中的缺陷，执行指定单元测试，写出供后续阶段复用的共享状态制品，并补充评审说明。它代表多步骤、本地可验证、同时要求代码与交接产物的修复任务。",
    ),
    "t2_g2_reviewer_queue_fix": (
        "评审队列修复",
        "修复评审队列中的归一化缺陷，执行指定单元测试，写出共享状态交接制品，并补充结构化评审说明。它代表多步骤的本地修复与共享状态协同任务。",
    ),
    "t2_g3_stage_plan_fix": (
        "阶段计划修复",
        "修复部署计划流程中丢失首阶段的问题，重新执行单元测试，写出下一阶段要复用的共享状态制品，并补充评审说明。它代表依赖任务合同保真的多步骤修复任务。",
    ),
    "t3_g1_review_loop_playbook": (
        "评审循环手册改写",
        "重写一份评审流程手册，要求每轮评审都以证据为先、角色边界清晰、范围不漂移，并用 checkpoint 记录保留循环状态。它代表重循环的文档类任务，而不是代码修复任务。",
    ),
    "t3_g2_release_signoff_handbook": (
        "发布签署手册改写",
        "重写一份发布签署手册，要求在最终签署前保留 blocker-first 的检查纪律，并让 checkpoint 可以支持中断后继续执行。它代表重循环的流程文档任务。",
    ),
    "t3_g3_resume_handoff_guide": (
        "恢复交接指南改写",
        "重写一份恢复与交接指南，要求保留 latest-checkpoint 恢复机制、优先延续未解决事项，并确保多轮中断后仍能连续推进。它代表重循环的连续性文档任务。",
    ),
}

EXEC_SCOPE_ZH = [
    "Hybrid 是面向特定本地工作流的局限性优化方案，不是对任意通用任务都成立的通用优化方案。",
    "它可以执行通用任务，但只要任务族超出本报告验证范围，输出质量、Token 优化和时间优化都不能保证。",
    "因此，本报告应被理解为面向受控本地工程任务的发布前估计，而不是对所有任务类型和复杂度都适用的统一结论。",
]

METHOD_ZH = [
    "本轮正式测试对比自然语言基线（NL baseline）与当前自适应 Hybrid 策略。",
    "测试集包含 4 档、每档 3 组、共 12 个本地重型任务。",
    "Token 统计优先使用 Codex 实际上报总消耗，只有在缺失时才回退为提示词加可见输出的估算值。",
    "输出质量采用任务专属 validator，并统一映射为 0 到 100 分。",
]

CLASSIFICATION_LIMITS_ZH = [
    "四档分类本质上是按运行结构做的路由启发式，不是对任务语义或业务价值的通用分类法。",
    "同一个用户任务，一旦新增显式文件、可复用交接状态、循环 checkpoint 或恢复要求，就可能落入不同档位。",
    "边界最不稳定的是混合任务：一个最初只是读取信息的小任务，可能因为临时增加测试、修复或复核要求而跨档变化。",
    "当真正的成功标准主要存在于本地验证器之外、工作区之外或隐性上下文中时，这套分类的解释力会明显下降。",
]

RECOMMENDED_TASK_FAMILIES_ZH = [
    "本地只读提取或摘要任务，而且输出格式、字面短语和证据字段要求明确。",
    "只包含一次明确交接的一次性评审任务，并且需要产出结构化文档。",
    "带有明确文件、测试命令和交接制品的本地多步骤代码或配置修复任务。",
    "具有 checkpoint、恢复点和客观内容要求的循环式文档或流程手册改写任务。",
]

NON_REPRESENTATIVE_TASK_FAMILIES_ZH = [
    "开放式网络检索、产品策略讨论或范围会在执行中持续变化的探索型任务。",
    "创意写作、审美驱动产出或主要依赖主观判断的任务。",
    "依赖远程系统、人工审批、外部服务或网络时延的生产运维类任务。",
    "强依赖隐性背景知识、口头约定或人工补充上下文的人在环流程任务。",
]


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}%"


def sec(value: float) -> str:
    return f"{float(value):.2f}"


def text(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def note_zh(note: str) -> str:
    if note.startswith("exactly ") and " non-empty lines" in note:
        count = note.split()[1]
        return f"输出恰好 {count} 行非空内容"
    if note == "tier line correct":
        return "Tier 行正确"
    if note == "tier line missing or incorrect":
        return "Tier 行缺失或错误"
    if note.startswith("evidence names "):
        return f"Evidence 行包含 {note[len('evidence names '):]}"
    if note.startswith("evidence missing "):
        return f"Evidence 行缺失 {note[len('evidence missing '):]}"
    if note.startswith("required facts present: "):
        return f"要求事实命中 {note[len('required facts present: '):]}"
    if note == "review report written":
        return "已生成评审报告"
    if note == "review report missing":
        return "评审报告缺失"
    if note == "required headings present":
        return "必需标题齐全"
    if note == "required headings missing":
        return "必需标题缺失"
    if note.startswith("report cites "):
        return f"报告引用了 {note[len('report cites '):]}"
    if note.startswith("report missing concrete path "):
        return f"报告缺少具体路径 {note[len('report missing concrete path '):]}"
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
    if note.startswith("document content checks: "):
        return f"文档内容检查命中 {note[len('document content checks: '):]}"
    if note.startswith("document heading checks: "):
        return f"文档标题检查命中 {note[len('document heading checks: '):]}"
    if note == "no document headings required":
        return "无额外标题要求"
    if note.startswith("checkpoint note checks: "):
        return f"Checkpoint 记录检查命中 {note[len('checkpoint note checks: '):]}"
    if note == "checkpoint note present":
        return "已生成 checkpoint 记录"
    if note == "checkpoint note missing":
        return "checkpoint 记录缺失"
    if note.endswith(" missing"):
        return f"缺失文件 {note[:-len(' missing')]}"
    return note


def para(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text(value), style)


def task_zh(task_name: str, title: str, description: str) -> tuple[str, str]:
    return TASK_ZH.get(task_name, (title, description))


def tier_aggregate(summary: dict, tier: str) -> dict:
    for row in summary["tiers"]:
        if str(row["tier"]).lower() == tier.lower():
            return row["aggregate"]
    raise KeyError(f"missing tier aggregate for {tier}")


def effective_token_count(row: dict) -> int:
    reported = row.get("reported_total_tokens")
    if isinstance(reported, int):
        return reported
    return int(row.get("estimated_total_tokens") or 0)


def t0_negative_lines_zh(summary: dict) -> list[str]:
    agg = tier_aggregate(summary, "t0")
    negative_rows = [
        row
        for row in summary["tasks"]
        if str(row["tier"]).lower() == "t0" and float(row["token_optimization_pct"]) < 0
    ]
    labels = "、".join(
        f"{task_zh(row['task_name'], row['title'], row['description'])[0]}（{pct(row['token_optimization_pct'])}）"
        for row in negative_rows
    )
    return [
        (
            f"在当前正式结果中，t0 档整体 Token 优化率为 {pct(agg['token_optimization_pct'])}，时间优化率为 {pct(agg['time_optimization_pct'])}，"
            f"平均质量由 {agg['baseline_avg_quality']:.2f} 提升到 {agg['hybrid_avg_quality']:.2f}。"
        ),
        f"出现负 Token 优化的任务主要是：{labels}。",
        "根因是固定开销占比过高。对于体量极小、只读、输出极短的任务，Hybrid 额外引入的路由包装、保真约束和更严格的提示合同，本身就可能比任务正文更耗 Token。",
        "这不等同于当前结果中的质量退化。相反，t0 在本轮测试里质量没有低于 baseline，但由于任务过小，额外控制成本无法被摊薄，导致 Token 效率不稳定。",
        "实际影响是：对这类超小任务，Hybrid 更适合拿来保格式、保字面要求、保一致性，而不适合被当成稳定的 Token 节省器。",
    ]


def append_lines(story: list, lines: list[str], style: ParagraphStyle, *, bullets: bool = False) -> None:
    prefix = "- " if bullets else ""
    for line in lines:
        story.append(para(f"{prefix}{line}" if bullets else line, style))


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_REGULAR), subfontIndex=0))
    pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, str(FONT_BOLD), subfontIndex=0))


def styles() -> dict[str, ParagraphStyle]:
    base_styles = getSampleStyleSheet()
    body = ParagraphStyle(
        name="BodyCN",
        parent=base_styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
    )
    return {
        "body": body,
        "title": ParagraphStyle(
            name="TitleCN",
            parent=body,
            fontName=FONT_NAME_BOLD,
            fontSize=20,
            leading=26,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            name="SubtitleCN",
            parent=body,
            fontSize=11,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4A4A4A"),
        ),
        "h1": ParagraphStyle(
            name="H1CN",
            parent=body,
            fontName=FONT_NAME_BOLD,
            fontSize=15,
            leading=20,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            name="H2CN",
            parent=body,
            fontName=FONT_NAME_BOLD,
            fontSize=12.5,
            leading=17,
            spaceBefore=8,
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            name="SmallCN",
            parent=body,
            fontSize=9,
            leading=12,
        ),
        "small_center": ParagraphStyle(
            name="SmallCenterCN",
            parent=body,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
        ),
    }


def build_story(summary: dict) -> list:
    st = styles()
    body = st["body"]
    small = st["small"]
    small_center = st["small_center"]
    overall = summary["overall"]
    release_reco = "GO" if summary.get("release_ready") else "HOLD"
    story: list = []

    story.append(para("Hybrid 策略发布前本地重型测试报告（中文版）", st["title"]))
    story.append(para("基于当前正式 summary 动态生成", st["subtitle"]))
    story.append(Spacer(1, 6 * mm))

    info_rows = [
        [para("报告类型", body), para("Hybrid 发布前本地重型测试正式报告", body)],
        [para("Run ID", body), para(summary.get("run_id", ""), body)],
        [para("生成时间", body), para(summary.get("generated_at", ""), body)],
        [para("测试任务数", body), para(str(summary.get("task_count", "")), body)],
        [para("Formal Run Root", body), para(summary.get("run_root", ""), small)],
        [para("门禁测试通过", body), para("是" if int(summary.get("gate_tests", {}).get("exit_code", 1)) == 0 else "否", body)],
        [para("策略锁一致", body), para("是" if not summary.get("lock_mismatches") else "否", body)],
        [para("发布建议", body), para(release_reco, body)],
    ]
    info_table = Table(info_rows, colWidths=[35 * mm, 145 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF4FF")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#6B7C93")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9AA9B8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 5 * mm))

    story.append(para("一、执行摘要与适用边界", st["h1"]))
    append_lines(story, EXEC_SCOPE_ZH, body)
    story.append(Spacer(1, 3 * mm))
    story.append(para("二、测试范围与统计口径", st["h1"]))
    append_lines(story, METHOD_ZH, body)

    overview_rows = [
        [para("指标", body), para("数值", body)],
        [para("Baseline 总 Token", body), para(str(overall["baseline_total_tokens"]), body)],
        [para("Hybrid 总 Token", body), para(str(overall["hybrid_total_tokens"]), body)],
        [para("Token 优化率", body), para(pct(overall["token_optimization_pct"]), body)],
        [para("Baseline 总时间（秒）", body), para(sec(overall["baseline_total_seconds"]), body)],
        [para("Hybrid 总时间（秒）", body), para(sec(overall["hybrid_total_seconds"]), body)],
        [para("时间优化率", body), para(pct(overall["time_optimization_pct"]), body)],
        [para("Baseline 平均质量", body), para(f"{overall['baseline_avg_quality']:.2f}", body)],
        [para("Hybrid 平均质量", body), para(f"{overall['hybrid_avg_quality']:.2f}", body)],
        [para("平均质量差值", body), para(f"{overall['quality_delta']:.2f}", body)],
    ]
    overview_table = Table(overview_rows, colWidths=[50 * mm, 50 * mm])
    overview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#6B7C93")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9AA9B8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(overview_table)
    story.append(Spacer(1, 4 * mm))
    story.append(
        para(
            f"整体结果显示：Hybrid 在本轮 12 项正式任务上实现 Token 总优化 {pct(overall['token_optimization_pct'])}，"
            f"时间总优化 {pct(overall['time_optimization_pct'])}，平均质量分由 {overall['baseline_avg_quality']:.2f} 提升到 {overall['hybrid_avg_quality']:.2f}。"
            f"按当前 formal 口径，发布建议为 {release_reco}。",
            body,
        )
    )

    story.append(Spacer(1, 3 * mm))
    story.append(para("三、分类局限性与推荐适用范围", st["h1"]))
    story.append(para("1. 分类局限性", st["h2"]))
    append_lines(story, CLASSIFICATION_LIMITS_ZH, body, bullets=True)
    story.append(Spacer(1, 2 * mm))
    story.append(para("2. 推荐参考当前结果的任务族", st["h2"]))
    append_lines(story, RECOMMENDED_TASK_FAMILIES_ZH, body, bullets=True)
    story.append(Spacer(1, 2 * mm))
    story.append(para("3. 不应直接参考当前结果的任务族", st["h2"]))
    append_lines(story, NON_REPRESENTATIVE_TASK_FAMILIES_ZH, body, bullets=True)
    story.append(Spacer(1, 3 * mm))
    story.append(para("四、t0 负优化原因与影响", st["h1"]))
    append_lines(story, t0_negative_lines_zh(summary), body)
    story.append(PageBreak())

    story.append(para("五、各档测试任务选择说明", st["h1"]))
    selection_rows = [
        [
            para("档位", small_center),
            para("组别", small_center),
            para("任务名称", small_center),
            para("测试任务描述", small_center),
        ]
    ]
    for row in summary["tasks"]:
        title_zh, desc_zh = task_zh(row["task_name"], row["title"], row["description"])
        selection_rows.append(
            [
                para(TIER_ZH.get(row["tier"], row["tier"]), small_center),
                para(str(row["group"]), small_center),
                para(title_zh, small),
                para(desc_zh, small),
            ]
        )
    selection_table = Table(selection_rows, colWidths=[28 * mm, 15 * mm, 42 * mm, 95 * mm], repeatRows=1)
    selection_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E8FB")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#6B7C93")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9AA9B8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(selection_table)
    story.append(PageBreak())

    story.append(para("六、档位汇总统计", st["h1"]))
    token_rows = [[para("档位", small_center), para("任务数", small_center), para("Baseline Token", small_center), para("Hybrid Token", small_center), para("Token 优化率", small_center)]]
    time_rows = [[para("档位", small_center), para("Baseline 时间", small_center), para("Hybrid 时间", small_center), para("时间优化率", small_center), para("Baseline 平均质量 / Hybrid 平均质量", small_center)]]
    for tier_row in summary["tiers"]:
        agg = tier_row["aggregate"]
        token_rows.append(
            [
                para(TIER_ZH.get(tier_row["tier"], tier_row["tier"]), small_center),
                para(str(tier_row["task_count"]), small_center),
                para(str(agg["baseline_total_tokens"]), small_center),
                para(str(agg["hybrid_total_tokens"]), small_center),
                para(pct(agg["token_optimization_pct"]), small_center),
            ]
        )
        time_rows.append(
            [
                para(TIER_ZH.get(tier_row["tier"], tier_row["tier"]), small_center),
                para(sec(agg["baseline_total_seconds"]), small_center),
                para(sec(agg["hybrid_total_seconds"]), small_center),
                para(pct(agg["time_optimization_pct"]), small_center),
                para(f"{agg['baseline_avg_quality']:.2f} / {agg['hybrid_avg_quality']:.2f}", small_center),
            ]
        )
    for rows in (token_rows, time_rows):
        table = Table(rows, colWidths=[36 * mm, 20 * mm, 35 * mm, 35 * mm, 38 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#6B7C93")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9AA9B8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 4 * mm))

    story.append(para("七、逐任务详细结果", st["h1"]))
    for idx, row in enumerate(summary["tasks"], start=1):
        title_zh, desc_zh = task_zh(row["task_name"], row["title"], row["description"])
        baseline = row["baseline"]
        hybrid = row["hybrid"]
        story.append(para(f"{idx}. [{row['tier'].upper()} G{row['group']}] {title_zh}", st["h2"]))
        story.append(para(f"测试任务描述：{desc_zh}", body))
        metric_rows = [
            [para("指标", small_center), para("NL baseline", small_center), para("Hybrid", small_center), para("优化 / 差值", small_center)],
            [para("Token 总消耗", small), para(str(effective_token_count(baseline)), small_center), para(str(effective_token_count(hybrid)), small_center), para(pct(row["token_optimization_pct"]), small_center)],
            [para("运行时间（秒）", small), para(sec(baseline["elapsed_seconds"]), small_center), para(sec(hybrid["elapsed_seconds"]), small_center), para(pct(row["time_optimization_pct"]), small_center)],
            [para("输出质量分", small), para(f"{baseline['quality_score']}（{GRADE_ZH.get(baseline['quality_grade'], baseline['quality_grade'])}）", small_center), para(f"{hybrid['quality_score']}（{GRADE_ZH.get(hybrid['quality_grade'], hybrid['quality_grade'])}）", small_center), para(f"{row['quality_delta']:+d}", small_center)],
            [para("路由符合预期", small), para("-", small_center), para("是" if row["route_matches_expected"] else "否", small_center), para("-", small_center)],
        ]
        metric_table = Table(metric_rows, colWidths=[35 * mm, 43 * mm, 43 * mm, 43 * mm], repeatRows=1)
        metric_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E8FB")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#6B7C93")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9AA9B8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(metric_table)
        story.append(Spacer(1, 2 * mm))
        story.append(para("Baseline 质量说明：" + "；".join(note_zh(item) for item in baseline["quality_notes"]), small))
        story.append(para("Hybrid 质量说明：" + "；".join(note_zh(item) for item in hybrid["quality_notes"]), small))
        story.append(Spacer(1, 3 * mm))

    story.append(PageBreak())
    story.append(para("八、发布结论", st["h1"]))
    story.append(
        para(
            f"本轮正式本地重型测试覆盖 t0 到 t3 四档、共 {summary.get('task_count', 0)} 个任务。Hybrid 在总体上实现了 "
            f"{pct(overall['token_optimization_pct'])} 的 Token 优化与 {pct(overall['time_optimization_pct'])} 的时间优化，"
            f"平均质量由 {overall['baseline_avg_quality']:.2f} 提升到 {overall['hybrid_avg_quality']:.2f}。",
            body,
        )
    )
    story.append(
        para(
            "当前发布建议仅针对本报告覆盖的受控本地工程任务范围成立，不应被表述为对任意通用任务都保证有效。"
            f"按当前 formal 口径，发布建议为 {release_reco}。",
            body,
        )
    )
    return story


def draw_header_footer(canvas_obj, doc) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont(FONT_NAME, 9)
    canvas_obj.drawString(doc.leftMargin, doc.height + doc.topMargin + 10, "Hybrid 策略发布前本地重型测试报告（中文版）")
    canvas_obj.drawRightString(doc.pagesize[0] - doc.rightMargin, 12, f"第 {doc.page} 页")
    canvas_obj.restoreState()


def build_pdf(target: Path, story: list) -> None:
    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="Hybrid 策略发布前本地重型测试报告（中文版）",
    )
    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)


def default_output_path(summary_path: Path) -> Path:
    return OUTPUT_PDF_ROOT / f"{summary_path.stem}_cn.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Chinese PDF heavy report from a summary JSON.")
    parser.add_argument("--summary", required=True, help="Path to the summary JSON.")
    parser.add_argument("--output", help="Optional explicit output PDF path.")
    parser.add_argument("--desktop-copy", action="store_true", help="Also copy the generated PDF to the desktop.")
    args = parser.parse_args()

    summary_path = Path(args.summary).resolve()
    output_pdf = Path(args.output).resolve() if args.output else default_output_path(summary_path)
    run_copy = summary_path.with_name(f"{summary_path.stem}_cn.pdf")
    desktop_copy = Path.home() / "Desktop" / output_pdf.name

    register_fonts()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    story = build_story(summary)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(output_pdf, story)
    shutil.copy2(output_pdf, run_copy)
    if args.desktop_copy:
        shutil.copy2(output_pdf, desktop_copy)
    print(output_pdf)
    print(run_copy)
    if args.desktop_copy:
        print(desktop_copy)


if __name__ == "__main__":
    main()
