#!/usr/bin/env python3
"""验证边界 · Verification Frontier — live local-LLM demo with per-session logging."""
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
from model_runner import generate_response, get_session_log, get_global_log, model_status

INTRO = """
# 🛡️ 验证边界 · Verification Frontier
### 安全捕获 LLM 科学推理中的逻辑错误
> 真实本地 LLM (Qwen2.5-0.5B) 在页面中运行。评委看到模型犯错，再看验证器捕获。
> 每次调用按会话记录 (per-session log)。
**GOAI 2026 · AI for Research · Open Exploration**
"""

FOOTER = (
    "---\n"
    "`candidateOnly:true` · `canClaimAGI:false` · "
    "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)"
)

# ── Prompts designed to trigger errors from a 0.5B model ──────────────
SHOWCASE = [
    {
        "id": "dim-velocity",
        "title": "🔢 量纲：加速度 vs 速度",
        "prompt": (
            "A ball is dropped from rest. After 1 second, gravity (g=9.8 m/s^2) has acted on it.\n"
            "What is its final velocity? Give just the final number and units."
        ),
        "verifier": "si",
        "reference": "9.8 m/s",
        "hint": "⚠️ 这是一个**故意设计的提示**，旨在触发量纲错误。我们有意只问「final velocity」而不提醒单位——小模型常混淆 `m/s²`（加速度）与 `m/s`（速度）。",
    },
    {
        "id": "dim-energy",
        "title": "🔢 量纲：力 vs 能量",
        "prompt": (
            "A 2 kg ball moves at 3 m/s.\n"
            "Calculate its kinetic energy. Give just the final number and units."
        ),
        "verifier": "si",
        "reference": "9 J",
        "hint": "⚠️ **故意设计的提示**：不提示「焦耳」，让模型自行选择单位——它经常输出 `N`（力）而非 `J`（能量）。",
    },
    {
        "id": "sym-expand",
        "title": "➕ 展开：符号或常数错误",
        "prompt": "Expand (x+1)^2. Show the result.",
        "verifier": "symbolic",
        "reference": "(x+1)^2",
        "hint": "⚠️ **故意设计的提示**：要求展开但不给步骤提示——小模型在高温采样下常犯符号翻转、漏项或常数错误。",
    },
    {
        "id": "ill-contradictory",
        "title": "🔍 不可解：矛盾方程组",
        "prompt": "Solve the system: x + y = 3, x + y = 5.\nShow your work.",
        "verifier": "ill_posed",
        "reference": "",
        "hint": "⚠️ **故意设计的提示**：给出一个矛盾方程组。正确的回答是「无解」，但 LLM 通常会幻觉出一个「答案」。这正是 2025 文献报告的「LLM 无法识别不可解性」。",
    },
    {
        "id": "ill-circular",
        "title": "🔍 不可解：循环依赖",
        "prompt": "A depends on B. B depends on A. Find the value of A.\nShow your work.",
        "verifier": "ill_posed",
        "reference": "",
        "hint": "⚠️ **故意设计的提示**：循环依赖（A→B→A）在数学上不可解。LLM 通常不识别循环性，而是编造一个答案。",
    },
]


def _extract(text: str) -> str:
    """Extract a candidate answer from the model's full response."""
    if not text or not text.strip():
        return ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]

    # 1. Look for explicit "answer = X" pattern
    for line in reversed(lines):
        m = re.search(r"(?:answer|result|velocity|energy|expansion|final)\s*[:=]\s*(.+)", line, re.I)
        if m:
            val = m.group(1).strip().rstrip(".")
            if val:
                return val[:60]

    # 2. Look for SI: number + unit anywhere in last 3 lines
    for line in reversed(lines[-3:]):
        m = re.search(r"([-+]?\d+\.?\d*)\s*(m/s\^?2|m/s²|m/s|J|N|kg|W|Pa)", line)
        if m:
            unit = m.group(2).replace("²", "^2")
            return f"{m.group(1)} {unit}"

    # 3. Look for symbolic: x^2 or x**2 pattern
    for line in reversed(lines[-3:]):
        clean = line.replace(" ", "").replace("²", "^2")
        if re.search(r"[a-z]\^?2|[a-z]\*\*2", clean, re.I):
            clean = re.sub(r"^(.*?[:=])", "", clean)
            return clean[:40]

    # 4. Just the last non-empty line, truncated
    return lines[-1][:60] if lines else text.strip()[:60]


