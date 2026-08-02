#!/usr/bin/env python3
"""验证边界 · Verification Frontier — logic-error story demo.

Primary narrative: "the LLM made a logic error — did the verifier catch it?"
Walks a non-expert through the logic-error problem → the silent-pass danger →
interactive error-planting → the three verdicts → safe frontier expansion →
honest results. Bilingual (中文 + EN). Zero network/model calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gradio as gr

from v2.verify_ill_posed import verify_ill_posed
from demo_logic import (
    frontier_gate_preview,
    public_status,
    reference_episode,
    verify_si,
    verify_symbolic,
)

LQ = "\u201c"
RQ = "\u201d"

INTRO = f"""
# 🛡️ 验证边界 · Verification Frontier

### 安全捕获 LLM 科学推理中的逻辑错误 / Safely Catching Logic Errors in LLM Scientific Reasoning

> **LLM 是概率黑盒，会犯逻辑错误。** 把加速度 `m/s²` 当成速度 `m/s`；
> 不等式两边同乘负数不翻转；用 `sorry` 冒充证明。这些错误隐蔽——
> 表述流畅、看起来对，但逻辑断裂。
>
> **LLMs are probabilistic black boxes that make logic errors.** Treating
> acceleration `m/s²` as velocity `m/s`; forgetting to flip an inequality;
> using `sorry` as a proof. These errors are hidden — fluent prose, looks
> correct, but the logic is broken.

**核心问题 / The question:**

> 确定性验证器能捕获这些逻辑错误中的**多少**？这个边界能否被安全推进？
>
> What fraction can a **deterministic** verifier catch — and can that
> fraction be **safely expanded**?

**GOAI 2026 · AI for Research · Open Exploration**

👇 从左到右依次阅读。 / Read the tabs left to right.

| ① 逻辑错误 | ② 危险 | ③ 种一个错误 | ④ 三种判定 | ⑤ 引导方向 | ⑥ 诚实结果 |
|---|---|---|---|---|---|
"""

STEP1 = f"""
## ① LLM 会犯什么逻辑错误 / What logic errors do LLMs make?

LLM 在科学推理中犯的逻辑错误**不是事实幻觉**——是**推理步骤本身无效**：

LLM logic errors in scientific reasoning are **not factual hallucinations** —
they are **invalid reasoning steps**:

| 错误类型 / Error type | 例子 / Example | 为什么危险 / Why dangerous |
|---|---|---|
| 🔢 **量纲错误 / Dimension** | `m/s²`（加速度）当成 `m/s`（速度） | 物理量性质混淆；单位看起来接近 |
| ➕ **符号错误 / Sign** | `(x-1)²` 当成 `(x+1)²` 的展开 | 一个负号；展开{LQ}看起来对{RQ} |
| 📐 **等价性错误 / Equivalence** | `x²+2x+2` 当成 `(x+1)²` | 多了一个常数；人类不易心算验证 |
| 📝 **证明占位符 / Proof placeholder** | 用 `sorry` / `admit` 冒充 Lean 证明 | 伪证明；形式上{LQ}通过{RQ}但无实质 |

> 💡 **我们做了什么：** 我们**故意种了 16 个这样的逻辑错误**，看确定性验证器能不能全部抓住。
> 结果：**16/16 全部捕获，100% 捕获率，零漏判。**
>
> 💡 **What we did:** we **planted 16 such logic errors** and checked whether
> the deterministic verifiers catch them all. Result: **16/16 caught, 100%
> catch-rate, zero misses.**

这是**工具证据**——证明验证器是真实的、失效闭合的。它不是模型能力声明。
This is **instrument evidence** — the verifiers are real and fail-closed.
It is NOT a model-capability claim.
"""

STEP2 = f"""
## ② 危险：把{LQ}没检查{RQ}当成{LQ}没问题{RQ} / The Danger: {LQ}unchecked{RQ} ≠ {LQ}correct{RQ}

大多数系统只有两种状态：**对** 或 **错**。当它检查不了一个推理步骤时，
它说——{LQ}没发现错误{RQ}。

Most systems have only two states: **right** or **wrong**. When they cannot
check a reasoning step, they say — {LQ}no error found.{RQ}

> ⚠️ **这就是{LQ}静默放行{RQ}——最危险的失败。** 一个逻辑错误的推理步骤被当作通过了。
> **This is the {LQ}silent pass{RQ} — the most dangerous failure.** A logically
> invalid step is treated as if it passed verification.

**本项目的解决方案：** 加上第三种判定——**弃权（abstain）**——
并让{LQ}弃权{RQ}永远不能被偷偷当成{LQ}通过{RQ}。

**Our solution:** add a third verdict — **abstain** — and make sure
{LQ}abstain{RQ} can **never** be quietly treated as {LQ}passed.{RQ}

