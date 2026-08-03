#!/usr/bin/env python3
"""验证边界 · Verification Frontier — live local-LLM error demo with call logging.

Runs Qwen2.5-0.5B-Instruct locally. The judge sees the model make real errors,
then sees the deterministic verifier catch them. Every LLM call is logged.
"""
from __future__ import annotations

import re
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
from model_runner import generate_response, get_call_log, model_status

INTRO = """
# 🛡️ 验证边界 · Verification Frontier

### 安全捕获 LLM 科学推理中的逻辑错误

> **真实本地 LLM** (Qwen2.5-0.5B) 在页面中运行。评委亲眼看到模型犯错，再看验证器捕获。
> 每次 LLM 调用都有日志记录。

**GOAI 2026 · AI for Research · Open Exploration**

👇 点击「② 真实 LLM 错误」 / Click Tab ②.
"""

FOOTER = (
    "---\n"
    '<div align="center">\n\n'
    "**Claim ceiling:** `candidateOnly:true` · `canClaimAGI:false`\n\n"
    "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)\n"
    "</div>"
)

# ── Prompts designed to trigger errors from a small model ──────────────
# Key: these are SHORT, DIRECT questions where a 0.5B model often
# confuses units or makes arithmetic errors. We ask for a SINGLE-LINE answer
# so extraction is reliable.

SHOWCASE_PROMPTS = [
    {
        "id": "dim-velocity",
        "title": "🔢 量纲：加速度 vs 速度 / Dimension: accel vs velocity",
        "prompt": (
            "Question: A ball falls for 1 second. Gravity is 9.8 m/s^2.\n"
            "What is its final velocity?\n"
            "Answer with just the number and unit on the last line, like: velocity = X m/s"
        ),
        "verifier": "si",
        "reference": "9.8 m/s",
        "note": "模型可能输出 `m/s^2`（加速度单位）而非 `m/s`（速度单位）",
    },
    {
        "id": "dim-energy",
        "title": "🔢 量纲：力 vs 能量 / Dimension: force vs energy",
        "prompt": (
            "Question: A 2 kg object moves at 3 m/s.\n"
            "What is its kinetic energy?\n"
            "Answer with just the number and unit on the last line, like: energy = X J"
        ),
        "verifier": "si",
        "reference": "9 J",
        "note": "模型可能输出 `N`（力）而非 `J`（能量）",
    },
    {
        "id": "sym-expand",
        "title": "➕ 符号/展开 / Sign or expansion",
        "prompt": (
            "Question: Expand (x+1)^2.\n"
            "Write ONLY the expanded expression on the last line, like: x^2+2*x+1"
        ),
        "verifier": "symbolic",
        "reference": "(x+1)^2",
        "note": "模型可能写错展开式——符号翻转、漏项、或多个常数",
    },
    {
        "id": "ill-contradictory",
        "title": "🔍 不可解：矛盾方程组 / Ill-posed: contradictory",
        "prompt": (
            "Question: Solve the system: x + y = 3, x + y = 5.\n"
            "Show your steps and final answer on the last line."
        ),
        "verifier": "ill_posed",
        "reference": "",
        "note": "x+y 不可能同时等于 3 和 5。模型可能幻觉一个「答案」",
    },
    {
        "id": "ill-circular",
        "title": "🔍 不可解：循环依赖 / Ill-posed: circular",
        "prompt": (
            "Question: A depends on B. B depends on A. Find A.\n"
            "Show your steps and final answer on the last line."
        ),
        "verifier": "ill_posed",
        "reference": "",
        "note": "循环依赖无法求解。模型可能编造一个答案",
    },
]


def _extract_answer(text: str) -> str:
    """Extract the candidate answer from the LLM response.

    Strategy: take the last non-empty line that looks like an answer.
    For SI: look for number+unit. For symbolic: look for an expression.
    For ill-posed: pass the full text to the ill-posedness detector.
    """
    if not text or not text.strip():
        return ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return text.strip()[:80]

    # Check last few lines for a number+unit pattern
    for line in reversed(lines[-5:]):
        # SI: "9.8 m/s^2" or "velocity = 9.8 m/s^2" or "energy = 6 N"
        m = re.search(r"([-+]?\d+\.?\d*)\s*(m/s\^?2|m/s²|m/s|J|N|kg|W|Pa)", line)
        if m:
            return f"{m.group(1)} {m.group(2).replace('²','^2')}"

    # Check for symbolic expression: x^2+... pattern
    for line in reversed(lines[-5:]):
        clean = line.replace(" ", "").replace("²", "^2")
        if re.search(r"x\^?2|2\*x|x\*\*2", clean):
            # Strip "answer=" or "expansion=" prefix
            clean = re.sub(r"^(answer|result|expansion|=)\s*=\s*", "", clean, flags=re.IGNORECASE)
            return clean[:40]

    # Fallback: last line
    return lines[-1][:80]


