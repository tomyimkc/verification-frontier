#!/usr/bin/env python3
"""Build the Simplified Chinese and English four-page GOAI PDFs."""
from __future__ import annotations

import os
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    from .pdf_contract import INVARIANT_PDF_DATE
except ImportError:
    from pdf_contract import INVARIANT_PDF_DATE

HERE = Path(__file__).resolve().parent
ZH_PDF = HERE / "GOAI-AI4R-Open-Exploration-ZH.pdf"
EN_PDF = HERE / "GOAI-AI4R-Open-Exploration-EN.pdf"


def register_unicode_font() -> str:
    override = os.environ.get("GOAI_PDF_FONT")
    candidates = [
        Path(override).expanduser() if override else None,
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    checked: list[str] = []
    failures: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        checked.append(str(candidate))
        if candidate.is_file():
            try:
                pdfmetrics.registerFont(TTFont("SubmissionUnicode", str(candidate)))
            except Exception as exc:
                failures.append(f"{candidate}: {type(exc).__name__}: {exc}")
                continue
            return "SubmissionUnicode"
    details = f" Checked: {checked}."
    if failures:
        details += f" Load failures: {failures}."
    raise RuntimeError(
        "No supported Unicode font found for bilingual PDF generation. "
        "Set GOAI_PDF_FONT to a readable CJK-capable TTF/TTC file." + details
    )


FONT = register_unicode_font()


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=FONT,
            fontSize=22,
            leading=27,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17365D"),
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=10,
            leading=13.5,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#555555"),
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=FONT,
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#17365D"),
            spaceBefore=2,
            spaceAfter=5,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=FONT,
            fontSize=12,
            leading=15.5,
            textColor=colors.HexColor("#2F5597"),
            spaceBefore=4,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=5.5,
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.4,
            leading=11,
            alignment=TA_LEFT,
            spaceAfter=2,
            wordWrap="CJK",
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.4,
            leading=11,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=0,
            wordWrap="CJK",
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=10.3,
            leading=14.5,
            leftIndent=8,
            rightIndent=8,
            borderColor=colors.HexColor("#9FBAD0"),
            borderWidth=0.8,
            borderPadding=6,
            backColor=colors.HexColor("#F3F7FA"),
            spaceBefore=4,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName=FONT,
            fontSize=8.2,
            leading=11,
            leftIndent=6,
            borderColor=colors.HexColor("#D9E2F3"),
            borderWidth=0.5,
            borderPadding=5,
            backColor=colors.HexColor("#F8F9FB"),
            spaceBefore=3,
            spaceAfter=5,
        ),
    }


S = styles()


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def bullets(items: list[str]) -> list[Paragraph]:
    return [P(f"• {item}") for item in items]


def styled_table(
    data: list[list[str]],
    widths: list[float],
    *,
    font_size: float = 7.1,
) -> Table:
    rows = []
    for row_index, row in enumerate(data):
        style = "table_head" if row_index == 0 else "small"
        rows.append(
            [P(cell, style) if not isinstance(cell, Paragraph) else cell for cell in row]
        )
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), font_size + 2.2),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#A6A6A6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def footer(language: str):
    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E2F3"))
        canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
        canvas.setFont(FONT, 6.6)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(
            18 * mm,
            8.5 * mm,
            f"GOAI 2026 AI for Research | {language} | candidateOnly:true | canClaimAGI:false",
        )
        canvas.drawRightString(192 * mm, 8.5 * mm, f"{canvas.getPageNumber()} / 4")
        canvas.restoreState()

    return draw


