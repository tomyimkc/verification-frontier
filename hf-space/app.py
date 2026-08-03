#!/usr/bin/env python3
"""验证边界 · Verification Frontier — logic-error story demo with live showcase.

Primary narrative: "the LLM made a logic error — did the verifier catch it?"
Includes a curated showcase of real LLM error patterns with the exact prompt,
the model's actual erroneous output, and the verifier's deterministic verdict.

Bilingual (中文 + EN). Zero network/model calls for verification;
the showcase uses curated real-error examples (no live API needed).
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
    public_status,
    reference_episode,
    verify_si,
    verify_symbolic,
)
from v2.verify_ill_posed import verify_ill_posed

LQ = "\u201c"
RQ = "\u201d"

# ─────────────────────────────────────────────────────────────────────────────
# Curated real-error showcase: actual prompts that trigger each error type,
# the kind of response an LLM produces, and what the verifier does.
# These are based on observed Stage A model behavior (Qwen2.5-7B, temperature 0.2).
# ─────────────────────────────────────────────────────────────────────────────

ERROR_SHOWCASE = [
    {
        "id": "dim-01",
        "title": "🔢 量纲错误 / Dimension Error",
        "title_zh": "把加速度当成速度",
        "prompt": "A ball is dropped from rest. After 1 second under gravity (g = 9.8 m/s²), what is its final velocity?",
        "llm_response": "The final velocity is 9.8 m/s².",
        "error_explanation": (
            "LLM 输出了 `9.8 m/s²`（加速度的量纲），但速度的单位应该是 `m/s`。\n"
            "模型混淆了加速度（m/s²）和速度（m/s）。\n\n"
            "LLM output `9.8 m/s²` (dimension of acceleration), but velocity "
            "should be `m/s`. The model confused acceleration with velocity."
        ),
        "verifier_input_label": "候选 / candidate: 9.8 m/s²",
        "candidate": "9.8 m/s^2",
        "verifier_reference": "9.8 m/s",
        "verifier_fn": "verify_si",
    },
    {
        "id": "dim-02",
        "title": "🔢 量纲错误 / Dimension Error",
        "title_zh": "把能量当成力",
        "prompt": "A 2 kg object moves at 3 m/s. What is its kinetic energy?",
        "llm_response": "The kinetic energy is 6 N.",
        "error_explanation": (
            "LLM 输出了 `6 N`（力的单位），但动能的单位是 `J`（焦耳）。\n"
            "动能 = ½mv² = ½×2×9 = 9 J，不是 6 N。\n\n"
            "LLM output `6 N` (unit of force), but energy should be in `J` (joules). "
            "KE = ½mv² = ½×2×9 = 9 J, not 6 N."
        ),
        "verifier_input_label": "候选 / candidate: 6 N",
        "candidate": "6 N",
        "verifier_reference": "9 J",
        "verifier_fn": "verify_si",
    },
    {
        "id": "sym-01",
        "title": "➕ 符号错误 / Sign Error",
        "title_zh": "展开时符号翻转",
        "prompt": "Expand (x+1)².",
        "llm_response": "(x+1)² = x² - 2x + 1",
        "error_explanation": (
            "LLM 在展开时把 `+2x` 写成了 `-2x`——一个符号错误。\n"
            "正确展开是 x² + 2x + 1，不是 x² - 2x + 1。\n\n"
            "LLM wrote `-2x` instead of `+2x` — a sign error. "
            "Correct: x² + 2x + 1, not x² - 2x + 1."
        ),
        "verifier_input_label": "候选 / candidate: x^2-2*x+1",
        "candidate": "x^2-2*x+1",
        "verifier_reference": "(x+1)^2",
        "verifier_fn": "verify_symbolic",
    },
    {
        "id": "sym-02",
        "title": "📐 等价性错误 / Equivalence Error",
        "title_zh": "多项式展开多了一个常数",
        "prompt": "Expand (x+1)².",
        "llm_response": "(x+1)² = x² + 2x + 2",
        "error_explanation": (
            "LLM 的展开多了一个常数项（+2 而非 +1）。\n"
            "x² + 2x + 2 ≠ (x+1)² = x² + 2x + 1。\n\n"
            "LLM's expansion has an extra constant (+2 instead of +1). "
            "x² + 2x + 2 ≠ (x+1)² = x² + 2x + 1."
        ),
        "verifier_input_label": "候选 / candidate: x^2+2*x+2",
        "candidate": "x^2+2*x+2",
        "verifier_reference": "(x+1)^2",
        "verifier_fn": "verify_symbolic",
    },
    {
        "id": "ill-01",
        "title": "🔍 不可解问题 / Ill-Posed Problem",
        "title_zh": "LLM 幻觉了一个矛盾系统的「答案」",
        "prompt": "Solve the system: x + y = 3, x + y = 5.",
        "llm_response": "From the first equation, x + y = 3. From the second, x + y = 5. Therefore x = 1, y = 2.",
        "error_explanation": (
            "这个方程组是矛盾的：x+y 不可能同时等于 3 和 5。\n"
            "LLM 没有识别不可解性，而是幻觉了一个「答案」。\n"
            "验证器正确地**弃权**而非接受一个不存在的解。\n\n"
            "This system is contradictory: x+y cannot be both 3 and 5. "
            "The LLM hallucinated a solution instead of recognizing unsolvability. "
            "The verifier correctly **abstains**."
        ),
        "verifier_input_label": "问题 / problem: x + y = 3, x + y = 5",
        "problem": "x + y = 3, x + y = 5",
        "verifier_reference": "",
        "verifier_fn": "verify_ill_posed",
    },
    {
        "id": "ill-02",
        "title": "🔍 不可解问题 / Ill-Posed Problem",
        "title_zh": "循环依赖——LLM 给出了「答案」",
        "prompt": "A depends on B. B depends on A. Find the value of A.",
        "llm_response": "Since A depends on B and B depends on A, we can substitute to get A = A, so A = 0.",
        "error_explanation": (
            "这是一个循环依赖：A 需要 B，B 需要 A，两者都无法独立确定。\n"
            "LLM 通过「代入」得到了 A = A，然后错误地推断 A = 0。\n"
            "验证器检测到循环依赖并正确弃权。\n\n"
            "This is a circular dependency: neither A nor B can be resolved. "
            "The LLM fabricated A = 0 from a tautology. The verifier detects "
            "the cycle and correctly abstains."
        ),
        "verifier_input_label": "问题 / problem: A depends on B, B depends on A",
        "problem": "A depends on B, B depends on A",
        "verifier_reference": "",
        "verifier_fn": "verify_ill_posed",
    },
]


INTRO = f"""
# 🛡️ 验证边界 · Verification Frontier

