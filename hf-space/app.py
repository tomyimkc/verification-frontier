#!/usr/bin/env python3
"""验证边界 · Verification Frontier — live local-LLM error demo.

The showcase tab runs a real LLM (Qwen2.5-0.5B-Instruct, local CPU) that makes
actual errors. The judge sees the prompt, the model's real response, and the
deterministic verifier's verdict — all live, no API cost.

Bilingual (中文 + EN).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gradio as gr

from demo_logic import (
    frontier_gate_preview,
    verify_si,
    verify_symbolic,
)
from v2.verify_ill_posed import verify_ill_posed
from model_runner import generate_response, model_status

INTRO = """
# 🛡️ 验证边界 · Verification Frontier

### 安全捕获 LLM 科学推理中的逻辑错误 / Safely Catching Logic Errors in LLM Scientific Reasoning

> **LLM 是概率黑盒，会犯逻辑错误。** 这个 Demo 运行一个**真实的本地 LLM**
> (Qwen2.5-0.5B)，让评委亲眼看到模型犯错，再看确定性验证器如何捕获。
>
> **LLMs are probabilistic black boxes.** This demo runs a **real local LLM**
> so judges can see the model make errors, then watch the deterministic verifier catch them.

**GOAI 2026 · AI for Research · Open Exploration**

👇 点击「② 真实 LLM 错误」看模型实时犯错。 / Click Tab ② to see the model make errors live.
"""

FOOTER = (
    "---\n"
    '<div align="center">\n\n'
    "**声明边界 / Claim ceiling:**\n"
    "`candidateOnly: true` · `canClaimAGI: false`\n\n"
    "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)\n\n"
    "</div>"
)

# ── Showcase prompts: designed to trigger each error type from a small model ──

SHOWCASE_PROMPTS = [
    {
        "id": "dim-velocity",
        "title": "🔢 量纲错误：加速度 vs 速度 / Dimension: acceleration vs velocity",
        "prompt": "A ball is dropped from rest. After 1 second under gravity (g = 9.8 m/s^2), what is its final velocity? Answer in one sentence with units.",
        "verifier": "si",
        "reference": "9.8 m/s",
        "note": "小模型经常输出 `9.8 m/s²`（加速度单位）而非 `9.8 m/s`（速度单位）。看模型怎么回答！",
    },
    {
        "id": "dim-energy",
        "title": "🔢 量纲错误：力 vs 能量 / Dimension: force vs energy",
        "prompt": "A 2 kg object moves at 3 m/s. What is its kinetic energy? Answer in one sentence with units.",
        "verifier": "si",
        "reference": "9 J",
        "note": "模型可能输出 `N`（力）而非 `J`（能量）。正确答案是 ½×2×3² = 9 J。",
    },
    {
        "id": "sym-expand",
        "title": "➕ 符号/等价错误 / Sign or equivalence error",
        "prompt": "Expand (x+1)^2. Show the expansion.",
        "verifier": "symbolic",
        "reference": "(x+1)^2",
        "note": "模型可能写错展开式——漏项、符号翻转、或多个常数。正确答案 x²+2x+1。",
    },
    {
        "id": "ill-contradictory",
        "title": "🔍 不可解：矛盾方程组 / Ill-posed: contradictory system",
        "prompt": "Solve the system: x + y = 3, x + y = 5. Show your work.",
        "verifier": "ill_posed",
        "reference": "",
        "note": "这个系统矛盾——x+y 不可能同时等于 3 和 5。模型可能幻觉出一个「答案」。验证器应该弃权。",
    },
    {
        "id": "ill-circular",
        "title": "🔍 不可解：循环依赖 / Ill-posed: circular dependency",
        "prompt": "A depends on B. B depends on A. Find the value of A. Show your work.",
        "verifier": "ill_posed",
        "reference": "",
        "note": "循环依赖无法求解。模型可能编造一个答案。验证器应该检测循环并弃权。",
    },
]


def _extract_answer(text: str) -> str:
    """Crude answer extraction from model output — grab the last line or a number+unit."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return text.strip()[:50]
    # Try to find a line with a numeric answer
    import re
    for line in reversed(lines):
        # Look for "X.X unit" pattern
        m = re.search(r"([-+]?\d+\.?\d*)\s*(m/s\^?2|m/s|J|N|kg|W|Pa)", line)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        # Look for x^2 pattern
        if "x^2" in line or "x²" in line:
            return line.replace(" ", "")[:30]
    return lines[-1][:50]