def zh_story() -> list:
    story: list = [
        P("面向开放科学探索的失效闭合验证阶梯", "title"),
        P("A Fail-Closed Verification Ladder for Open Scientific Exploration", "subtitle"),
        P(
            "GOAI 2026 前沿探索 / AI for Research — 开放探索赛题<br/>"
            "Yim Kin Cheong（Tom）｜独立研究者｜香港｜Apache-2.0",
            "subtitle",
        ),
        P("1. 真实研究问题", "h1"),
        P(
            "开放科学探索中的 Agent 不仅要生成候选步骤，还必须知道当前工具能否检查该步骤。"
            "缺少明确覆盖状态时，“没有验证工具”可能被错误地当成“没有发现错误”，形成静默通过。"
        ),
        P(
            "能否构建一个紧凑、可运行的科学探索环境，使 Agent 在每一步都能区分“已被验证”、"
            "“已被证伪”和“当前验证器无法检查”，并据此保留、修正或标记该步骤？",
            "quote",
        ),
        P("开放探索三项核心约束", "h2"),
        *bullets(
            [
                "<b>真实问题：</b>科学 Agent 的验证覆盖范围经常是隐式的，无法可靠支持迭代。",
                "<b>探索环境：</b>固定问题、验证器与接口；Agent 可改变候选答案和后续修正。",
                "<b>发现信号：</b>三值结果、原因代码、后续动作和逐步 JSONL 记录。",
            ]
        ),
        Spacer(1, 4),
        P(
            "<b>声明边界：</b>本项目不尝试解决黎曼猜想，也不将模型低通过率包装为科研能力。"
            "提交物是环境与验证记录。"
        ),
        PageBreak(),
        P("2. 可运行环境与探索闭环", "h1"),
        styled_table(
            [
                ["结果", "合同含义"],
                ["accepted", "适用的确定性检查在其合同范围内确认候选成立"],
                ["rejected", "适用的确定性检查确认了具体错误"],
                ["abstain", "没有适用的可执行检查能够判断；绝不静默通过"],
            ],
            [35 * mm, 135 * mm],
        ),
        Spacer(1, 6),
        P("验证层", "h2"),
        *bullets(
            [
                "<b>SI 物理：</b>量纲与数值容差，纯 Python。",
                "<b>符号数学：</b>可选 SymPy 等价性检查；缺失时明确报告 sympy_unavailable。",
                "<b>形式证明：</b>Lean 结果作为外部固定证据；紧凑包不声称捆绑 Lean。",
            ]
        ),
        P("探索闭环", "h2"),
        P(
            "问题观察 → 策略提出候选 → 验证器返回 accepted / rejected / abstain<br/>"
            "→ 保留 / 修正 / 停止 / 标记为当前不可验证 → 写入 JSONL step receipt",
            "code",
        ),
        P("最小参照系", "h2"),
        styled_table(
            [
                ["策略", "用途"],
                ["always-answer", "测试持续作答时的接受、拒绝与覆盖弃权"],
                ["abstain-all", "测试无条件保守策略"],
                ["single-shot", "测试不修正的一次性候选"],
                ["scripted-refine", "测试收到拒绝后修正并再次验证"],
            ],
            [42 * mm, 128 * mm],
        ),
        PageBreak(),
        P("3. 运行证据与诚实解释", "h1"),
        P("紧凑环境开发基准（SymPy 1.14.0）", "h2"),
        styled_table(
            [
                ["策略", "步数", "接受", "拒绝", "弃权"],
                ["always-answer", "6", "4", "1", "1"],
                ["abstain-all", "6", "0", "0", "6"],
                ["single-shot", "6", "1", "5", "0"],
                ["scripted-refine", "12", "5", "0", "1"],
            ],
            [56 * mm, 25 * mm, 28 * mm, 28 * mm, 28 * mm],
        ),
        P(
            "所有策略对 open-unformalized 项目的接受数均为 0。无 SymPy 时环境仍可运行，"
            "符号层明确弃权，而不是把工具缺失计为成功。"
        ),
        P("既有候选阶梯证据", "h2"),
        styled_table(
            [
                ["层级", "n", "接受", "拒绝", "弃权", "解释"],
                ["closed", "10", "5", "5", "0", "已知证明与故意错误占位符的检查"],
                ["held-out", "10", "0", "10", "0", "固定 Lean 检查器下的候选模型证明失败"],
                ["open-unformalized", "11", "0", "0", "11", "缺少可执行命题时的环境合同行为"],
            ],
            [35 * mm, 13 * mm, 18 * mm, 18 * mm, 18 * mm, 68 * mm],
            font_size=6.6,
        ),
        P(
            "<b>关键解释：</b>开放层弃权不是“模型知道问题未解”的证据。完整阶梯运行未预注册，"
            "保持候选证据；held-out 与 open-unformalized 必须分开报告。"
        ),
        P(
            "机器可读产物：artifacts/episodes.jsonl、benchmark-summary.json 与"
            " verify_artifacts.py。验证器在开放项被接受、claim ceiling 消失或 episode"
            " 缺少终止记录时失败。"
        ),
        PageBreak(),
        P("4. 贡献、相关工作、开放性与延续路径", "h1"),
        P(
            "本项目不声称发明确定性验证、Agent 弃权、验证边界、量纲分析、SymPy、Lean 或 RLVR。"
            "直接相关工作包括 RLVP（arXiv:2607.10474）、EG-VAR（arXiv:2607.12650）、"
            "Recursive Epistemic Engines 的 Novelty Horizon 和 AgentAbstain"
            "（arXiv:2607.10059）。"
        ),
        P("竞赛期贡献", "h2"),
        *bullets(
            [
                "显式三值验证覆盖合同及原因代码；",
                "propose → verify → act 多步环境和四个确定性参照策略；",
                "JSONL 日志、机器可读摘要与失效闭合产物验证；",
                "将模型证据与环境设计的弃权分开报告；",
                "中英文四页材料与可复现紧凑包。",
            ]
        ),
        P("披露", "h2"),
        P(
            "<b>预先存在：</b>Sophia 的 SI、数学、step、Lean 验证器，形式证明评测与既有候选结果。"
            "<br/><b>竞赛期新增：</b>GOAI 包装、环境闭环、基线、日志、合规相关工作比较与双语材料。"
        ),
        P("复现", "h2"),
        P(
            "python3 demo.py --selfcheck<br/>"
            "python3 -m unittest -v test_demo.py<br/>"
            "python3 demo.py --benchmark --output-dir artifacts<br/>"
            "python3 verify_artifacts.py artifacts",
            "code",
        ),
        P(
            "<b>限制：</b>六个紧凑问题不是科学 benchmark；策略不是学习型 Agent；Lean 不在紧凑包内；"
            "领域仅覆盖物理与数学。candidateOnly:true；canClaimAGI:false。"
        ),
    ]
    return story


