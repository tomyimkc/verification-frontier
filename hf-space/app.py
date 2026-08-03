#!/usr/bin/env python3
"""验证边界 · Verification Frontier — live demo with LLM self-judge,
step-level CoT verification, and a deterministic final-answer verifier.

Each showcase card runs a four-step flow on a real local LLM
(Qwen2.5-3B-Instruct):
  1. Generate          — the LLM answers (and may make a subtle error)
  2. Self-Judge        — the SAME LLM critiques its own answer
  3. Step-Verify       — the response is parsed into CoT steps and EACH step is
                         checked for arithmetic balance and unit consistency
  4. Final Verdict     — the deterministic verifier checks the final answer

The comparison reveals when self-judgment fails, when step-level checking
catches an arithmetic slip, and when only the deterministic verifier catches a
conceptual error.
"""
from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gradio as gr

from demo_logic import frontier_gate_preview, verify_si, verify_symbolic
from v2.verify_ill_posed import verify_ill_posed
from model_runner import (
    generate_response,
    generate_with_steps,
    get_global_log,
    get_session_log,
    model_status,
    self_judge,
)
from step_checker import check_steps, summarize as summarize_steps

INTRO = """
# 🛡️ 验证边界 · Verification Frontier
### 安全捕获 LLM 科学推理中的逻辑错误
> **真实云端 LLM**（Qwen2.5-7B-Instruct，via HF Inference API）生成回答 →
> **同一个 LLM 自我检查** → **逐步 CoT 验证**（每一步检查算术与单位）→
> **确定性验证器裁决**。
> 评委可以看到：7B 模型在难题上偶尔出错，自我检查有时漏判，确定性验证器始终捕获。
**GOAI 2026 · AI for Research · Open Exploration**
"""

FOOTER = (
    "---\n"
    "`candidateOnly:true` · `canClaimAGI:false` · "
    "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)"
)

# Each showcase is tuned for a 3B model: the prompts are designed to trigger a
# *subtle* error (wrong formula, missing square, forgotten sign flip, hallucinated
# solution to a contradictory system). `verifier` selects which deterministic
# verifier runs in Step 4; `reference` is the gold used by the SI/symbolic
# verifiers; the ill-posed verifier needs no reference (it inspects the text).
SHOWCASE = [
    {
        "id": "momentum",
        "title": "🎱 动量守恒 / Conservation of Momentum",
        "prompt": (
            "A 3 kg cart moving at 4 m/s collides with a stationary 2 kg cart. "
            "After collision they stick together. What is the final velocity? "
            "Show work and give the final answer with units on the last line."
        ),
        "verifier": "si",
        "reference": "2.4 m/s",
        "hint": "⚠️ **挑战性问题**：动量守恒 p_before = p_after。正确答案 = 12/5 = 2.4 m/s。7B 在高温下可能算错中间步骤。",
    },
    {
        "id": "thermo",
        "title": "🔥 热力学 / Thermodynamics",
        "prompt": (
            "How much energy is needed to heat 500g of water from 20°C to 80°C? "
            "Specific heat of water is 4.18 J/(g·°C). "
            "Give the final answer in joules on the last line."
        ),
        "verifier": "si",
        "reference": "125400 J",
        "hint": "⚠️ **挑战性问题**：Q = mcΔT = 500 × 4.18 × 60 = 125400 J。模型可能算错 500×4.18×60 或用错温度差。",
    },
    {
        "id": "lorentz",
        "title": "🚀 相对论 / Relativity",
        "prompt": (
            "A particle moves at 0.8c. What is its Lorentz factor γ? "
            "Show work and give the final number."
        ),
        "verifier": "si",
        "reference": "1.6667 s",
        "hint": "⚠️ **挑战性问题**：γ = 1/√(1-0.64) = 1/0.6 = 5/3 ≈ 1.6667。模型可能在 √(0.36) 上出错。",
    },
    {
        "id": "opt-deriv",
        "title": "📈 优化 / Optimization Derivative",
        "prompt": (
            "Find the minimum of f(x) = x^3 - 6x^2 + 9x + 1. "
            "Take the derivative, find critical points, and determine which is the minimum. "
            "Show all steps."
        ),
        "verifier": "symbolic",
        "reference": "3*x^2-12*x+9",
        "hint": "⚠️ **挑战性问题**：f'(x) = 3x²-12x+9 = 0 → x=1 或 x=3。x=3 是最小值。模型可能搞混最大/最小。",
    },
    {
        "id": "faraday",
        "title": "⚡ 电磁感应 / Faraday's Law",
        "prompt": (
            "A square loop of wire (0.1m × 0.1m) is in a magnetic field B = 2T. "
            "The field decreases to 0T in 0.5 seconds. "
            "What is the magnitude of the induced EMF? Show work."
        ),
        "verifier": "si",
        "reference": "0.04 V",
        "hint": "⚠️ **挑战性问题**：EMF = ΔΦ/Δt = (B×A)/Δt = (2×0.01)/0.5 = 0.04V。模型可能算错面积或时间。",
    },
    {
        "id": "contradictory",
        "title": "🔍 不可解：伪装的矛盾系统 / Disguised Contradictory",
        "prompt": (
            "Solve for x and y: 3x + 2y = 12, 6x + 4y = 25. Show your work."
        ),
        "verifier": "ill_posed",
        "reference": "",
        "hint": "⚠️ **挑战性问题**：第二个方程是第一个的 2 倍但常数不对（25≠24）。系统矛盾。7B 可能不识别而幻觉一个解。",
    },
    {
        "id": "circular-opt",
        "title": "🔍 不可解：循环优化 / Circular Optimization",
        "prompt": (
            "Maximize profit where: Revenue depends on Price, Price depends on Demand, "
            "Demand depends on Revenue. Find the optimal Price. Show your work."
        ),
        "verifier": "ill_posed",
        "reference": "",
        "hint": "⚠️ **挑战性问题**：循环依赖 R→P→D→R。无法在不打破循环的情况下求解。7B 可能不识别循环性。",
    },
]