def _verify(vtype, candidate, reference, full_text):
    if vtype == "ill_posed":
        # For ill-posed, check the full text (model may write the system in its reasoning)
        return verify_ill_posed(full_text).to_dict()
    if not candidate or not candidate.strip():
        return {"verdict": "abstain", "reasonCode": "no_answer", "reason": "Click Generate first."}
    if vtype == "si":
        return verify_si(candidate, reference)
    if vtype == "symbolic":
        return verify_symbolic(candidate, reference)
    return {"verdict": "abstain", "reason": "unknown"}


def build_app():
    with gr.Blocks(title="验证边界 · Verification Frontier", theme=gr.themes.Soft()) as app:
        # Per-session ID
        session_id = gr.State(value=lambda: uuid.uuid4().hex)

        gr.Markdown(INTRO)

        with gr.Tabs():
            with gr.Tab("① 概览"):
                gr.Markdown(
                    "## ① LLM 会犯什么逻辑错误\n\n"
                    "| 类型 | 例子 |\n|---|---|\n"
                    "| 🔢 量纲 | `m/s²` 当 `m/s` |\n"
                    "| ➕ 符号 | `(x-1)²` 当 `(x+1)²` |\n"
                    "| 📐 等价 | `x²+2x+2` 当 `(x+1)²` |\n"
                    "| 🔍 不可解 | 对矛盾系统给「答案」|\n\n"
                    "**67/67 逻辑错误被捕获 · 30/30 病态问题被弃权**\n\n"
                    "👉 点击 ② 看真实 LLM 犯错。"
                )

            with gr.Tab("② 真实 LLM / Live LLM"):
                gr.Markdown(
                    "## ② 真实 LLM 错误展示 / Live LLM Error Showcase\n\n"
                    "> **⚠️ 实验设计说明 / Experimental Design Note**\n>\n"
                    "> 以下提示是**故意设计的**，旨在触发 LLM 的特定逻辑错误。\n"
                    "> 我们有意省略单位提示、给出矛盾系统、或要求小模型做它容易出错的计算。\n"
                    "> 这不是为了证明 LLM「笨」，而是为了**演示确定性验证器如何捕获这些错误**。\n"
                    ">\n"
                    "> The prompts below are **deliberately crafted** to trigger specific logic errors.\n"
                    "> We intentionally omit unit hints, present contradictory systems, or ask a\n"
                    "> small model to do calculations it tends to get wrong. The point is NOT to\n"
                    "> show the LLM is dumb — it's to **demonstrate how the deterministic verifier\n"
                    "> catches the errors**.\n\n"
                    "**真实本地 LLM**（Qwen2.5-0.5B，~500M 参数，CPU 推理）\n\n"
                    "点击「🤖 生成」→ 等 ~5 秒 → 看完整回答 → 点击「🔍 验证」\n\n"
                    "每次调用按会话记录（底部可查看本会话日志和全部日志）。\n"
                    "Every call is logged per-session (see bottom: Session Log + Global Log).\n"
                    "The **full response text** is captured in the log."
                )

                # Status + log row
                with gr.Row():
                    st_btn = gr.Button("🔄 状态", size="sm")
                    st_out = gr.JSON(label="模型", value=lambda: model_status())
                    sl_btn = gr.Button("📋 本会话日志", size="sm")
                    sl_out = gr.JSON(label="本会话调用 / Session Log")
                    gl_btn = gr.Button("🌐 全部日志", size="sm")
                    gl_out = gr.JSON(label="全部调用 / Global Log")

                st_btn.click(lambda: model_status(), outputs=st_out)

                def _sess_log(sid):
                    return get_session_log(sid) or [{"note": "no calls yet — click Generate on a card above"}]
                sl_btn.click(_sess_log, inputs=[session_id], outputs=sl_out)
                gl_btn.click(lambda: get_global_log(15), outputs=gl_out)

                gr.Markdown("---")

                for item in SHOWCASE:
                    with gr.Group():
                        gr.Markdown(f"### {item['title']}")
                        gr.Markdown(f"**📝 Prompt:**\n```\n{item['prompt']}\n```")
                        gr.Markdown(f"<small>💡 {item['hint']}</small>")

                        gen_btn = gr.Button(f"🤖 生成 / Generate ({item['id']})", variant="secondary")
                        llm_out = gr.Textbox(
                            label="🤖 LLM 回答（完整）/ LLM Response (full)",
                            lines=7, interactive=False,
                            placeholder="点击生成 / Click Generate ↑",
                        )
                        extracted_box = gr.Textbox(
                            label="🔍 提取候选 / Extracted", interactive=False,
                            placeholder="自动提取 / auto-extracted",
                        )
                        extracted_hidden = gr.Textbox(visible=False)

                        verify_btn = gr.Button(f"🔍 验证 / Verify ({item['id']})", variant="primary")
                        verdict_out = gr.JSON(label="🔍 裁决 / Verdict")

                        def _gen(prompt, sid):
                            resp = generate_response(prompt, session_id=sid, max_new_tokens=200, temperature=0.8)
                            ans = _extract(resp)
                            return resp, ans, ans

                        gen_btn.click(
                            _gen,
                            inputs=[gr.State(item["prompt"]), session_id],
                            outputs=[llm_out, extracted_box, extracted_hidden],
                        )

                        def _ver(vtype, cand, ref, full):
                            return _verify(vtype, cand, ref, full)
                        verify_btn.click(
                            _ver,
                            inputs=[
                                gr.State(item["verifier"]),
                                extracted_hidden,
                                gr.State(item["reference"]),
                                llm_out,
                            ],
                            outputs=verdict_out,
                        )
                    gr.Markdown("")

            with gr.Tab("③ 种一个错误"):
                gr.Markdown("## ③ 手动测试 / Manual test")
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="reference")
                gr.Button("🔍 Check").click(verify_si, [si_c, si_r], gr.JSON(label="verdict"))
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="reference")
                gr.Button("🔍 Check").click(verify_symbolic, [sy_c, sy_r], gr.JSON(label="verdict"))

            with gr.Tab("④ 三种判定"):
                gr.Markdown(
                    "## ④ 三种判定\n\n"
                    "| 判定 | 含义 |\n|---|---|\n"
                    "| ✅ accepted | 确定性检查证明正确 |\n"
                    "| ❌ rejected | 确定性检查发现逻辑错误 |\n"
                    "| ⏸️ abstain | 无检查能判定——弃权 |"
                )

            with gr.Tab("⑤ 引导方向"):
                gr.Markdown("## ⑤ 引导 LLM 方向\n\nLLM 提议 → 人类批准 → 覆盖推进。")
                with gr.Row():
                    o = gr.Checkbox(value=False, label="👤 owner")
                    e = gr.Checkbox(value=False, label="🔬 expert")
                    t = gr.Checkbox(value=False, label="🧪 tests")
                gr.Button("⚡ Run").click(frontier_gate_preview, [o, e, t], gr.JSON(label="gate"))

            with gr.Tab("⑥ 不可解"):
                gr.Markdown("## ⑥ 病态检测\n\n**30/30 弃权率**")
                ill = gr.Textbox(value="x + y = 3, x + y = 5", label="problem")
                gr.Button("🔍 Check").click(lambda t: verify_ill_posed(t).to_dict(), [ill], gr.JSON(label="verdict"))

            with gr.Tab("⑦ 诚实结果"):
                gr.Markdown(
                    "## ⑦ 结果\n\n"
                    "| 指标 | 结果 |\n|---|---|\n"
                    "| 逻辑错误捕获 | **67/67 (100%)** |\n"
                    "| 病态弃权 | **30/30 (100%)** |\n"
                    "| 基线比较 | proposed-system 全优 |\n"
                    "| 自我修正 | 83.6% 错误下降 |\n"
                    "| Stage A (GPU) | 23/24 |"
                )

        gr.Markdown(FOOTER)
    return app


if __name__ == "__main__":
    build_app().launch()