def en_story() -> list:
    story: list = [
        P("A Fail-Closed Verification Ladder for Open Scientific Exploration", "title"),
        P("面向开放科学探索的失效闭合验证阶梯", "subtitle"),
        P(
            "GOAI 2026 AI for Research — Open Exploration<br/>"
            "Yim Kin Cheong (Tom) | Independent Researcher | Hong Kong | Apache-2.0",
            "subtitle",
        ),
        P("1. Real research problem", "h1"),
        P(
            "A scientific agent needs more than candidate generation. At every step it must "
            "know whether its current tools can check the proposal. When verifier coverage "
            "is implicit, “no applicable check” can be confused with “no error found,” "
            "creating a silent pass."
        ),
        P(
            "Can a compact, runnable scientific-exploration environment distinguish verified, "
            "refuted, and currently unsupported steps so an agent can keep, revise, or "
            "explicitly mark each proposal?",
            "quote",
        ),
        P("Three Open Exploration constraints", "h2"),
        *bullets(
            [
                "<b>Real problem:</b> scientific-agent verifier coverage is often implicit and cannot reliably guide iteration.",
                "<b>Exploration environment:</b> problems, verifiers, and interfaces are fixed; proposals and revisions can change.",
                "<b>Discovery signal:</b> typed verdicts, reason codes, next actions, and JSONL step receipts.",
            ]
        ),
        Spacer(1, 4),
        P(
            "<b>Claim boundary:</b> the project does not attempt to solve the Riemann "
            "Hypothesis and does not present low model pass rates as scientific capability."
        ),
        PageBreak(),
        P("2. Runnable environment and loop", "h1"),
        styled_table(
            [
                ["Outcome", "Contract"],
                ["accepted", "An applicable deterministic check establishes the candidate."],
                ["rejected", "An applicable deterministic check establishes a concrete error."],
                ["abstain", "No applicable executable check can decide; never a silent pass."],
            ],
            [35 * mm, 135 * mm],
        ),
        Spacer(1, 6),
        P("Verifier tiers", "h2"),
        *bullets(
            [
                "<b>SI physics:</b> dimension and numeric tolerance in pure Python.",
                "<b>Symbolic mathematics:</b> optional SymPy equivalence; reports sympy_unavailable when absent.",
                "<b>Formal proof:</b> Lean results are external pinned evidence; Lean is not claimed as bundled.",
            ]
        ),
        P("Episode contract", "h2"),
        P(
            "problem observation → policy proposal → accepted / rejected / abstain<br/>"
            "→ keep / revise / stop / mark unsupported → JSONL step receipt",
            "code",
        ),
        P("Minimal reference systems", "h2"),
        styled_table(
            [
                ["Policy", "Purpose"],
                ["always-answer", "Exercises acceptance, rejection, and coverage abstention."],
                ["abstain-all", "Exercises unconditional conservatism."],
                ["single-shot", "Exercises one proposal without revision."],
                ["scripted-refine", "Exercises rejection followed by a revised proposal."],
            ],
            [42 * mm, 128 * mm],
        ),
        PageBreak(),
        P("3. Operational evidence and interpretation", "h1"),
        P("Compact environment benchmark with SymPy 1.14.0", "h2"),
        styled_table(
            [
                ["Policy", "Steps", "Accepted", "Rejected", "Abstain"],
                ["always-answer", "6", "4", "1", "1"],
                ["abstain-all", "6", "0", "0", "6"],
                ["single-shot", "6", "1", "5", "0"],
                ["scripted-refine", "12", "5", "0", "1"],
            ],
            [56 * mm, 25 * mm, 28 * mm, 28 * mm, 28 * mm],
        ),
        P(
            "Every policy has zero acceptance on the open-unformalized item. Without SymPy, "
            "the environment still runs and reports explicit symbolic-tier abstention."
        ),
        P("Existing candidate ladder receipt", "h2"),
        styled_table(
            [
                ["Rung", "n", "Accepted", "Rejected", "Abstain", "Interpretation"],
                ["closed", "10", "5", "5", "0", "Known versus deliberately wronged proof checks."],
                ["held-out", "10", "0", "10", "0", "Candidate model-proof failures under pinned Lean."],
                ["open-unformalized", "11", "0", "0", "11", "Environment behavior without executable propositions."],
            ],
            [35 * mm, 13 * mm, 18 * mm, 18 * mm, 18 * mm, 68 * mm],
            font_size=6.6,
        ),
        P(
            "<b>Critical interpretation:</b> open-rung abstention is not evidence that a model "
            "recognized an unsolved problem. The full ladder run was not preregistered and "
            "remains candidate evidence."
        ),
        P(
            "Machine-readable artifacts are episodes.jsonl, benchmark-summary.json, and "
            "verify_artifacts.py. Validation fails on open acceptance, missing claim-ceiling "
            "fields, or missing terminal receipts."
        ),
        PageBreak(),
        P("4. Contribution, related work, openness, and continuation", "h1"),
        P(
            "The project does not claim to invent deterministic verification, agent "
            "abstention, verification frontiers, dimensional analysis, SymPy, Lean, or RLVR. "
            "Direct prior work includes RLVP (arXiv:2607.10474), EG-VAR "
            "(arXiv:2607.12650), Recursive Epistemic Engines and its Novelty Horizon, "
            "and AgentAbstain (arXiv:2607.10059)."
        ),
        P("Contest-period contribution", "h2"),
        *bullets(
            [
                "An explicit three-state coverage contract and reason codes;",
                "a multi-step propose → verify → act environment and four deterministic reference policies;",
                "JSONL traces, machine-readable summaries, and fail-closed artifact validation;",
                "separate reporting of model evidence and environment-designed abstention;",
                "Simplified Chinese and English four-page materials.",
            ]
        ),
        P("Disclosure", "h2"),
        P(
            "<b>Pre-existing:</b> Sophia SI, mathematics, step, and Lean verifier "
            "infrastructure, formal-proof evaluations, and prior candidate results."
            "<br/><b>Contest-period:</b> GOAI packaging, environment loop, baselines, "
            "receipts, claim-safe related work, and bilingual materials."
        ),
        P("Reproduce", "h2"),
        P(
            "python3 demo.py --selfcheck<br/>"
            "python3 -m unittest -v test_demo.py<br/>"
            "python3 demo.py --benchmark --output-dir artifacts<br/>"
            "python3 verify_artifacts.py artifacts",
            "code",
        ),
        P(
            "<b>Limits:</b> six compact problems are not a scientific benchmark; policies "
            "are not learned agents; Lean is not bundled; domains are physics and mathematics. "
            "candidateOnly:true; canClaimAGI:false."
        ),
    ]
    return story


