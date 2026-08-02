#!/usr/bin/env python3
"""验证边界 · Verification Frontier — a story-driven, plain-language demo.

This is NOT a tools page. It is a guided narrative that walks a non-expert
through: the three verdicts → the silent-pass danger → safe frontier expansion
→ the human/expert gate → an honest 23/24 report. Bilingual (中文 + EN).
Zero network calls, zero model calls.
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

LQ = "\u201c"  # left curly quote
RQ = "\u201d"  # right curly quote

INTRO = f"""
# 🛡️ 验证边界 · Verification Frontier

### 安全扩展科学 Agent 的验证边界 / Safely Expanding the Verification Frontier of Scientific Agents

> **用 5 分钟讲完一个关于{LQ}信任{RQ}的故事 / A 5-minute story about trust.**
>
> 想象一个科学 Agent（比如帮科学家做计算或证明的 AI 助手）。它在每一步都要回答一个问题：
> **{LQ}这个结果，我能不能验证它是对的？{RQ}**
>
> Imagine a scientific agent — an AI that helps a scientist compute or prove things.
> At every step it faces one question: **{LQ}Can I verify this answer is correct?{RQ}**

**GOAI 2026 · AI for Research · Open Exploration**

下方有 6 个标签，请从左到右依次阅读。 / Read the 6 tabs below, left to right.

<table><tr>
<td align="center">① 三种判定<br/>Three Verdicts</td>
<td align="center">② 危险<br/>The Danger</td>
<td align="center">③ 试试看<br/>Try It</td>
<td align="center">④ 安全扩展<br/>Safe Expansion</td>
<td align="center">⑤ 必须有人批准<br/>Human Gate</td>
<td align="center">⑥ 诚实的结果<br/>Honest Result</td>
</tr></table>
"""

STEP1 = f"""
## ① 三种判定 / The Three Verdicts

当一个 Agent 检查一个答案时，只有**三种**诚实的判定：

When an agent checks an answer, there are only **three** honest verdicts:

| 判定 / Verdict | 含义 / Meaning | 例子 / Example |
|---|---|---|
| ✅ **accepted 通过** | 有一个现成的可执行检查**证明它对** / an executable check **proves it right** | `9.8 m/s²` 的自由落体加速度 |
| ❌ **rejected 否决** | 有一个现成的可执行检查**证明它错** / an executable check **proves it wrong** | 把{LQ}米/秒{RQ}当成{LQ}米/秒²{RQ} |
| ⏸️ **abstain 弃权** | **没有**任何现成检查能判断——老实说{LQ}我不知道{RQ} / **no** executable check can decide — honestly says {LQ}I don't know{RQ} | 一个还没有形式化的开放数学难题 |

> **关键点 / Key point：** 第三种{LQ}弃权{RQ}绝不是{LQ}通过{RQ}。它诚实地承认{LQ}我还验证不了{RQ}。
> The third verdict, abstain, is **never** {LQ}passed.{RQ} It honestly admits {LQ}I cannot verify this yet.{RQ}
"""

STEP2 = f"""
## ② 危险：把{LQ}不知道{RQ}当成{LQ}没问题{RQ} / The Danger: {LQ}I don't know{RQ} ≠ {LQ}No problem{RQ}

大多数系统只有两种状态：**对** 或 **错**。于是当它检查不了一个答案时，
它会说——{LQ}没发现错误{RQ}。

Most systems have only two states: **right** or **wrong**. So when they cannot
check an answer, they say — {LQ}no error found.{RQ}

> ⚠️ **这就是{LQ}静默放行{RQ}——最危险的失败。**
> **This is the {LQ}silent pass{RQ} — the most dangerous failure.**

**打个比方 / Analogy:**

想象一个保安，他的清单上只有两项：{LQ}这个人有钥匙吗？有 / 没有。{RQ}
现在来了一个他完全不认识的人。清单上没有{LQ}我不认识这个人{RQ}这一项，
于是他……默认放行了。

Imagine a security guard whose checklist has only two boxes: {LQ}has key: yes/no.{RQ}
A total stranger arrives. There is no box for {LQ}I don't recognize this person,{RQ}
so… they wave them through.

**验证边界项目要做的，就是给这个保安加上第三只盒子：{LQ}弃权{RQ}，并且让{LQ}弃权{RQ}
永远不能被偷偷当成{LQ}通过{RQ}。**