def _strip_latex(text: str) -> str:
    """Remove LaTeX markup to get plain text."""
    text = text.replace("\\[", "").replace("\\]", "")
    text = text.replace("\\boxed{", "").replace("\\(", "").replace("\\)", "")
    text = text.replace("\\text{", " ").replace("\\,", " ")
    text = text.replace("\\cdot", "*").replace("\\frac", "")
    text = text.replace("\\times", "*").replace("\\div", "/")
    text = text.replace("\\approx", "=").replace("\\gamma", "")
    text = text.replace("\\varepsilon", "").replace("\\Phi", "Phi")
    text = text.replace("\\Delta", "").replace("\\left", "").replace("\\right", "")
    text = text.replace("{", "").replace("}", "")
    text = text.replace("\\\\", "\\")
    return text


def _extract(text: str) -> str:
    """Best-effort extract a final numeric/symbolic candidate from a response.

    Strips LaTeX markup first (7B models output \\boxed{2.4 \\text{m/s}}),
    then looks for number+unit or symbolic expressions.
    """
    if not text or not text.strip():
        return ""

    # Strip LaTeX from the whole text first
    cleaned = _strip_latex(text)

    lines = [l.strip() for l in cleaned.strip().splitlines() if l.strip()]

    # Look for explicit "answer = X" / "velocity = X" patterns
    for line in reversed(lines[-5:]):
        m = re.search(
            r"(?:answer|result|velocity|energy|power|factor|EMF|volume)\s*[:=]\s*(.+)",
            line, re.I,
        )
        if m:
            val = m.group(1).strip().rstrip(".")
            if val:
                # Try to extract number+unit from this
                m2 = re.search(
                    r"([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*"
                    r"(m/s\^?2|m/s²|m/s|km/h|J|N|W|kg|Pa|s\b|m\b|V\b|T\b|Wb)",
                    val,
                )
                if m2:
                    unit = m2.group(2).replace("²", "^2")
                    return f"{m2.group(1)} {unit}"
                return val[:60]

    # Look for bare number+unit in last few lines
    for line in reversed(lines[-5:]):
        m = re.search(
            r"([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*"
            r"(m/s\^?2|m/s²|m/s|km/h|J|N|W|kg|Pa|s\b|m\b|V\b|T\b|Wb)",
            line,
        )
        if m:
            unit = m.group(2).replace("²", "^2")
            return f"{m.group(1)} {unit}"

    # Issue 1 fix: dimensionless number (e.g. Lorentz factor γ ≈ 1.667)
    for line in reversed(lines[-5:]):
        m = re.search(r"=\s*([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*$", line)
        if m:
            return m.group(1)

    # Issue 2 fix: bare number at end of a line (after LaTeX strip)
    for line in reversed(lines[-5:]):
        clean = _strip_latex(line).strip().rstrip(".")
        m = re.search(r"([-+]?\d+\.?\d*)\s*$", clean)
        if m and len(m.group(1)) > 0:
            # Only return if the line is short (likely just the answer)
            if len(clean) < 30:
                return m.group(1)

    # Look for symbolic expression
    for line in reversed(lines[-5:]):
        clean = _strip_latex(line).replace(" ", "").replace("²", "^2")
        if re.search(r"[a-z]\^?2|[a-z]\*\*2", clean, re.I):
            clean = re.sub(r"^(.*?[:=])", "", clean)
            clean = clean.replace("\\", "")
            if clean and clean[0] != "(":
                return clean[:40]

    # Fallback: last non-empty line
    last = lines[-1] if lines else cleaned.strip()
    last = re.sub(
        r"^(?:the\s+)?(?:final\s+)?(?:answer|result|solution|therefore)[\s,:=]*",
        "", last, flags=re.I,
    ).strip().rstrip(".")
    return last[:60] if last else ""