def zh_story() -> list:
    """Winner-oriented v2 Simplified Chinese four-page narrative."""
    return [
        P("安全扩展科学 Agent 的验证边界", "title"),
        P("Safely Expanding the Verification Frontier of Scientific Agents", "subtitle"),
        P(
            "GOAI 2026 前沿探索 / AI for Research — 开放探索赛题<br/>"
            "Yim Kin Cheong（Tom）｜独立研究者｜香港｜Apache-2.0",
            "subtitle",
        ),
        P("1. 研究问题与拟议贡献", "h1"),
        P(
            "科学 Agent 必须区分：可执行检查确认候选、可执行检查证伪候选、以及候选超出当前"
            "验证器覆盖范围。把第三种情况当成“没有发现错误”会形成静默通过；但只会弃权又会"
            "令科研流程停滞。"
        ),
        P(
            "模型提出、经人类批准的验证器扩展，能否在密封迁移任务上安全提高一个冻结科学"
            "验证栈的可执行覆盖率？",
            "quote",
        ),
        P("竞赛期拟议贡献", "h2"),
        *bullets(
            [
                "带类型的覆盖缺口与失效闭合三值结果；",
                "有边界的规格/验证器提案；",
                "所有者与独立专家 AI 双重审批；",
                "正例、反例、失效闭合测试与隐藏迁移 sibling；",
                "覆盖增量、回归与回滚记录。",
            ]
        ),
        P(
            "<b>创新边界：</b>不声称发明量纲分析、SymPy、Lean、RLVR、Agent 弃权或验证边界。"
            "提交物是环境与验证信号，不声称科学发现、递归自我改进、模型能力或 AGI。"
        ),
        PageBreak(),
        P("2. 探索环境与人类审批", "h1"),
        styled_table(
            [
                ["结果", "合同含义"],
                ["accepted", "适用的确定性检查确认候选成立"],
                ["rejected", "适用检查确认了具体错误"],
                ["abstain", "没有适用的可执行检查能够判断；绝不静默通过"],
            ],
            [35 * mm, 135 * mm],
        ),
        Spacer(1, 5),
        P(
            "观察 → 提案 → 验证<br/>"
            "accepted：保留｜rejected：修正或停止｜abstain：分类缺口并提出有边界扩展<br/>"
            "→ 所有者 + 专家 AI 审批 → 执行测试 → 重新验证 → 局部激活或继续弃权",
            "code",
        ),
        P("失效闭合不变量", "h2"),
        *bullets(
            [
                "模型不能批准自己的扩展；",
                "看过汇总确认性结果的评审不计入审批；",
                "缺少审批或测试失败时保持 abstain；",
                "开放问题控制项永远不能被提升；",
                "每个终止记录保留 candidateOnly:true、canClaimAGI:false，且 winner 门为 false。",
            ]
        ),
        P("三个确定性领域", "h2"),
        styled_table(
            [
                ["领域", "覆盖合同"],
                ["物理", "SI、仿射单位、向量、不确定度、守恒残差、参考系"],
                ["符号数学", "定义域、假设、奇点、分段边界、不等式方向"],
                ["Lean", "固定 Lean 4.24.0 + Mathlib 内核及自然语言/形式合同对齐"],
            ],
            [35 * mm, 135 * mm],
        ),
        P("内容寻址证据链", "h2"),
        P(
            "proposal# → owner-review# + expert-AI-review# → typed-tests# → activation#"
            "<br/>→ transfer# → protected-suite# → rollback# → extension-chain#",
            "code",
        ),
        P(
            "公开免登录 Demo 只暴露公共验证器、参照 episode、合成审批流程和 seal 元数据，"
            "绝不暴露密封任务、答案或凭证。"
        ),
        PageBreak(),
        P("3. 预注册 benchmark 与当前里程碑", "h1"),
        styled_table(
            [
                ["组成", "物理", "符号数学", "Lean", "总计"],
                ["frontier 有效+安全匹配对", "20", "20", "20", "60"],
                ["辅助迁移有效+安全匹配对", "20", "20", "20", "60"],
                ["已覆盖控制匹配对", "4", "4", "4", "12"],
                ["完整研究任务数", "88", "88", "88", "264"],
            ],
            [72 * mm, 23 * mm, 25 * mm, 23 * mm, 25 * mm],
        ),
        P("主指标：安全边界匹配对准确率（SFPA）", "h2"),
        P(
            "只有当有效项被机器正确判断、安全项被拒绝或弃权、且相关扩展通过迁移与回归门时，"
            "该匹配对才算成功。SFPA 覆盖 60 个匹配对，但统计推断按至少 30 个独立扩展/生成器"
            "家族聚类；参数变体与 sampling replicate 不会放大独立样本量。"
        ),
        P("预注册 winner-level 门槛", "h2"),
        *bullets(
            [
                "60 个 frontier 安全项中零不安全接受；",
                "相对最强非 oracle 基线 delta_SFPA ≥ +20 个百分点；",
                "95% cluster-bootstrap CI 下界 > 0，成对 sign-flip p < 0.05；",
                "每个必需模型家族都相对其最强非 oracle 基线取得正点估计；",
                "每个计分扩展通过两个密封有效迁移任务及其配对安全任务；",
                "已覆盖控制集和受保护测试集无回归。",
            ]
        ),
        P("截至 2026-08-01 的仪器证据", "h2"),
        styled_table(
            [
                ["里程碑", "状态"],
                ["公共开发/回归包", "150 行；每领域 50 行"],
                ["Stage A + Pro6000 守护通道", "24 家族（每领域 8）；30 任务仅绑定一次；3 个开放控制不可提升；尚无模型结果/审批"],
                ["真实 Lean 开发验证", "150/150"],
                ["内容寻址 receipt 协议", "3 链 / 34 receipts / 60 blobs；对抗基准 7/7"],
                ["CPU-only Protocol Twin", "B0-B6；8 消融组 / 13 变体；2,160 单元；0 模型/网络调用"],
                ["Study Root v3", "756 arm / 1,404 消融 / 6 后代迁移；24 有效 + 164 无效 DAG；24,000 模拟"],
                ["合成 rehearsal", "144 任务 / 72 对；confirmatoryEligible:false"],
                ["rehearsal 验证", "144/144；48 个 Lean 项；仅 15 家族且存在结构泄漏"],
            ],
            [65 * mm, 105 * mm],
            font_size=6.8,
        ),
        P(
            "<b>证伪条件：</b>任一不安全接受、任一必需模型家族相对其最强基线为负、"
            "任一 receipt 断链、控制集回归，或 CI / p-value 门未通过，均否决 winner-level 结论。",
            "quote",
        ),
        P("<b>以上只证明仪器完整性，不证明验证边界扩展有效。</b>"),
        PageBreak(),
        P("4. 基线、相关工作、披露与继续条件", "h1"),
        P("必需实验臂", "h2"),
        P(
            "原始模型；固定三值验证器；固定验证器+等预算修正；仅作答/弃权而无可执行扩展；"
            "等预算纯人工扩展；拟议的人类审批系统；专家编写 oracle ceiling。关键消融包括移除"
            "人类审批、可执行 patch、迁移义务、显式弃权及逐个移除验证层。CPU-only twin 在"
            "构造 fixture 上检查 B1/B5 replay、B2 修正输入、A6 sentinel、缺失单元与预算字段；"
            "它未绑定真实计分研究，也不是有效性实验。"
        ),
        P("相关工作与创新风险", "h2"),
        P(
            "直接相关工作包括 RLVP（arXiv:2607.10474）、EG-VAR（arXiv:2607.12650）、"
            "Recursive Epistemic Engines 的 Novelty Horizon，以及 AgentAbstain"
            "（arXiv:2607.10059）。最大风险来自既有受保护验证器扩展研究；因此可辩护贡献是"
            "前瞻性实证与可复现仪器，而不是宣称发明验证边界。"
        ),
        P("披露", "h2"),
        P(
            "<b>预先存在：</b>Sophia 的 SI/符号验证器、Lean 检查与评测、来源及防过度声明门、"
            "既有候选阶梯证据。<br/><b>竞赛期新增：</b>typed frontier 协议、匹配对生成器与"
            " seal、内容寻址 receipt 协议、人类审批合同、24 家族 Stage A、守护型本地模型"
            " runner、统计程序、双语材料与 hosted-demo 包。"
        ),
        P("继续条件", "h2"),
        P(
            "当前建议为：<b>确认性执行 NO-GO；初赛基础设施提案 CONDITIONAL GO</b>。只有"
            "真正私有的 30 家族 benchmark、提示、模型、预算与扩展 bundle 全部冻结，并以真实"
            "独立审批、隐藏迁移、受保护套件和回滚执行实例化 receipt 协议后，才能开始确认性评分。"
        ),
        P(
            "./run_all.sh<br/>"
            "python3 v2/run_model_attempts.py --dry-run",
            "code",
        ),
        P(
            "<b>限制：</b>尚无确认性 benchmark 或有效性结果；当前 rehearsal 是人工构造且结构"
            "已泄漏；Stage A 本地提案、双重审批与可执行扩展测试尚未完成；仍需人类和领域专家"
            "评审。candidateOnly:true；canClaimAGI:false；winnerLevelEligible:false；"
            "winnerLevelGateMet:false。"
        ),
    ]