The Verification Frontier project adds that third box — {LQ}abstain{RQ} — and makes
sure {LQ}abstain{RQ} can **never** be quietly treated as {LQ}passed.{RQ}

👇 下一页，你来当这个保安。 / Next page, you be the guard.
"""

STEP3_HEAD = (
    "## ③ 自己当验证器 / Be the verifier yourself\n\n"
    "下面你可以亲手输入物理量或数学式，看看系统如何判定。"
    "注意：对于无法判断的，它会**弃权**而不是瞎猜。\n\n"
    "Below you can type a physics quantity or a math expression "
    "and watch the system decide. Note: when it can't decide, "
    "it **abstains** rather than guessing.\n"
)

STEP3_FOOT = (
    "> 看到了吗？判定永远是三种之一：**通过 / 否决 / 弃权**。"
    "对于没有可执行检查的（比如一个开放数学难题），系统会弃权。\n\n"
    "> See? The verdict is always one of three: **accepted / rejected / abstain**. "
    "For things with no executable check (e.g. an open math problem), it abstains."
)

STEP4 = f"""
## ④ 安全地扩大能验证的范围 / Safely Expanding What Can Be Checked

{LQ}弃权{RQ}解决了静默放行，但带来新问题：**如果永远弃权，科学就永远卡住。**
所以我们问了一个研究问题：

{LQ}Abstain{RQ} fixes the silent pass, but creates a new problem: **if we always
abstain, science gets stuck forever.** So we asked a research question:

> ### 💡 能不能让 Agent {LQ}提议{RQ}一个新的检查方法，在{LQ}人类批准{RQ}后，安全地扩大它能验证的范围？
> ### 💡 Can an agent *propose* a new checking method that, after a *human approves it*, safely expands what can be verified?

**规则 / The rules:**
1. 🤖 Agent 可以**提议**一个新的检查（验证器）。/ The agent may **propose** a new check.
2. 👤 **人类（所有者）必须批准。** / A **human (owner) must approve.**
3. 🔬 **独立的专家 AI 也必须批准。** / An **independent expert-AI must also approve.**
4. 🧪 提议的检查必须通过**可见的测试**（正例、反例、安全、回滚）。/ The proposed check must pass **visible tests**.
5. 🚫 Agent **永远不能**自己批准自己的提议。/ The agent can **never** approve its own proposal.

**只有全部满足，范围才会安全地扩大一格。否则，保持弃权。**
**Only when ALL are met does coverage safely grow by one step. Otherwise, it stays abstain.**