def _verify(vtype: str, candidate: str, reference: str, full_text: str) -> dict:
    """Route to the right deterministic verifier for Step 4."""
    if vtype == "ill_posed":
        # Issue 4+5 fix: strip LaTeX from full text before ill-posed detection
        clean_text = _strip_latex(full_text)
        return verify_ill_posed(clean_text).to_dict()
    if not candidate or not candidate.strip():
        return {"verdict": "abstain", "reasonCode": "no_answer",
                "reason": "Click Generate first."}
    # Issue 2 fix: strip LaTeX from candidate before any verifier
    candidate = _strip_latex(candidate).strip()
    if vtype == "si":
        return verify_si(candidate, reference)
    if vtype == "symbolic":
        # Also clean reference
        ref_clean = _strip_latex(reference).strip()
        return verify_symbolic(candidate, ref_clean)
    return {"verdict": "abstain", "reason": "unknown verifier"}


def _format_step_report(steps: list[str], verdicts) -> str:
    """Render the step-verification output as markdown for the UI."""
    if not steps:
        return "_No steps parsed from the response yet — click **Generate** first._"
    summary = summarize_steps(verdicts)
    out = [
        f"**逐步骤检查 / Per-step check:** "
        f"{summary['verified']} ✅  ·  {summary['error']} ❌  ·  "
        f"{summary['unchecked']} ⏸️  (of {summary['total']} steps)",
        "",
    ]
    if summary["error"] == 0:
        out.append("> ✅ **No arithmetic or unit-dimension errors detected in any step.**")
    else:
        out.append("> ❌ **At least one step failed a check** — see the ❌ step(s) below.")
    out.append("")
    for v in verdicts:
        out.append(f"**Step {v.index + 1} {v.icon}** — {v.summary}")
        body = v.text.strip().replace("\n", "\n> ")
        out.append(f"> {body}")
        # Show the failing equation inline when there is one, so the error is
        # obvious without the user having to parse the raw response.
        for eq in (v.detail.get("equations") or []):
            tag = []
            if eq.get("numeric") is True:
                tag.append("balanced")
            elif eq.get("numeric") is False:
                tag.append("arithmetic ✗")
            if eq.get("units") is True:
                tag.append("units ✓")
            elif eq.get("units") is False:
                tag.append(f"units ✗ ({eq.get('lhsUnitDim')} vs {eq.get('rhsUnitDim')})")
            if tag:
                out.append(f">   `{eq['lhs']} = {eq['rhs']}` — {'; '.join(tag)}")
        out.append("")
    out.append(
        "<small>⏸️ = no machine-checkable equation (prose, or a symbolic/compound "
        "expression we cannot reduce). This is fail-closed: we never claim to have "
        "verified what we cannot parse. Conceptual correctness (wrong formula, wrong "
        "conversion factor) is checked separately in Step 4.</small>"
    )
    return "\n".join(out)