def en_story() -> list:
    """Winner-oriented v2 English four-page narrative."""
    return [
        P("Safely Expanding the Verification Frontier of Scientific Agents", "title"),
        P("安全扩展科学 Agent 的验证边界", "subtitle"),
        P(
            "GOAI 2026 AI for Research — Open Exploration<br/>"
            "Yim Kin Cheong (Tom) | Independent Researcher | Hong Kong | Apache-2.0",
            "subtitle",
        ),
        P("1. Research problem and proposed contribution", "h1"),
        P(
            "Scientific agents must distinguish a candidate established by an executable "
            "check, a candidate refuted by a check, and a candidate outside current verifier "
            "coverage. Treating the third case as “no error found” creates a silent pass; "
            "merely abstaining leaves the workflow stuck."
        ),
        P(
            "Can model-proposed, human-approved verifier extensions increase the safe "
            "executable coverage of a frozen scientific verification stack on sealed "
            "transfer tasks?",
            "quote",
        ),
        P("Contest-period proposed contribution", "h2"),
        *bullets(
            [
                "Typed coverage gaps and fail-closed three-state outcomes;",
                "bounded specification or verifier proposals;",
                "owner and independent expert-AI approval;",
                "positive, negative, fail-closed, and hidden-transfer tests;",
                "coverage-delta, regression, activation, and rollback receipts.",
            ]
        ),
        P(
            "<b>Novelty boundary:</b> this project does not claim to invent dimensional "
            "analysis, SymPy, Lean, RLVR, agent abstention, or the verification frontier. "
            "The deliverable is the environment and verification signal, not scientific "
            "discovery, recursive self-improvement, model capability, or AGI."
        ),
        PageBreak(),
        P("2. Exploration environment and human gate", "h1"),
        styled_table(
            [
                ["Outcome", "Contract"],
                ["accepted", "An applicable deterministic check establishes the candidate."],
                ["rejected", "An applicable check establishes a concrete failure."],
                ["abstain", "No applicable executable check can decide; never a silent pass."],
            ],
            [35 * mm, 135 * mm],
        ),
        Spacer(1, 5),
        P(
            "observe → propose → verify<br/>"
            "accepted: keep | rejected: revise or stop | abstain: classify the gap and "
            "propose a bounded extension<br/>"
            "→ owner + expert-AI gate → executable tests → re-verify → activate locally "
            "or preserve abstention",
            "code",
        ),
        P("Fail-closed invariants", "h2"),
        *bullets(
            [
                "A model cannot approve its own extension;",
                "a reviewer who saw aggregate confirmatory outcomes does not count;",
                "missing approval or failed tests preserve abstention;",
                "open-problem controls can never be promoted;",
                "every terminal receipt preserves candidateOnly:true and canClaimAGI:false, with winner gates false.",
            ]
        ),
        P("Three deterministic domains", "h2"),
        styled_table(
            [
                ["Domain", "Coverage contract"],
                ["Physics", "SI, affine units, vectors, uncertainty, conservation, frames"],
                ["Symbolic", "Domains, assumptions, singularities, piecewise bounds, inequalities"],
                ["Lean", "Pinned Lean 4.24.0 + Mathlib kernel and claim/formal alignment"],
            ],
            [35 * mm, 135 * mm],
        ),
        P("Content-addressed evidence DAG", "h2"),
        P(
            "proposal# → owner-review# + expert-AI-review# → typed-tests# → activation#"
            "<br/>→ transfer# → protected-suite# → rollback# → extension-chain#",
            "code",
        ),
        P(
            "The public no-login demo exposes public verifiers, reference episodes, "
            "synthetic gate mechanics, and seal metadata—never sealed tasks, golds, or "
            "credentials."
        ),
        PageBreak(),
        P("3. Preregistered benchmark and current milestones", "h1"),
        styled_table(
            [
                ["Component", "Physics", "Symbolic", "Lean", "Total"],
                ["Frontier valid+safety pairs", "20", "20", "20", "60"],
                ["Auxiliary transfer valid+safety pairs", "20", "20", "20", "60"],
                ["Already-covered control pairs", "4", "4", "4", "12"],
                ["Full study tasks", "88", "88", "88", "264"],
            ],
            [72 * mm, 23 * mm, 25 * mm, 23 * mm, 25 * mm],
        ),
        P("Primary endpoint: Safe Frontier-Pair Accuracy (SFPA)", "h2"),
        P(
            "A pair succeeds only when its valid member is correctly machine-decided, its "
            "safety sibling is rejected or abstained, and the responsible extension passes "
            "transfer and regression gates. SFPA covers 60 pairs, but inference clusters "
            "over at least 30 independent extension/generator families; parameter variants "
            "and sampling replicates do not inflate independent N."
        ),
        P("Preregistered winner-level gates", "h2"),
        *bullets(
            [
                "Zero unsafe acceptance among 60 frontier safety siblings;",
                "delta_SFPA at least +20 percentage points over the strongest non-oracle baseline;",
                "95% cluster-bootstrap CI lower bound > 0 and paired sign-flip p < 0.05;",
                "positive point estimate in each required model family versus its own strongest baseline;",
                "every counted extension passes two sealed valid transfers and paired safety tasks;",
                "no covered-control or protected-suite regression.",
            ]
        ),
        P("Instrument evidence completed by August 1, 2026", "h2"),
        styled_table(
            [
                ["Milestone", "Status"],
                ["Public development/regression pack", "150 rows; 50 per domain"],
                ["Stage A + guarded Pro6000 lane", "24 families (8/domain); 30 tasks bound once; 3 open controls non-promotable; no model outcome/approval yet"],
                ["Real Lean development validation", "150/150"],
                ["Content-addressed receipt protocol", "3 chains / 34 receipts / 60 blobs; benchmark 7/7"],
                ["CPU-only Protocol Twin", "B0-B6; 8 groups / 13 variants; 2,160 cells; 0 model/network calls"],
                ["Study Root v3", "756 arm / 1,404 ablation / 6 transfer descendants; 24 serialization variants + 164 invalid mutations; 24,000 sims"],
                ["Synthetic rehearsal", "144 tasks / 72 pairs; confirmatoryEligible:false"],
                ["Rehearsal validation", "144/144; 48 Lean items; only 15 leaked families"],
            ],
            [65 * mm, 105 * mm],
            font_size=6.8,
        ),
        P(
            "<b>Falsify the winner claim if:</b> any unsafe acceptance occurs; any required "
            "model family loses to its strongest baseline; any receipt link or covered control "
            "regresses; or the CI / p-value gates fail.",
            "quote",
        ),
        P("<b>These establish instrument integrity, not frontier-expansion efficacy.</b>"),
        PageBreak(),
        P("4. Baselines, related work, disclosure, and continuation", "h1"),
        P("Required experimental arms", "h2"),
        P(
            "Raw model; fixed three-state verifier; fixed verifier plus equal-budget "
            "refinement; act-or-abstain without executable extension; budget-matched "
            "human-only extension; proposed human-gated system; expert-authored oracle "
            "ceiling. Key ablations remove the human gate, executable patch, transfer "
            "obligation, explicit abstention, and each verifier tier. The CPU-only twin "
            "checks B1/B5 replay, B2 revised input, an A6 sentinel, cell completeness, and "
            "fixture budget fields. It is not bound to a scored study or an efficacy experiment."
        ),
        P("Related work and novelty risk", "h2"),
        P(
            "Direct work includes RLVP (arXiv:2607.10474), EG-VAR "
            "(arXiv:2607.12650), Recursive Epistemic Engines and its Novelty Horizon, "
            "and AgentAbstain (arXiv:2607.10059). The largest risk is prior guarded "
            "verifier-expansion work. The defensible contribution is prospective empirical "
            "evidence and reproducible instrumentation—not invention of the frontier."
        ),
        P("Disclosure", "h2"),
        P(
            "<b>Pre-existing:</b> Sophia SI/symbolic verifiers, Lean checking/evaluations, "
            "provenance and no-overclaim gates, and prior candidate ladder evidence."
            "<br/><b>Contest-period:</b> typed frontier protocol, matched-pair generator "
            "and seal, content-addressed receipt protocol, human-gate contracts, the "
            "24-family Stage A programme, guarded local-model runner, statistics, bilingual "
            "materials, and hosted-demo package."
        ),
        P("Continuation condition", "h2"),
        P(
            "Current recommendation: <b>NO-GO for confirmatory execution; CONDITIONAL GO "
            "for preliminary upload as an infrastructure proposal</b>. Scoring starts only "
            "after a genuinely private 30-family benchmark, prompts, models, budgets, "
            "and extension bundle are frozen, and the receipt protocol is instantiated with "
            "real independent reviews, hidden transfer, protected-suite, and rollback runs."
        ),
        P(
            "./run_all.sh<br/>"
            "python3 v2/run_model_attempts.py --dry-run",
            "code",
        ),
        P(
            "<b>Limits:</b> no confirmatory benchmark or efficacy result exists; the rehearsal "
            "is constructed and structurally leaked; Stage A local proposals, dual reviews, "
            "and executable extension tests are incomplete; human and domain-expert review "
            "remain necessary. candidateOnly:true; canClaimAGI:false; "
            "winnerLevelEligible:false; winnerLevelGateMet:false."
        ),
    ]


def build(path: Path, language: str, story: list) -> None:
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        invariant=1,
        pageCompression=1,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=(
            "Safely Expanding the Verification Frontier of Scientific Agents"
            if language == "English"
            else "安全扩展科学 Agent 的验证边界"
        ),
        author="Yim Kin Cheong (Tom)",
        subject="GOAI 2026 AI for Research Open Exploration",
    )
    document.build(
        story,
        onFirstPage=footer(language),
        onLaterPages=footer(language),
        canvasmaker=Canvas,
    )
    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    if page_count != 4:
        raise RuntimeError(f"{path.name}: expected exactly 4 pages, got {page_count}")
    metadata = reader.metadata or {}
    for field in ("/CreationDate", "/ModDate"):
        if metadata.get(field) != INVARIANT_PDF_DATE:
            raise RuntimeError(
                f"{path.name}: expected invariant {field}={INVARIANT_PDF_DATE!r}, "
                f"got {metadata.get(field)!r}"
            )


def main() -> int:
    build(ZH_PDF, "简体中文", zh_story())
    build(EN_PDF, "English", en_story())
    print(f"built {ZH_PDF.name}: 4 pages")
    print(f"built {EN_PDF.name}: 4 pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