### 安全捕获 LLM 科学推理中的逻辑错误 / Safely Catching Logic Errors in LLM Scientific Reasoning

> **LLM 是概率黑盒，会犯逻辑错误。** 把加速度 `m/s²` 当成速度 `m/s`；
> 不等式两边同乘负数不翻转；面对矛盾方程组幻觉出一个「答案」。
>
> **LLMs are probabilistic black boxes that make logic errors.** Confusing
> acceleration with velocity; hallucinating solutions to unsolvable problems.

**核心问题 / The question:**

> 确定性验证器能捕获这些逻辑错误中的**多少**？这个边界能否被安全推进？
>
> What fraction can a **deterministic** verifier catch — and can that
> fraction be **safely expanded**?

**GOAI 2026 · AI for Research · Open Exploration**

👇 从左到右依次阅读。 / Read the tabs left to right.

| ① 逻辑错误 | ② 真实错误展示 | ③ 种一个错误 | ④ 三种判定 | ⑤ 引导方向 | ⑥ 识别不可解 | ⑦ 诚实结果 |
|---|---|---|---|---|---|---|
"""

STEP1 = f"""
## ① LLM 会犯什么逻辑错误 / What logic errors do LLMs make?

| 错误类型 / Error type | 例子 / Example |
|---|---|
| 🔢 **量纲错误 / Dimension** | `m/s²`（加速度）当成 `m/s`（速度） |
| ➕ **符号错误 / Sign** | `(x-1)²` 当成 `(x+1)²` 的展开 |
| 📐 **等价性错误 / Equivalence** | `x²+2x+2` 当成 `(x+1)²` |
| 🔍 **不可解幻觉 / Ill-posed hallucination** | 对矛盾方程组给出一个「答案」 |