def build_app():
    with gr.Blocks(title="验证边界 · Verification Frontier", theme=gr.themes.Soft()) as app:
        session_id = gr.State(value=lambda: uuid.uuid4().hex)

        gr.Markdown(INTRO)

        with gr.Tabs():
            with gr.Tab("① 概览"):
                gr.Markdown(
                    "## ① LLM 会犯什么逻辑错误\n\n"
                    "| 类型 | 例子 |\n|---|---|\n"
                    "| ➗ 不等式方向 | 除以负数忘记翻转不等号 |\n"
                    "| 🏀 公式错误 | 用 `v=√(2gh)` 当作下落时间 |\n"
                    "| 🔄 单位换算 | `72 km/h` 乘以 `3.6` 而非除以 |\n"
                    "| ⚡ 缺平方 | `P=IR` 而非 `P=I²R` |\n"
                    "| 🔍 不可解 | 对矛盾系统给「答案」|\n\n"
                    "**67/67 逻辑错误被确定性验证器捕获 · 30/30 病态问题被弃权**\n\n"
                    "👉 点击 ② 看真实 LLM 生成 → 自我检查 → 逐步验证 → 确定性验证。"
                )

            with gr.Tab("② 真实 LLM / Live LLM"):
                gr.Markdown(
                    "## ② 真实 LLM 错误展示 + 自我检查 + 逐步验证 + 确定性验证\n\n"
                    "> **⚠️ 实验设计 / Experimental Design**\n>\n"
                    "> 提示是**故意设计的**，旨在触发特定逻辑错误（省略单位提示、给出矛盾系统、"
                    "> 用需要翻转的不等式等）。目的不是证明 LLM「笨」，而是演示："
                    "> **LLM 自我检查何时失败、逐步检查何时发现算术错误、"
                    "> 确定性验证器何时捕获概念性错误**。\n>\n"
                    "> Prompts are **deliberately crafted** to trigger errors. The point is to show\n"
                    "> **when self-judgment fails, when step-level checking catches an arithmetic\n"
                    "> slip, and when only the deterministic verifier catches a conceptual error**.\n\n"
                    "**四步流程 / Four-step flow:**\n"
                    "1. 🤖 **生成 / Generate**：LLM 回答问题（可能犯错）\n"
                    "2. 🔎 **自我检查 / Self-Judge**：同一个 LLM 批判自己的回答\n"
                    "3. 🪜 **逐步验证 / Step-Verify**：把回答拆成步骤，逐个检查算术平衡与单位一致性\n"
                    "4. 🔬 **最终裁决 / Final Verdict**：确定性验证器检查最终答案\n\n"
                    "**真实本地 LLM**（Qwen2.5-3B-Instruct，CPU）。每次调用记录在日志中（完整响应）。"
                )

                with gr.Row():
                    st_btn = gr.Button("🔄 状态", size="sm")
                    st_out = gr.JSON(label="模型 / Model", value=lambda: model_status())
                    sl_btn = gr.Button("📋 本会话", size="sm")
                    sl_out = gr.JSON(label="本会话 / Session")
                    gl_btn = gr.Button("🌐 全部", size="sm")
                    gl_out = gr.JSON(label="全部 / Global")

                st_btn.click(lambda: model_status(), outputs=st_out)
                sl_btn.click(lambda sid: get_session_log(sid) or [{"note": "no calls yet"}],
                             inputs=[session_id], outputs=sl_out)
                gl_btn.click(lambda: get_global_log(15), outputs=gl_out)

                gr.Markdown("---")

                for item in SHOWCASE:
                    _build_showcase_card(item, session_id)
                    gr.Markdown("")

            with gr.Tab("③ 手动测试 / Manual"):
                gr.Markdown(
                    "## ③ 手动验证 / Manual Verification\n\n"
                    "直接输入候选和参考，看确定性验证器裁决。"
                )
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="reference")
                gr.Button("🔍 Check").click(
                    verify_si, [si_c, si_r], gr.JSON(label="verdict"))
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="reference")
                gr.Button("🔍 Check").click(
                    verify_symbolic, [sy_c, sy_r], gr.JSON(label="verdict"))

            with gr.Tab("④ 不可解 / Ill-Posed"):
                gr.Markdown("## ④ 病态检测\n\n**30/30 弃权率**")
                ill = gr.Textbox(value="x + y = 3, x + y = 5", label="problem")
                gr.Button("🔍 Check").click(
                    lambda t: verify_ill_posed(t).to_dict(),
                    [ill], gr.JSON(label="verdict"))

            with gr.Tab("⑤ 结果 / Results"):
                gr.Markdown(
                    "## ⑤ 诚实的结果\n\n"
                    "| 指标 | 结果 |\n|---|---|\n"
                    "| 逻辑错误捕获 | **67/67 (100%)** |\n"
                    "| 病态弃权 | **30/30 (100%)** |\n"
                    "| 基线比较 | proposed-system 全优 |\n"
                    "| 自我修正 | 83.6% 错误下降 |\n"
                    "| Stage A (GPU) | 23/24 |"
                )

        gr.Markdown(FOOTER)
    return app