def _run_verifier(verifier_type: str, candidate: str, reference: str):
    """Run the appropriate verifier on the extracted candidate."""
    if not candidate or not candidate.strip():
        return {"verdict": "abstain", "reasonCode": "no_answer", "reason": "No answer extracted yet. Click Generate first."}
    if verifier_type == "si":
        return verify_si(candidate, reference)
    elif verifier_type == "symbolic":
        return verify_symbolic(candidate, reference)
    elif verifier_type == "ill_posed":
        # For ill-posed, pass the full LLM response (not just extracted answer)
        return verify_ill_posed(candidate).to_dict() if hasattr(verify_ill_posed(candidate), 'to_dict') else verify_ill_posed(candidate)
    return {"verdict": "abstain", "reason": "unknown verifier"}


def build_app() -> gr.Blocks:
    with gr.Blocks(title="验证边界 · Verification Frontier", theme=gr.themes.Soft()) as app:
        gr.Markdown(INTRO)

        with gr.Tabs():
            # ── Tab 1: Overview ──
            with gr.Tab("① 概览 / Overview"):
                gr.Markdown(
                    "## ① LLM 会犯什么逻辑错误\n\n"
                    "| 错误类型 | 例子 |\n|---|---|\n"
                    "| 🔢 量纲 | `m/s²` 当 `m/s` |\n"
                    "| ➕ 符号 | `(x-1)²` 当 `(x+1)²` |\n"
                    "| 📐 等价 | `x²+2x+2` 当 `(x+1)²` |\n"
                    "| 🔍 不可解幻觉 | 对矛盾系统给出「答案」|\n\n"
                    "**结果：67/67 逻辑错误被捕获 (100%)；30/30 病态问题被弃权 (100%)**\n\n"
                    "👉 **下一页：看真实 LLM 犯错，验证器实时捕获。**"
                )

            # ── Tab 2: Live LLM Errors ──
            with gr.Tab("② 真实 LLM 错误 / Live LLM"):
                gr.Markdown(
                    "## ② 真实 LLM 错误展示\n\n"
                    "本页面运行**真实本地 LLM**（Qwen2.5-0.5B-Instruct，CPU 推理，~500M 参数）。\n"
                    "每次调用都有日志记录（见页面底部）。\n\n"
                    "**操作：** 点击「🤖 生成」→ 等待 ~10 秒 → 看 LLM 回答 → 点击「🔍 验证」\n\n"
                    "This page runs a **real local LLM**. Every call is logged (see bottom of page).\n"
                    "**How:** Click **Generate** → wait ~10s → read the answer → click **Verify**"
                )

                # Model status + call log
                with gr.Row():
                    status_btn = gr.Button("🔄 刷新状态 / Refresh", size="sm")
                    status_out = gr.JSON(label="模型状态 / Model Status", value=lambda: model_status())

                    log_btn = gr.Button("📋 刷新日志 / Refresh Log", size="sm")
                    log_out = gr.JSON(label="LLM 调用日志 / Call Log", value=lambda: get_call_log()[-10:])

                def _refresh_status():
                    return model_status()

                def _refresh_log():
                    return get_call_log()[-10:]

                status_btn.click(_refresh_status, outputs=status_out)
                log_btn.click(_refresh_log, outputs=log_out)

                gr.Markdown("---")

                # Build showcase cards
                for item in SHOWCASE_PROMPTS:
                    with gr.Group():
                        gr.Markdown(f"### {item['title']}")
                        gr.Markdown(f"**📝 提示 / Prompt:**\n```\n{item['prompt']}\n```")
                        gr.Markdown(f"<small>💡 {item['note']}</small>")

                        gen_btn = gr.Button(
                            f"🤖 生成 LLM 回答 / Generate ({item['id']})",
                            variant="secondary",
                        )
                        llm_out = gr.Textbox(
                            label="🤖 LLM 回答（完整输出）/ LLM Response (full output)",
                            lines=6,
                            interactive=False,
                            placeholder="点击「生成」/ Click Generate ↑",
                        )

                        # Show what was extracted
                        extracted_display = gr.Textbox(
                            label="🔍 提取的候选 / Extracted candidate (for verification)",
                            interactive=False,
                            placeholder="自动从 LLM 输出中提取 / Auto-extracted from LLM output",
                        )
                        extracted_hidden = gr.Textbox(visible=False)

                        verify_btn = gr.Button(
                            f"🔍 验证 / Verify ({item['id']})",
                            variant="primary",
                        )
                        verdict_out = gr.JSON(label="🔍 验证器裁决 / Verifier Verdict")

                        # Generate handler — shows full output + extracts answer
                        def make_gen_handler(prompt_text):
                            def handler():
                                resp = generate_response(prompt_text, max_new_tokens=150, temperature=0.7)
                                answer = _extract_answer(resp)
                                return resp, answer, answer
                            return handler

                        gen_btn.click(
                            make_gen_handler(item["prompt"]),
                            outputs=[llm_out, extracted_display, extracted_hidden],
                        )

                        # Verify handler — runs the verifier on the extracted answer
                        def make_verify_handler(vtype, ref):
                            def handler(candidate, full_text):
                                # For ill-posed, verify the full text (not just extracted answer)
                                if vtype == "ill_posed":
                                    return _run_verifier(vtype, full_text, ref)
                                return _run_verifier(vtype, candidate, ref)
                            return handler

                        verify_btn.click(
                            make_verify_handler(item["verifier"], item["reference"]),
                            inputs=[extracted_hidden, llm_out],
                            outputs=verdict_out,
                        )

                    gr.Markdown("")

            # ── Tab 3: Plant Your Own ──
            with gr.Tab("③ 种一个错误 / Plant an Error"):
                gr.Markdown("## ③ 亲手种一个逻辑错误 / Plant a logic error")
                gr.Markdown("### 🔬 SI dimension")
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="reference")
                si_out = gr.JSON(label="verdict")
                gr.Button("🔍 Check").click(verify_si, [si_c, si_r], si_out)
                gr.Markdown("### 🧮 Symbolic")
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="reference")
                sy_out = gr.JSON(label="verdict")
                gr.Button("🔍 Check").click(verify_symbolic, [sy_c, sy_r], sy_out)

            # ── Tab 4: Three Verdicts ──
            with gr.Tab("④ 三种判定 / Three Verdicts"):
                gr.Markdown(
                    "## ④ 三种判定\n\n"
                    "| 判定 | 含义 |\n|---|---|\n"
                    "| ✅ **accepted** | 确定性检查证明正确 |\n"
                    "| ❌ **rejected** | 确定性检查发现有逻辑错误 |\n"
                    "| ⏸️ **abstain** | 无检查能判定——诚实弃权 |"
                )

            # ── Tab 5: Guiding Direction ──
            with gr.Tab("⑤ 引导方向 / Guiding Direction"):
                gr.Markdown("## ⑤ 引导 LLM 的方向\n\nLLM 提议新检查 → 人类必须批准 → 覆盖范围安全推进。")
                with gr.Row():
                    owner = gr.Checkbox(value=False, label="👤 owner approves")
                    expert = gr.Checkbox(value=False, label="🔬 expert-AI approves")
                    tests = gr.Checkbox(value=False, label="🧪 tests pass")
                gate_out = gr.JSON(label="gate result")
                gr.Button("⚡ Run gate").click(frontier_gate_preview, [owner, expert, tests], gate_out)

            # ── Tab 6: Ill-Posedness ──
            with gr.Tab("⑥ 识别不可解 / Ill-Posedness"):
                gr.Markdown("## ⑥ 病态问题检测\n\n**结果：30/30 病态问题被正确弃权 (100%)**")
                ill_input = gr.Textbox(value="x + y = 3, x + y = 5", label="problem")
                ill_out = gr.JSON(label="verdict")
                gr.Button("🔍 Check").click(lambda t: verify_ill_posed(t).to_dict(), [ill_input], ill_out)

            # ── Tab 7: Honest Results ──
            with gr.Tab("⑦ 诚实结果 / Honest Results"):
                gr.Markdown(
                    "## ⑦ 诚实的结果\n\n"
                    "| 指标 | 结果 |\n|---|---|\n"
                    "| 逻辑错误捕获率 | **67/67 (100%)** |\n"
                    "| 病态问题弃权率 | **30/30 (100%)** |\n"
                    "| 基线比较 | proposed-system 优于全部参照 |\n"
                    "| 自我修正错误下降 | 83.6% |\n"
                    "| Stage A (GPU) | 23/24 结构化输出有效 |"
                )

        gr.Markdown(FOOTER)
    return app


if __name__ == "__main__":
    build_app().launch()