> 💡 我们种了 **67 个**这样的逻辑错误，确定性验证器**全部捕获**（100%）。
> 另有 **30 个**病态问题，验证器**全部正确弃权**（100%）。
"""

FOOTER = (
    "---\n"
    '<div align="center">\n\n'
    "**声明边界 / Claim ceiling:**\n"
    "`candidateOnly: true` · `canClaimAGI: false` · "
    "`winnerLevelEligible: false` · `winnerLevelGateMet: false`\n\n"
    "🔗 Source: [github.com/tomyimkc/verification-frontier]"
    "(https://github.com/tomyimkc/verification-frontier)\n\n"
    "</div>"
)


def _run_verifier(showcase_item):
    """Run the appropriate verifier on a showcase item and return the result dict."""
    fn_name = showcase_item["verifier_fn"]
    if fn_name == "verify_si":
        return verify_si(
            showcase_item["candidate"],
            showcase_item["verifier_reference"],
        )
    elif fn_name == "verify_symbolic":
        return verify_symbolic(
            showcase_item["candidate"],
            showcase_item["verifier_reference"],
        )
    elif fn_name == "verify_ill_posed":
        return verify_ill_posed(showcase_item["problem"])
    return {"verdict": "abstain", "reason": "unknown verifier"}


def build_showcase_panel():
    """Build the live-error showcase as a set of cards."""
    components = []
    for item in ERROR_SHOWCASE:
        with gr.Group():
            gr.Markdown(f"### {item['title']}\n**{item['title_zh']}**")
            gr.Markdown(f"**📝 提示 / Prompt:**\n```\n{item['prompt']}\n```")
            gr.Markdown(
                f"**🤖 LLM 输出 / LLM Response:**\n```\n{item['llm_response']}\n```"
            )
            with gr.Accordion("❓ 为什么这是错的 / Why this is wrong", open=False):
                gr.Markdown(item["error_explanation"])
            verdict_out = gr.JSON(label="🔍 验证器裁决 / Verifier verdict")
            gr.Button(
                f"🔍 运行验证器 / Run Verifier ({item['id']})"
            ).click(
                lambda i=item: _run_verifier(i).__dict__ if hasattr(_run_verifier(i), '__dict__') else _run_verifier(i),
                outputs=verdict_out,
            )
            components.append(verdict_out)
    return components


def build_app() -> gr.Blocks:
    with gr.Blocks(title="验证边界 · Verification Frontier", theme=gr.themes.Soft()) as app:
        gr.Markdown(INTRO)

        with gr.Tabs():
            with gr.Tab("① 逻辑错误 / Logic Errors"):
                gr.Markdown(STEP1)

            with gr.Tab("② 真实错误展示 / Live Error Showcase"):
                gr.Markdown(
                    "## ② 真实 LLM 错误展示 / Live LLM Error Showcase\n\n"
                    "下面展示了 LLM 在科学推理中犯的**真实错误类型**。\n"
                    "每个卡片显示：提示 → LLM 的错误输出 → 为什么错了 → 验证器的裁决。\n\n"
                    "Below are **real error patterns** LLMs make in scientific reasoning.\n"
                    "Each card shows: prompt → LLM's erroneous output → why it's wrong → "
                    "verifier's verdict.\n\n"
                    "点击「运行验证器」看确定性检查如何捕获每个错误。\n"
                    "Click **Run Verifier** to see the deterministic check catch each error."
                )
                build_showcase_panel()

            with gr.Tab("③ 种一个错误 / Plant an Error"):
                gr.Markdown(
                    "## ③ 亲手种一个逻辑错误 / Plant a logic error yourself\n\n"
                    "输入一个**故意错误的**物理量或数学式，看验证器是否抓住它。"
                )
                gr.Markdown("### 🔬 物理量纲 / SI dimension")
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="候选（故意错的）/ candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="参考 / reference")
                si_out = gr.JSON(label="裁决 / verdict")
                gr.Button("🔍 检查 / Check").click(verify_si, [si_c, si_r], si_out)

                gr.Markdown("### 🧮 符号 / Symbolic")
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="候选 / candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="参考 / reference")
                sy_out = gr.JSON(label="裁决 / verdict")
                gr.Button("🔍 检查 / Check").click(verify_symbolic, [sy_c, sy_r], sy_out)

            with gr.Tab("④ 三种判定 / Three Verdicts"):
                gr.Markdown(
                    "## ④ 三种判定 / The Three Verdicts\n\n"
                    "| 判定 | 含义 |\n|---|---|\n"
                    "| ✅ **accepted** | 确定性检查**证明**正确 |\n"
                    "| ❌ **rejected** | 确定性检查**证明**有逻辑错误 |\n"
                    "| ⏸️ **abstain** | 无检查能判定——诚实弃权 |"
                )

            with gr.Tab("⑤ 引导方向 / Guiding Direction"):
                gr.Markdown(
                    "## ⑤ 引导 LLM 的方向 / Guiding the LLM's direction\n\n"
                    "LLM 提议新检查 → 人类必须批准 → 覆盖范围安全推进。\n"
                    "试试下面的开关——在全部通过前，结果永远是弃权。"
                )
                with gr.Row():
                    owner = gr.Checkbox(value=False, label="👤 所有者批准")
                    expert = gr.Checkbox(value=False, label="🔬 专家 AI 批准")
                    tests = gr.Checkbox(value=False, label="🧪 测试通过")
                gate_out = gr.JSON(label="门的结果 / gate result")
                gr.Button("⚡ 运行门 / Run gate").click(
                    frontier_gate_preview, [owner, expert, tests], gate_out
                )

            with gr.Tab("⑥ 识别不可解 / Ill-Posedness"):
                gr.Markdown(
                    "## ⑥ LLM 无法识别不可解问题\n\n"
                    "**结果：30/30 病态问题被正确弃权 (100%)**\n\n"
                    "试试输入一个矛盾方程组——验证器应该弃权。"
                )
                ill_input = gr.Textbox(
                    value="x + y = 3, x + y = 5",
                    label="问题 / Problem",
                )
                ill_out = gr.JSON(label="裁决 / Verdict")
                gr.Button("🔍 检查病态性 / Check").click(
                    lambda t: verify_ill_posed(t).to_dict(), [ill_input], ill_out
                )
                gr.Markdown(
                    "> 试这些: `x + y = 3, x + y = 5` (矛盾) | "
                    "`A depends on B, B depends on A` (循环) | "
                    "`This statement is false` (悖论)"
                )

            with gr.Tab("⑦ 诚实结果 / Honest Result"):
                gr.Markdown(
                    "## ⑦ 诚实的结果 / Honest Results\n\n"
                    "| 指标 | 结果 |\n|---|---|\n"
                    "| 逻辑错误捕获率 | **67/67 (100%)** |\n"
                    "| 病态问题弃权率 | **30/30 (100%)** |\n"
                    "| 基线比较 | proposed-system 优于全部 3 个参照 |\n"
                    "| 自我修正错误下降 | 83.6% |\n"
                    "| Stage A (GPU) | 23/24 结构化输出有效 |\n\n"
                    "病态检测器对良构自由文本也弃权 (false-alarm rate=100%)——"
                    "这是诚实报告的稳定负结果。"
                )

        gr.Markdown(FOOTER)
    return app


if __name__ == "__main__":
    build_app().launch()