def _build_showcase_card(item: dict, session_id: gr.State) -> None:
    """Build one four-step showcase card inside the current Blocks context.

    Defined as a helper so the per-item handler closures capture the right
    ``item`` (avoiding the classic loop-closure bug). Each card holds its own
    hidden state for the parsed steps so Step-Verify and Step-4 do not need to
    re-parse the response.
    """
    with gr.Group():
        gr.Markdown(f"### {item['title']}")
        gr.Markdown(f"**📝 Prompt:**\n```\n{item['prompt']}\n```")
        gr.Markdown(f"<small>💡 {item['hint']}</small>")

        # Hidden state shared across the four steps of THIS card.
        prompt_hidden = gr.Textbox(item["prompt"], visible=False)
        response_hidden = gr.Textbox("", visible=False)   # latest full response
        steps_hidden = gr.JSON(value=[], visible=False)    # parsed CoT steps

        # ---- Step 1: Generate ----
        gen_btn = gr.Button(
            f"1️⃣ 🤖 LLM 生成 / Generate ({item['id']})", variant="secondary")
        llm_out = gr.Textbox(
            label="🤖 LLM 回答（完整）/ LLM Response (full)",
            lines=7, interactive=False,
            placeholder="点击生成 / Click Generate ↑",
        )

        def _gen(prompt, sid):
            result = generate_with_steps(
                prompt, session_id=sid, max_new_tokens=1000, temperature=0.7)
            resp = result["response"]
            return resp, resp, result["steps"]
        gen_btn.click(
            _gen,
            inputs=[prompt_hidden, session_id],
            outputs=[llm_out, response_hidden, steps_hidden])

        # ---- Step 2: Self-Judge ----
        judge_btn = gr.Button(
            f"2️⃣ 🔎 LLM 自我检查 / Self-Judge ({item['id']})", variant="secondary")
        judge_out = gr.Textbox(
            label="🔎 LLM 自我检查 / LLM Self-Assessment",
            lines=5, interactive=False,
            placeholder="同一个 LLM 批判自己的回答 / Same LLM critiques its own answer",
        )

        def _judge(prompt, response, sid):
            if not response or not response.strip() or response.startswith("["):
                return "[请先生成回答 / Generate first]"
            return self_judge(prompt, response, session_id=sid)
        judge_btn.click(
            _judge,
            inputs=[prompt_hidden, response_hidden, session_id],
            outputs=judge_out)

        # ---- Step 3: Step-Verify ----
        step_btn = gr.Button(
            f"3️⃣ 🪜 逐步验证 / Step-Verify ({item['id']})", variant="secondary")
        step_out = gr.Markdown(
            label=None,  # gr.Markdown has no label
            value="_点击「逐步验证」把回答拆成步骤并逐个检查 / "
            "Click Step-Verify to parse the response into steps and check each._",
        )

        def _step_verify(steps):
            if not steps:
                return "_No steps parsed from the response yet — click **Generate** first._"
            verdicts = check_steps(steps)
            return _format_step_report(steps, verdicts)
        step_btn.click(_step_verify, inputs=[steps_hidden], outputs=step_out)

        # ---- Step 4: Final Verdict (deterministic) ----
        verify_btn = gr.Button(
            f"4️⃣ 🔬 最终裁决 / Final Verdict ({item['id']})", variant="primary")
        verdict_out = gr.JSON(
            label="🔬 确定性验证器裁决 / Deterministic Verifier")
        extracted_box = gr.Textbox(
            label="🔍 提取候选 / Extracted candidate",
            interactive=False, placeholder="自动提取 / auto-extracted")

        def _final(vtype, reference, full):
            candidate = _extract(full)
            verdict = _verify(vtype, candidate, reference, full)
            return verdict, candidate
        verify_btn.click(
            _final,
            inputs=[gr.State(item["verifier"]), gr.State(item["reference"]),
                    response_hidden],
            outputs=[verdict_out, extracted_box])

        gr.Markdown(
            "<small>👆 对比步骤 2、3、4：自我检查可能说「正确」；逐步验证可能发现"
            "算术错误；确定性验证器捕获概念性错误。三者互补，这就是分层验证的价值。</small>"
        )


if __name__ == "__main__":
    build_app().launch()