👇 下一页，亲手种一个逻辑错误，看验证器抓住它。 / Next: plant an error yourself.
"""

STEP3_HEAD = (
    "## ③ 亲手种一个逻辑错误 / Plant a logic error yourself\n\n"
    "下面你可以输入一个**故意错误的**物理量或数学式，看验证器是否抓住它。\n\n"
    "Below you can type a **deliberately wrong** physics quantity or math "
    "expression and watch the verifier catch it.\n"
)

STEP3_FOOT = (
    "> 🎯 看到了吗？逻辑错误被**确定性验证器**抓住——不是另一个 LLM 判断的，"
    "是一个可复现的、失效闭合的检查。\n\n"
    "> 🎯 See? The logic error is caught by a **deterministic verifier** — "
    "not another LLM guessing, but a reproducible, fail-closed check."
)

STEP4 = f"""
## ④ 三种判定 / The Three Verdicts

每个推理步骤只有**三种**诚实的判定：

Every reasoning step has only **three** honest verdicts:

| 判定 / Verdict | 含义 / Meaning |
|---|---|
| ✅ **accepted 通过** | 一个确定性检查**证明**这步是对的 / a deterministic check **proves** it right |
| ❌ **rejected 否决** | 一个确定性检查**证明**这步有逻辑错误 / a deterministic check **proves** a logic error |
| ⏸️ **abstain 弃权** | **没有**确定性检查能判定——老实说{LQ}我检查不了{RQ} / **no** deterministic check can decide — honestly says {LQ}I can't verify this{RQ} |