def _run_verifier(verifier_type: str, candidate: str, reference: str):
    """Run the appropriate verifier."""
    if verifier_type == "si":
        return verify_si(candidate, reference)
    elif verifier_type == "symbolic":
        return verify_symbolic(candidate, reference)
    elif verifier_type == "ill_posed":
        return verify_ill_posed(candidate)
    return {"verdict": "abstain", "reason": "unknown"}


def build_app() -> gr.Blocks:
    with gr.Blocks(title="验证边界 · Verification Frontier", theme=gr.themes.Soft()) as app:
        gr.Markdown(INTRO)

        with gr.Tabs():
            # ── Tab 1: Overview ──
            with gr.Tab("① 概览 / Overview"):
                gr.Markdown(
                    "## ① LLM 会犯什么逻辑错误\n\n"
                    "| 错误类型 | 例子 |\n|---|---|\n"
                    "| 🔢 量纲错误 | `m/s²`（加速度）当 `m/s`（速度）|\n"
                    "| ➕ 符号错误 | `(x-1)²` 当 `(x+1)²` 展开 |\n"
                    "| 📐 等价错误 | `x²+2x+2` 当 `(x+1)²` |\n"
                    "| 🔍 不可解幻觉 | 对矛盾方程组给出「答案」|\n\n"
                    "👉 **下一页：看真实 LLM 犯这些错误，再看验证器捕获。**\n\n"
                    "👉 **Next: watch a real LLM make these errors, then see the verifier catch them.**"
                )

            # ── Tab 2: Live LLM Error Showcase ──
            with gr.Tab("② 真实 LLM 错误 / Live LLM Errors"):
                gr.Markdown(
                    "## ② 真实 LLM 错误展示 / Live LLM Error Showcase\n\n"
                    "这个页面运行一个**真实的本地 LLM**（Qwen2.5-0.5B-Instruct，CPU 推理）。\n"
                    "点击「🤖 生成」看模型回答——它很可能会犯逻辑错误。\n"
                    "然后点击「🔍 验证」看确定性验证器如何捕获。\n\n"
                    "This page runs a **real local LLM** (Qwen2.5-0.5B-Instruct, CPU).\n"
                    "Click **Generate** to see the model answer — it will likely make a logic error.\n"
                    "Then click **Verify** to see the deterministic verifier catch it."
                )

                # Model status
                status_btn = gr.Button("🔄 检查模型状态 / Check Model Status")
                status_out = gr.JSON(label="模型状态 / Model Status", value=lambda: model_status())
                status_btn.click(lambda: model_status(), outputs=status_out)

                gr.Markdown("---")

                # Build one interactive block per showcase prompt
                for item in SHOWCASE_PROMPTS:
                    with gr.Group():
                        gr.Markdown(f"### {item['title']}")
                        gr.Markdown(f"**📝 提示 / Prompt:**\n```\n{item['prompt']}\n```")
                        gr.Markdown(f"<small>💡 {item['note']}</small>")

                        gen_btn = gr.Button(f"🤖 生成 LLM 回答 / Generate ({item['id']})", variant="secondary")
                        llm_out = gr.Textbox(
                            label="🤖 LLM 回答 / LLM Response",
                            lines=4,
                            interactive=False,
                            placeholder="点击「生成」看模型回答 / Click Generate to see the model's answer",
                        )

                        # Hidden state for the extracted answer
                        extracted = gr.Textbox(visible=False)

                        verify_btn = gr.Button(f"🔍 验证 / Verify ({item['id']})", variant="primary")
                        verdict_out = gr.JSON(label="🔍 验证器裁决 / Verifier Verdict")

                        # Generate handler
                        def make_gen_handler(prompt_text):
                            def handler():
                                resp = generate_response(prompt_text)
                                answer = _extract_answer(resp)
                                return resp, answer
                            return handler

                        gen_btn.click(
                            make_gen_handler(item["prompt"]),
                            outputs=[llm_out, extracted],
                        )

                        # Verify handler
                        def make_verify_handler(vtype, ref):
                            def handler(candidate):
                                if not candidate or not candidate.strip():
                                    return {"verdict": "abstain", "reason": "no answer extracted yet — click Generate first"}
                                return _run_verifier(vtype, candidate, ref)
                            return handler

                        verify_btn.click(
                            make_verify_handler(item["verifier"], item["reference"]),
                            inputs=[extracted],
                            outputs=verdict_out,
                        )

                    gr.Markdown("")

            # ── Tab 3: Plant Your Own Error ──
            with gr.Tab("③ 种一个错误 / Plant an Error"):
                gr.Markdown("## ③ 亲手种一个逻辑错误 / Plant a logic error yourself")
                gr.Markdown("### 🔬 物理量纲 / SI dimension")
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="候选 / candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="参考 / reference")
                si_out = gr.JSON(label="裁决 / verdict")
                gr.Button("🔍 检查 / Check").click(verify_si, [si_c, si_r], si_out)

                gr.Markdown("### 🧮 符号 / Symbolic")
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="候选 / candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="参考 / reference")
                sy_out = gr.JSON(label="裁决 / verdict")
                gr.Button("🔍 检查 / Check").click(verify_symbolic, [sy_c, sy_r], sy_out)

            # ── Tab 4: Three Verdicts ──
            with gr.Tab("④ 三种判定 / Three Verdicts"):
                gr.Markdown(
                    "## ④ 三种判定 / The Three Verdicts\n\n"
                    "| 判定 | 含义 |\n|---|---|\n"
                    "| ✅ **accepted** | 确定性检查**证明**正确 |\n"
                    "| ❌ **rejected** | 确定性检查**证明**有逻辑错误 |\n"
                    "| ⏸️ **abstain** | 无检查能判定——诚实弃权 |"
                )

            # ── Tab 5: Guiding Direction ──
            with gr.Tab("⑤ 引导方向 / Guiding Direction"):
                gr.Markdown(
                    "## ⑤ 引导 LLM 的方向\n\n"
                    "LLM 提议新检查 → 人类必须批准 → 覆盖范围安全推进。"
                )
                with gr.Row():
                    owner = gr.Checkbox(value=False, label="👤 所有者批准")
                    expert = gr.Checkbox(value=False, label="🔬 专家 AI 批准")
                    tests = gr.Checkbox(value=False, label="🧪 测试通过")
                gate_out = gr.JSON(label="门的结果 / gate result")
                gr.Button("⚡ 运行门 / Run gate").click(
                    frontier_gate_preview, [owner, expert, tests], gate_out
                )

            # ── Tab 6: Ill-Posedness ──
            with gr.Tab("⑥ 识别不可解 / Ill-Posedness"):
                gr.Markdown(
                    "## ⑥ 病态问题检测\n\n"
                    "**结果：30/30 病态问题被正确弃权 (100%)**"
                )
                ill_input = gr.Textbox(value="x + y = 3, x + y = 5", label="问题 / Problem")
                ill_out = gr.JSON(label="裁决 / Verdict")
                gr.Button("🔍 检查 / Check").click(
                    lambda t: verify_ill_posed(t).to_dict(), [ill_input], ill_out
                )

            # ── Tab 7: Honest Results ──
            with gr.Tab("⑦ 诚实结果 / Honest Results"):
                gr.Markdown(
                    "## ⑦ 诚实的结果\n\n"
                    "| 指标 | 结果 |\n|---|---|\n"
                    "| 逻辑错误捕获率 | **67/67 (100%)** |\n"
                    "| 病态问题弃权率 | **30/30 (100%)** |\n"
                    "| 基线比较 | proposed-system 优于全部 3 个参照 |\n"
                    "| 自我修正错误下降 | 83.6% |\n"
                    "| Stage A (GPU) | 23/24 结构化输出有效 |"
                )

        gr.Markdown(FOOTER)
    return app


if __name__ == "__main__":
    build_app().launch()