👇 翻到下一页，亲手试试这些开关。 / Next page, try the switches yourself.
"""

STEP5_HEAD = (
    "## ⑤ 亲手试试批准门 / Try the approval gate\n\n"
    "下面是一个**公开的合成示例**。Agent 提议了一个新检查方法（把华氏度转成开尔文）。"
    "请你当所有者和专家，决定要不要批准。\n\n"
    "Below is a **public synthetic example**. The agent proposed a new check "
    "(convert Fahrenheit to Kelvin). You play the owner and expert — "
    "decide whether to approve.\n\n"
    "**关键：在所有门通过之前，结果永远是弃权。试试只勾一个、两个、三个。**\n\n"
    "**Key: until EVERY gate passes, the result stays abstain. "
    "Try checking only one, two, then all three.**"
)

STEP5_FOOT = (
    "> 🎯 **只有当三个都✅，覆盖范围才会扩大。缺任何一个，就保持弃权。**\n"
    "> 这是安全的核心：宁可卡住，也不冒险放行。\n\n"
    "> 🎯 **Only when all three are ✅ does coverage grow. "
    "Miss any one, and it stays abstain.**\n"
    "> This is the heart of safe: better to be stuck than to risk a silent pass."
)

STEP6_HEAD = (
    "## ⑥ 我们诚实的成绩单 / Our honest report card\n\n"
    "我们真的运行了一次完整的开发测试（24 个任务家族，覆盖物理、符号、Lean）。\n"
    "这是真实的结果——**包括一条失败的记录**：\n\n"
    "We actually ran one full development test (24 task families: physics, "
    "symbolic, Lean). Here is the **real result — including one failure**:\n"
)

STEP6_TABLE = (
    "| 指标 / Metric | 结果 / Result |\n"
    "|---|---|\n"
    "| 任务家族 / task families | **24**（8 物理 / 8 符号 / 8 Lean）|\n"
    "| 结构化输出有效 / structured output valid | **23 / 24** ✅ |\n"
    "| 失败的那一个 / the one that failed | 1 条 Lean 响应——**格式错误（未转义换行），被原样保留** |\n"
    "| 开放控制（未解问题）保留为弃权 / open controls kept as abstain | **2 / 2** ✅ |\n"
    "| 七类策略违规 / policy violations | **全部为 0** ✅ |\n"
    "| 被批准的扩展 / approved extensions | **0**（还需人类评审）|\n"
)

STEP6_FOOT = (
    f"> 💡 **为什么我们保留那条失败？** 因为一个悄悄重试到 24/24 的系统，"
    f"报告的是{LQ}运气{RQ}，而不是真实的合规性。这条失败*正是*解析器真实、"
    f"可靠闭失效的证据。\n\n"
    f"> 💡 **Why did we keep that failure?** Because a system that silently "
    f"retries until 24/24 reports *luck*, not real compliance. That failure "
    f"*is* the evidence that the parser is real and fail-closed.\n\n"
    f"**这仅仅是结构化输出与策略合规的证据。它不是验证器扩展、科学发现、"
    f"能力提升、竞赛成绩、获奖资格、AGI 或 ASI 的证据。**\n\n"
    f"**This is structured-output and policy-compliance evidence only. It is "
    f"NOT evidence of a verifier extension, scientific discovery, capability "
    f"uplift, contest score, winner eligibility, AGI, or ASI.**"
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
    with gr.Blocks(
        title="验证边界 · Verification Frontier",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown(INTRO)

        with gr.Tabs():
            with gr.Tab("① 三种判定 / Three Verdicts"):
                gr.Markdown(STEP1)

            with gr.Tab("② 危险 / The Danger"):
                gr.Markdown(STEP2)

            with gr.Tab("③ 试试看 / Try It"):
                gr.Markdown(STEP3_HEAD)

                gr.Markdown("### 🔬 SI 物理验证 / SI physics verification")
                gr.Markdown(
                    "<small>试这些 / try: `9.8 m/s^2` vs `9.8 m/s`（量纲不符 → 否决）；"
                    "`8.91 J` vs `9.0 J`（数值在 1% 内 → 通过）</small>"
                )
                with gr.Row():
                    si_c = gr.Textbox(value="9.8 m/s^2", label="候选 / candidate")
                    si_r = gr.Textbox(value="9.8 m/s", label="参考 / reference")
                si_out = gr.JSON(label="判定 / verdict")
                gr.Button("🔍 验证物理 / Verify physics").click(
                    verify_si, [si_c, si_r], si_out
                )

                gr.Markdown("### 🧮 符号验证 / Symbolic verification")
                gr.Markdown(
                    "<small>试这些 / try: `x^2+2*x+1` vs `(x+1)^2`（等价 → 通过）；"
                    "`x^2+2*x+2` vs `(x+1)^2`（不等价 → 否决）</small>"
                )
                with gr.Row():
                    sy_c = gr.Textbox(value="x^2+2*x+1", label="候选 / candidate")
                    sy_r = gr.Textbox(value="(x+1)^2", label="参考 / reference")
                sy_out = gr.JSON(label="判定 / verdict")
                gr.Button("🔍 验证符号 / Verify symbolic").click(
                    verify_symbolic, [sy_c, sy_r], sy_out
                )

                gr.Markdown(STEP3_FOOT)

            with gr.Tab("④ 安全扩展 / Safe Expansion"):
                gr.Markdown(STEP4)

            with gr.Tab("⑤ 必须有人批准 / Human Gate"):
                gr.Markdown(STEP5_HEAD)
                with gr.Row():
                    owner = gr.Checkbox(
                        value=False, label="👤 所有者批准 / owner approves"
                    )
                    expert = gr.Checkbox(
                        value=False, label="🔬 专家 AI 批准 / expert-AI approves"
                    )
                    tests = gr.Checkbox(
                        value=False, label="🧪 测试全部通过 / all tests pass"
                    )
                gate_out = gr.JSON(label="门的结果 / gate result")
                gr.Button("⚡ 运行门 / Run gate").click(
                    frontier_gate_preview, [owner, expert, tests], gate_out
                )
                gr.Markdown(STEP5_FOOT)

            with gr.Tab("⑥ 诚实的结果 / Honest Result"):
                gr.Markdown(STEP6_HEAD)
                gr.Markdown(STEP6_TABLE)
                gr.Markdown(STEP6_FOOT)

        gr.Markdown(FOOTER)
    return app


if __name__ == "__main__":
    build_app().launch()