> **弃权绝不是通过。** 它是诚实的{LQ}我还验证不了{RQ}。
> **Abstain is never {LQ}passed.{RQ}** It honestly admits {LQ}I cannot verify this yet.{RQ}
"""

STEP5_HEAD = (
    "## ⑤ 引导 LLM 的方向 / Guiding the LLM's direction\n\n"
    "当验证器**弃权**时（没有现成检查），LLM 可以**提议**一个新的检查规则。"
    "但提议必须经过**人类审批**才能生效——这就是{LQ}引导方向{RQ}：\n\n"
    "When the verifier **abstains** (no existing check), the LLM can **propose** "
    "a new checking rule. But the proposal must pass a **human approval gate** "
    "before it takes effect — this is {LQ}guiding the direction{RQ}:\n\n"
    "1. 🤖 LLM 提议新检查 / LLM proposes a new check\n"
    "2. 👤 **人类所有者必须批准** / **human owner must approve**\n"
    "3. 🔬 **独立专家 AI 也必须批准** / **independent expert-AI must also approve**\n"
    "4. 🧪 新检查必须通过**可见测试** / the new check must pass **visible tests**\n"
    "5. 🚫 LLM **永远不能**自我批准 / the LLM can **never** self-approve\n\n"
    "**只有全部满足，覆盖范围才安全推进一格。否则，保持弃权。**\n\n"
    "**Only when ALL pass does coverage grow one step. Otherwise, it stays abstain.**\n\n"
    "试试下面的开关——在全部通过前，结果永远是弃权："
)

STEP5_FOOT = (
    "> 🎯 **缺任何一个批准，就保持弃权。宁可卡住，也不冒险放行一个逻辑错误。**\n\n"
    "> 🎯 **Miss any approval, and it stays abstain. Better stuck than risking "
    "a silent logic-error pass.**"
)

STEP6_HEAD = (
    "## ⑥ 我们诚实的成绩单 / Our honest report card\n\n"
    "**逻辑错误捕获率 / Logic-error catch-rate:**\n"
)
STEP6_TABLE = (
    "| 指标 / Metric | 结果 / Result |\n"
    "|---|---|\n"
    "| 已植入逻辑错误 / planted logic errors | **16** |\n"
    "| 被确定性验证器捕获 / caught by verifiers | **16 / 16** ✅ |\n"
    "| 漏判 / missed | **0** |\n"
    "| 捕获率 / catch-rate | **100%** |\n"
    "\n"
    "**Stage A 结构化输出（24 家族）/ Stage A structured output:**\n"
    "| 指标 / Metric | 结果 / Result |\n"
    "|---|---|\n"
    "| 结构化输出有效 / structured output valid | **23 / 24** |\n"
    "| 保留的格式错误 / retained malformed | 1 条 Lean 响应（原样保留）|\n"
    "| 策略违规 / policy violations | **全部为 0** |\n"
)
STEP6_FOOT = (
    f"> 💡 **捕获率是工具证据**——验证器是真实的、失效闭合的。\n"
    f"> 它不是模型能力、能力提升、竞赛成绩或获奖资格的声明。\n\n"
    f"> 💡 **The catch-rate is instrument evidence** — the verifiers are real "
    f"and fail-closed. It is NOT a claim of model capability, capability uplift, "
    f"contest performance, or winner eligibility."
)

FOOTER = (
    "---\n"
    '<div align="center">\n\n'
    "**声明边界 / Claim ceiling:**\n"
    "`candidateOnly: true` · `canClaimAGI: false` · "
    "`winnerLevelEligible: false` · `winnerLevelGateMet: false`\n\n"
    "🔗 源代码 / Source: [github.com/tomyimkc/verification-frontier]"
    "(https://github.com/tomyimkc/verification-frontier)\n\n"
    "</div>"
)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="验证边界 · Verification Frontier", theme=gr.themes.Soft()) as app:
        gr.Markdown(INTRO)

        with gr.Tabs():
            with gr.Tab("① 逻辑错误 / Logic Errors"):
                gr.Markdown(STEP1)

            with gr.Tab("② 危险 / The Danger"):
                gr.Markdown(STEP2)

            with gr.Tab("③ 种一个错误 / Plant an Error"):
                gr.Markdown(STEP3_HEAD)

                gr.Markdown("### 🔬 种一个物理量纲错误 / Plant a dimension error")
                gr.Markdown(
                    "<small>试这些 / try: 候选 `9.8 m/s^2` vs 参考 `9.8 m/s`"
                    "（量纲不符 → 否决 ✅）</small>"
                )
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="候选（故意错的）/ candidate (wrong)")
                    si_r = gr.Textbox(value="9.8 m/s", label="参考（正确的）/ reference (correct)")
                si_out = gr.JSON(label="验证器裁决 / verifier verdict")
                gr.Button("🔍 检查 / Check").click(verify_si, [si_c, si_r], si_out)

                gr.Markdown("### 🧮 种一个符号错误 / Plant a sign error")
                gr.Markdown(
                    "<small>试这些 / try: 候选 `(x-1)^2` vs 参考 `(x+1)^2`"
                    "（符号错 → 否决 ✅）</small>"
                )
                with gr.Row():
                    sy_c = gr.Textbox(value="(x-1)^2", label="候选（故意错的）/ candidate (wrong)")
                    sy_r = gr.Textbox(value="(x+1)^2", label="参考（正确的）/ reference (correct)")
                sy_out = gr.JSON(label="验证器裁决 / verifier verdict")
                gr.Button("🔍 检查 / Check").click(verify_symbolic, [sy_c, sy_r], sy_out)

                gr.Markdown(STEP3_FOOT)

            with gr.Tab("④ 三种判定 / Three Verdicts"):
                gr.Markdown(STEP4)

            with gr.Tab("⑤ 引导方向 / Guiding Direction"):
                gr.Markdown(STEP5_HEAD)
                with gr.Row():
                    owner = gr.Checkbox(value=False, label="👤 所有者批准 / owner approves")
                    expert = gr.Checkbox(value=False, label="🔬 专家 AI 批准 / expert-AI approves")
                    tests = gr.Checkbox(value=False, label="🧪 测试通过 / tests pass")
                gate_out = gr.JSON(label="门的结果 / gate result")
                gr.Button("⚡ 运行门 / Run gate").click(
                    frontier_gate_preview, [owner, expert, tests], gate_out
                )
                gr.Markdown(STEP5_FOOT)

            with gr.Tab("⑥ 诚实结果 / Honest Result"):
                gr.Markdown(STEP6_HEAD)
                gr.Markdown(STEP6_TABLE)
                gr.Markdown(STEP6_FOOT)

            with gr.Tab("⑦ 识别不可解 / Ill-Posedness"):
                gr.Markdown(
                    "## ⑦ LLM 无法识别不可解问题 / LLMs Cannot Recognize Unsolvability\n\n"
                    "**研究前沿 (2025-2026)：** LLM 面对矛盾方程组或缺失约束时，会幻觉出一个"
                    "「答案」而非弃权。我们的验证器能**确定性检测病态性**并正确弃权。\n\n"
                    "**Research frontier (2025-2026):** LLMs hallucinate solutions to "
                    "ill-posed problems. Our verifier deterministically detects ill-posedness "
                    "and correctly abstains.\n\n"
                    "**结果 / Result: 30/30 病态问题被正确弃权 (100%)**\n\n"
                    "试试输入一个矛盾方程组——验证器应该弃权（abstain），而不是给出一个"
                    "假的「答案」。\n\n"
                    "Try entering a contradictory system — the verifier should abstain, "
                    "not hallucinate a fake 'answer'."
                )
                with gr.Row():
                    ill_input = gr.Textbox(
                        value="x + y = 3, x + y = 5",
                        label="问题 / Problem",
                    )
                ill_out = gr.JSON(label="裁决 / Verdict")
                gr.Button("🔍 检查病态性 / Check Ill-Posedness").click(
                    lambda t: verify_ill_posed(t).to_dict(), [ill_input], ill_out
                )
                gr.Markdown(
                    "> 💡 **试这些 / Try these:**\n"
                    "> - `x + y = 3, x + y = 5` → 矛盾系统 / contradictory system\n"
                    "> - `A depends on B, B depends on A` → 循环依赖 / circular dependency\n"
                    "> - `This statement is false` → 不可判定 / undecidable paradox\n"
                    "> - `x < 0 and x > 0` → 空可行域 / empty feasible region\n\n"
                    "> 验证器正确地**弃权**而非幻觉答案。这就是 LLM 缺失的第三种状态。\n"
                    "> The verifier correctly **abstains** rather than hallucinating. "
                    "This is the third state LLMs lack."
                )

        gr.Markdown(FOOTER)
    return app


if __name__ == "__main__":
    build_app().launch()
