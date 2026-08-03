#!/usr/bin/env python3
"""验证边界 · Verification Frontier — live demo with LLM self-judge vs deterministic verifier.

Each showcase card shows: LLM answers → same LLM judges itself → deterministic verifier judges.
The comparison reveals when self-judgment fails but deterministic checking succeeds.
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
from model_runner import generate_response, self_judge, get_session_log, get_global_log, model_status

INTRO = """
# 🛡️ 验证边界 · Verification Frontier
### 安全捕获 LLM 科学推理中的逻辑错误
> 真实本地 LLM (Qwen2.5-0.5B) 生成回答 → **同一个 LLM 自我检查** → 确定性验证器裁决。
> 评委可以看到：自我检查何时失败，确定性检查何时成功。
**GOAI 2026 · AI for Research · Open Exploration**
"""

FOOTER = (
    "---\n"
    "`candidateOnly:true` · `canClaimAGI:false` · "
    "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)"
)

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
        "hint": "⚠️ **故意设计的提示**：不提醒单位——小模型常混淆 `m/s²`（加速度）与 `m/s`（速度）。",
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
        "hint": "⚠️ **故意设计的提示**：不提示「焦耳」——模型常输出 `N`（力）而非 `J`（能量）。",
    },
    {
        "id": "sym-expand",
        "title": "➕ 展开：符号或常数错误",
        "prompt": "Expand (x+1)^2. Show the result.",
        "verifier": "symbolic",
        "reference": "(x+1)^2",
        "hint": "⚠️ **故意设计的提示**：不给步骤提示——高温采样下小模型常犯符号翻转或常数错误。",
    },
    {
        "id": "ill-contradictory",
        "title": "🔍 不可解：矛盾方程组",
        "prompt": "Solve the system: x + y = 3, x + y = 5.\nShow your work.",
        "verifier": "ill_posed",
        "reference": "",
        "hint": "⚠️ **故意设计的提示**：给出矛盾方程组——正确答案是「无解」，但 LLM 通常幻觉一个「答案」。",
    },
    {
        "id": "ill-circular",
        "title": "🔍 不可解：循环依赖",
        "prompt": "A depends on B. B depends on A. Find the value of A.\nShow your work.",
        "verifier": "ill_posed",
        "reference": "",
        "hint": "⚠️ **故意设计的提示**：循环依赖在数学上不可解——LLM 通常不识别循环性而编造答案。",
    },
]


def _extract(text: str) -> str:
    if not text or not text.strip():
        return ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        m = re.search(r"(?:answer|result|velocity|energy|expansion|final)\s*[:=]\s*(.+)", line, re.I)
        if m:
            val = m.group(1).strip().rstrip(".")
            if val:
                return val[:60]
    for line in reversed(lines[-3:]):
        m = re.search(r"([-+]?\d+\.?\d*)\s*(m/s\^?2|m/s²|m/s|J|N|kg|W|Pa)", line)
        if m:
            unit = m.group(2).replace("²", "^2")
            return f"{m.group(1)} {unit}"
    for line in reversed(lines[-3:]):
        clean = line.replace(" ", "").replace("²", "^2")
        if re.search(r"[a-z]\^?2|[a-z]\*\*2", clean, re.I):
            clean = re.sub(r"^(.*?[:=])", "", clean)
            return clean[:40]
    return lines[-1][:60] if lines else text.strip()[:60]


def _verify(vtype, candidate, reference, full_text):
    if vtype == "ill_posed":
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
                    "**67/67 逻辑错误被确定性验证器捕获 · 30/30 病态问题被弃权**\n\n"
                    "👉 点击 ② 看真实 LLM 生成 → 自我检查 → 确定性验证。"
                )

            with gr.Tab("② 真实 LLM / Live LLM"):
                gr.Markdown(
                    "## ② 真实 LLM 错误展示 + 自我检查 vs 确定性验证\n\n"
                    "> **⚠️ 实验设计 / Experimental Design**\n>\n"
                    "> 提示是**故意设计的**，旨在触发特定逻辑错误（省略单位提示、给出矛盾系统等）。\n"
                    "> 目的不是证明 LLM「笨」，而是演示：**LLM 自我检查何时失败，确定性验证器何时成功**。\n>\n"
                    "> Prompts are **deliberately crafted** to trigger errors. The point is to show\n"
                    "> **when self-judgment fails but deterministic verification succeeds**.\n\n"
                    "**三步流程 / Three-step flow:**\n"
                    "1. 🤖 **生成**：LLM 回答问题（可能犯错）\n"
                    "2. 🔎 **自我检查**：同一个 LLM 批判自己的回答\n"
                    "3. 🔬 **确定性验证**：确定性验证器检查同一个回答\n\n"
                    "**真实本地 LLM**（Qwen2.5-0.5B，CPU）。每次调用记录在日志中（完整响应）。"
                )

                with gr.Row():
                    st_btn = gr.Button("🔄 状态", size="sm")
                    st_out = gr.JSON(label="模型", value=lambda: model_status())
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
                    with gr.Group():
                        gr.Markdown(f"### {item['title']}")
                        gr.Markdown(f"**📝 Prompt:**\n```\n{item['prompt']}\n```")
                        gr.Markdown(f"<small>💡 {item['hint']}</small>")

                        # Step 1: Generate
                        gen_btn = gr.Button(f"1️⃣ 🤖 LLM 生成 / Generate ({item['id']})", variant="secondary")
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
                        prompt_hidden = gr.Textbox(item["prompt"], visible=False)

                        # Step 2: Self-Judge
                        judge_btn = gr.Button(f"2️⃣ 🔎 LLM 自我检查 / Self-Judge ({item['id']})", variant="secondary")
                        judge_out = gr.Textbox(
                            label="🔎 LLM 自我检查 / LLM Self-Assessment",
                            lines=5, interactive=False,
                            placeholder="同一个 LLM 批判自己的回答 / Same LLM critiques its own answer",
                        )

                        # Step 3: Deterministic Verify
                        verify_btn = gr.Button(f"3️⃣ 🔬 确定性验证 / Verify ({item['id']})", variant="primary")
                        verdict_out = gr.JSON(label="🔬 确定性验证器裁决 / Deterministic Verifier")

                        gr.Markdown(
                            "<small>👆 对比步骤 2 和步骤 3：自我检查可能说「正确」，"
                            "但确定性验证器发现错误。这就是确定性验证的价值。</small>"
                        )

                        # Handlers
                        def _gen(prompt, sid):
                            resp = generate_response(prompt, session_id=sid, max_new_tokens=200, temperature=0.8)
                            ans = _extract(resp)
                            return resp, ans, ans

                        gen_btn.click(_gen,
                                      inputs=[prompt_hidden, session_id],
                                      outputs=[llm_out, extracted_box, extracted_hidden])

                        def _judge(prompt, response, sid):
                            if not response or not response.strip() or response.startswith("["):
                                return "[请先生成回答 / Generate first]"
                            return self_judge(prompt, response, session_id=sid)

                        judge_btn.click(_judge,
                                        inputs=[prompt_hidden, llm_out, session_id],
                                        outputs=[judge_out])

                        def _ver(vtype, cand, ref, full):
                            return _verify(vtype, cand, ref, full)
                        verify_btn.click(_ver,
                                         inputs=[gr.State(item["verifier"]), extracted_hidden,
                                                 gr.State(item["reference"]), llm_out],
                                         outputs=verdict_out)

                    gr.Markdown("")

            with gr.Tab("③ 手动测试 / Manual"):
                gr.Markdown("## ③ 手动验证 / Manual Verification\n\n直接输入候选和参考，看确定性验证器裁决。")
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="reference")
                gr.Button("🔍 Check").click(verify_si, [si_c, si_r], gr.JSON(label="verdict"))
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="reference")
                gr.Button("🔍 Check").click(verify_symbolic, [sy_c, sy_r], gr.JSON(label="verdict"))

            with gr.Tab("④ 不可解 / Ill-Posed"):
                gr.Markdown("## ④ 病态检测\n\n**30/30 弃权率**")
                ill = gr.Textbox(value="x + y = 3, x + y = 5", label="problem")
                gr.Button("🔍 Check").click(lambda t: verify_ill_posed(t).to_dict(), [ill], gr.JSON(label="verdict"))

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


if __name__ == "__main__":
    build_app().launch()
