#!/usr/bin/env python3
"""验证边界 · Verification Frontier — multi-model comparison demo.

One prompt → several LLMs answer in parallel → each answer runs the full
pipeline: Generate → Self-Judge → Step-Verify → Final Verdict.

The payoff a judge should see in under a minute: a model states a confident
wrong answer, its OWN self-judge calls that answer correct, and the
deterministic verifier still rejects it. That contrast is the whole thesis —
a probabilistic judge cannot be the last word; an executable check can.
"""
from __future__ import annotations
import re, sys, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gradio as gr

from demo_logic import verify_si, verify_symbolic, frontier_gate_preview
from v2.verify_ill_posed import verify_ill_posed
from step_checker import check_steps, summarize, ICON, ERROR, VERIFIED, UNCHECKED
from model_runner import (
    generate_multi, self_judge_single, get_session_log, get_global_log,
    model_status, DEFAULT_MODELS, AVAILABLE_MODELS,
)

CUSTOM_CSS = """
.gradio-container {max-width: 1280px !important;}
.model-card {border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; margin: 6px 0;}
.model-name {font-weight: bold; color: #2563eb; font-size: 1.1em;}
"""

CHALLENGE_PROMPTS = [
    "A 3 kg cart moving at 4 m/s collides with a stationary 2 kg cart. They stick together. What is the final velocity? Show work.",
    "How much energy to heat 500g water from 20°C to 80°C? c = 4.18 J/(g·°C). Answer in joules.",
    "A particle moves at 0.8c. What is its Lorentz factor γ? Show work.",
    "Solve: 3x + 2y = 12, 6x + 4y = 25. Show work.",
    "A 10Ω resistor has 2A current. What is the power dissipated? Show work.",
    "Maximize profit: Revenue depends on Price, Price depends on Demand, Demand depends on Revenue. Find optimal Price.",
]

# challenge → (reference answer, verifier type)
CHALLENGE_REFS = {
    CHALLENGE_PROMPTS[0]: ("2.4 m/s", "si"),
    CHALLENGE_PROMPTS[1]: ("125400 J", "si"),
    CHALLENGE_PROMPTS[2]: ("1.6667", "si"),
    CHALLENGE_PROMPTS[3]: ("", "ill_posed"),
    CHALLENGE_PROMPTS[4]: ("40 W", "si"),
    CHALLENGE_PROMPTS[5]: ("", "ill_posed"),
}

_PLACEHOLDER_PREFIXES = ("[", "等待")


def _is_blank(resp: str) -> bool:
    """True when a response box holds no real model output."""
    return not resp or not resp.strip() or resp.strip().startswith(_PLACEHOLDER_PREFIXES)


def _strip_latex(text):
    text = text.replace("\\[", "").replace("\\]", "").replace("\\boxed{", "")
    text = text.replace("\\(", "").replace("\\)", "").replace("\\text{", " ")
    text = text.replace("\\,", " ").replace("\\cdot", "*").replace("\\frac", "")
    text = text.replace("\\times", "*").replace("\\approx", "=").replace("\\gamma", "")
    text = text.replace("\\varepsilon", "").replace("\\Phi", "Phi").replace("\\Delta", "")
    text = text.replace("\\left", "").replace("\\right", "").replace("{", "").replace("}", "")
    text = text.replace("\\\\", "\\")
    return text


# Spelled-out unit names an LLM uses in prose ("2.4 meters per second"), mapped
# to their symbols so extraction does not falsely abstain on a correct answer.
_SPELLED_UNITS = [
    (r"meters?\s+per\s+second\s+squared", "m/s^2"),
    (r"meters?\s+per\s+second", "m/s"),
    (r"kilometers?\s+per\s+hour", "km/h"),
    (r"\bjoules?\b", "J"),
    (r"\bnewtons?\b", "N"),
    (r"\bwatts?\b", "W"),
    (r"\bkilograms?\b", "kg"),
    (r"\bpascals?\b", "Pa"),
    (r"\bvolts?\b", "V"),
    (r"\bteslas?\b", "T"),
    (r"\bwebers?\b", "Wb"),
    (r"\bseconds?\b", "s"),
    (r"\bmeters?\b", "m"),
]


def _normalize_units(text: str) -> str:
    for pattern, symbol in _SPELLED_UNITS:
        text = re.sub(pattern, symbol, text, flags=re.IGNORECASE)
    return text


def _extract(text, vtype):
    if not text or not text.strip():
        return ""
    cleaned = _normalize_units(_strip_latex(text))
    lines = [l.strip() for l in cleaned.strip().splitlines() if l.strip()]
    # number + unit
    for line in reversed(lines[-5:]):
        m = re.search(r"([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*(m/s\^?2|m/s²|m/s|km/h|J|N|W|kg|Pa|s\b|m\b|V\b|T\b|Wb|°C)", line)
        if m:
            return f"{m.group(1)} {m.group(2).replace('²', '^2')}"
    # bare number after =
    for line in reversed(lines[-5:]):
        m = re.search(r"=\s*([-+]?\d+\.?\d*)\s*$", line)
        if m:
            return m.group(1)
    # bare number in a short line
    for line in reversed(lines[-5:]):
        c = _strip_latex(line).strip().rstrip(".")
        m = re.search(r"([-+]?\d+\.?\d*)\s*$", c)
        if m and len(c) < 30:
            return m.group(1)
    # symbolic
    for line in reversed(lines[-5:]):
        c = _strip_latex(line).replace(" ", "")
        if re.search(r"[a-z]\^?2|[a-z]\*\*2", c, re.I):
            c = re.sub(r"^(.*?[:=])", "", c).replace("\\", "")
            if c:
                return c[:40]
    last = lines[-1] if lines else cleaned.strip()
    return last[:60]


def _verify(vtype, candidate, reference, full_text):
    if vtype == "ill_posed":
        return verify_ill_posed(_strip_latex(full_text)).to_dict()
    if not candidate or not candidate.strip():
        return {"verdict": "abstain", "reasonCode": "no_answer", "reason": "No answer extracted."}
    candidate = _strip_latex(candidate).strip()
    if vtype == "si":
        return verify_si(candidate, reference)
    if vtype == "symbolic":
        return verify_symbolic(candidate, _strip_latex(reference).strip())
    return {"verdict": "abstain", "reason": "unknown"}


def _split_steps(text: str) -> list[str]:
    """Split a model answer into reasoning steps for step-level checking.

    Prefers explicit numbered steps; falls back to non-empty lines.
    """
    if not text:
        return []
    cleaned = _normalize_units(_strip_latex(text))
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r"^\s*(?:step\s*)?\d{1,2}[\.\):]", l, re.I)]
    steps = numbered if len(numbered) >= 2 else lines
    return steps[:20]


# Unit tokens an answer attaches to a numeric result. The step checker reduces
# arithmetic only, and treats "12 / 5 = 2.4 m/s" as symbolic/compound — so every
# realistic step abstained. We strip a trailing unit for the ARITHMETIC check
# only; dimensional correctness is the SI verifier's job (step ④), not this one.
_UNIT_TOKEN = (
    r"(?:m/s\^?2|m/s²|m/s|km/h|kg\s*[*·]\s*m/s|N\s*[*·]\s*m|J/\(?g[·*]?°?C\)?|"
    r"°C|kg|Wb|Pa|J|N|W|V|T|A|Hz|rad|s|m)"
)
# Case-sensitive, and the unit must directly follow a NUMBER. Matching
# case-insensitively made the velocity variable "v" look like the volt unit "V"
# and shredded "v = 12 / 5 = 2.4" into "= 12 / 5 = 2.4".
_TRAILING_UNIT = re.compile(r"(?<=\d)\s*" + _UNIT_TOKEN + r"\s*$")


def _strip_trailing_units(step: str) -> str:
    """Remove a trailing unit from each side of an equation in a step."""
    parts = step.split("=")
    return "=".join(_TRAILING_UNIT.sub("", p).rstrip() or p for p in parts)


def render_step_report(text: str) -> str:
    """Per-step verdicts as markdown, with the first failing step called out.

    Pure function of the text so it is testable without Gradio or a network.
    """
    steps = _split_steps(text)
    if not steps:
        return "_No steps to check — generate an answer first._"
    verdicts = check_steps([_strip_trailing_units(s) for s in steps])
    if not verdicts:
        return "_No checkable steps found._"
    # StepVerdict is frozen, so the original text is re-attached at render time
    # rather than mutated — the UI shows the step as the model wrote it.
    originals = {v.index: steps[v.index] for v in verdicts if v.index < len(steps)}
    summary = summarize(verdicts)

    first_error = next((v for v in verdicts if v.verdict == ERROR), None)
    head = (
        f"**{summary['verified']} ✅ verified · {summary['error']} ❌ error · "
        f"{summary['unchecked']} ⏸️ unchecked** (of {summary['total']})"
    )
    if first_error is not None:
        head += f"\n\n> ❌ **First error at step {first_error.index + 1}** — {first_error.summary}"
    else:
        head += "\n\n> No step-level contradiction found. Unchecked steps are **not** a pass."

    rows = ["", "| # | | step | finding |", "|---:|:--:|---|---|"]
    for v in verdicts:
        step_text = (originals.get(v.index) or v.text or "").replace("|", "\\|")
        if len(step_text) > 70:
            step_text = step_text[:70] + "…"
        note = (v.summary or "").replace("|", "\\|")
        rows.append(f"| {v.index + 1} | {v.icon} | {step_text} | {note} |")
    return head + "\n" + "\n".join(rows)


def _short_name(model_id):
    parts = model_id.split("/")
    name = parts[-1] if len(parts) > 1 else model_id
    return name.replace("-Instruct", "").replace("-it", "")


def build_app():
    with gr.Blocks(title="验证边界 · Verification Frontier", css=CUSTOM_CSS, theme=gr.themes.Soft()) as app:
        session_id = gr.State(value=lambda: uuid.uuid4().hex)

        gr.Markdown("""
        # 🛡️ 验证边界 · Verification Frontier
        ### 安全捕获 LLM 科学推理中的逻辑错误 / Safely catching logic errors in LLM scientific reasoning

        **一个提示 → 多个 LLM 并行回答 → 每个回答走完整流程：生成 → 自检 → 步骤验证 → 最终裁决**
        **One prompt → several LLMs answer in parallel → each answer runs
        Generate → Self-Judge → Step-Verify → Final Verdict.**

        > 🔑 **要看的重点 / What to watch for:** 模型自信地给出错误答案，它**自己的**自检说"正确"，
        > 而确定性验证器仍然拒绝它。
        > A model states a wrong answer, its **own** self-judge calls it correct, and the
        > deterministic verifier rejects it anyway. That gap is the point.

        GOAI 2026 · AI for Research · Open Exploration
        """)

        with gr.Tabs():
            # ═══ Tab 1: Multi-Model Challenge ═══
            with gr.Tab("🎯 多模型对比 / Multi-Model"):
                gr.Markdown("""
                ## 🎯 同一问题，多个 LLM 同时回答 / Same Question, Multiple LLMs
                选择模型与挑战题 → 「生成」→ 「自检」/「步骤验证」/「验证全部」。
                Pick models and a challenge → Generate → then Self-Judge, Step-Verify, or Verify All.
                """)

                model_select = gr.CheckboxGroup(
                    choices=AVAILABLE_MODELS,
                    value=DEFAULT_MODELS,
                    label="🤖 选择模型 / Models (2 preselected — more models = slower)",
                )

                with gr.Row():
                    challenge = gr.Dropdown(
                        choices=CHALLENGE_PROMPTS,
                        value=CHALLENGE_PROMPTS[0],
                        label="📝 选择挑战题 / Select Challenge",
                        scale=4,
                    )
                    gen_btn = gr.Button("🤖 生成 / Generate All", variant="primary", scale=1)

                with gr.Row():
                    ref_box = gr.Textbox("2.4 m/s", label="参考答案 / Reference", scale=1)
                    vtype_box = gr.Textbox("si", label="验证器 / Verifier", scale=1)

                def _on_challenge_change(prompt):
                    return CHALLENGE_REFS.get(prompt, ("", "si"))

                challenge.change(_on_challenge_change, inputs=[challenge], outputs=[ref_box, vtype_box])

                # One column per AVAILABLE model; visibility follows the checkbox group.
                columns, responses, verdicts_out, judges_out, steps_out = {}, {}, {}, {}, {}

                with gr.Row():
                    for model in AVAILABLE_MODELS:
                        visible = model in DEFAULT_MODELS
                        with gr.Column(visible=visible) as col:
                            short = _short_name(model)
                            gr.Markdown(f"### 🤖 {short}")
                            resp_box = gr.Textbox(
                                label="① 回答 / Response", lines=10, interactive=False,
                                placeholder=f"等待 {short} 回答...",
                            )
                            judge_btn = gr.Button("② 🔎 自检 / Self-Judge", size="sm")
                            judge_box = gr.Textbox(
                                label="② 自检 / Self-Assessment (the model grading itself)",
                                lines=4, interactive=False,
                            )
                            step_btn = gr.Button("③ 🪜 步骤验证 / Step-Verify", size="sm")
                            step_box = gr.Markdown("_③ 逐步确定性检查 / deterministic per-step check_")
                            verdict_box = gr.JSON(label="④ 最终裁决 / Final Verdict")

                        columns[model] = col
                        responses[model] = resp_box
                        verdicts_out[model] = verdict_box
                        judges_out[model] = judge_box
                        steps_out[model] = step_box

                        # Bind per-model handlers HERE, where the widgets are in
                        # scope. A previous revision built these buttons but never
                        # called .click(), so Self-Judge silently did nothing.
                        def _make_judge(mid):
                            def _j(prompt, resp, sid):
                                if _is_blank(resp):
                                    return "[Generate first]"
                                return self_judge_single(mid, prompt, resp, session_id=sid)
                            return _j

                        judge_btn.click(
                            _make_judge(model),
                            inputs=[challenge, resp_box, session_id],
                            outputs=judge_box,
                        )

                        def _step_check(resp):
                            if _is_blank(resp):
                                return "_Generate an answer first._"
                            return render_step_report(resp)

                        step_btn.click(_step_check, inputs=[resp_box], outputs=step_box)

                def _toggle_columns(selected):
                    return [gr.update(visible=(m in selected)) for m in AVAILABLE_MODELS]

                model_select.change(
                    _toggle_columns,
                    inputs=[model_select],
                    outputs=[columns[m] for m in AVAILABLE_MODELS],
                )

                def _gen(prompt, selected, sid):
                    selected = selected or DEFAULT_MODELS
                    results = generate_multi(prompt, list(selected), session_id=sid)
                    out = []
                    for model in AVAILABLE_MODELS:
                        if model in selected:
                            out.append(results.get(model, {}).get("response", "[no response]"))
                        else:
                            out.append("")
                    return out

                gen_btn.click(
                    _gen,
                    inputs=[challenge, model_select, session_id],
                    outputs=[responses[m] for m in AVAILABLE_MODELS],
                )

                verify_btn = gr.Button("④ 🔬 验证全部 / Verify All", variant="primary")

                def _verify_all(prompt, ref, vtype, selected, *resps):
                    selected = selected or DEFAULT_MODELS
                    out = []
                    for model, resp in zip(AVAILABLE_MODELS, resps):
                        if model not in selected:
                            out.append({"verdict": "skipped", "reason": "model not selected"})
                            continue
                        if _is_blank(resp):
                            out.append({
                                "verdict": "abstain", "reasonCode": "no_response",
                                "reason": "Generate first.",
                            })
                            continue
                        candidate = _extract(resp, vtype)
                        out.append(_verify(vtype, candidate, ref, resp))
                    return out

                verify_btn.click(
                    _verify_all,
                    inputs=[challenge, ref_box, vtype_box, model_select] + [responses[m] for m in AVAILABLE_MODELS],
                    outputs=[verdicts_out[m] for m in AVAILABLE_MODELS],
                )

            # ═══ Tab 2: Custom Prompt ═══
            with gr.Tab("✏️ 自定义 / Custom"):
                gr.Markdown("## ✏️ 自定义提示 / Custom Prompt\n输入任何问题，所选模型同时回答。")
                custom_prompt = gr.Textbox(label="提示 / Prompt", value="Solve: -2x > 6. Show your work.", lines=2)
                custom_models = gr.CheckboxGroup(
                    choices=AVAILABLE_MODELS, value=DEFAULT_MODELS, label="🤖 模型 / Models",
                )
                custom_gen = gr.Button("🤖 生成 / Generate", variant="primary")
                with gr.Row():
                    custom_ref = gr.Textbox("-3", label="参考 / Reference")
                    custom_vtype = gr.Dropdown(["si", "symbolic", "ill_posed"], value="symbolic", label="验证器")

                custom_resp, custom_verdict, custom_step = {}, {}, {}
                with gr.Row():
                    for model in AVAILABLE_MODELS:
                        with gr.Column():
                            gr.Markdown(f"### {_short_name(model)}")
                            cb = gr.Textbox(label="Response", lines=8, interactive=False)
                            csb = gr.Button("🪜 Step-Verify", size="sm")
                            csm = gr.Markdown("_per-step check_")
                            cv = gr.JSON(label="Verdict")
                        custom_resp[model] = cb
                        custom_verdict[model] = cv
                        custom_step[model] = csm

                        def _cstep(resp):
                            if _is_blank(resp):
                                return "_Generate an answer first._"
                            return render_step_report(resp)

                        csb.click(_cstep, inputs=[cb], outputs=csm)

                def _gen_custom(prompt, selected, sid):
                    selected = selected or DEFAULT_MODELS
                    results = generate_multi(prompt, list(selected), session_id=sid)
                    return [
                        results.get(m, {}).get("response", "[error]") if m in selected else ""
                        for m in AVAILABLE_MODELS
                    ]

                custom_gen.click(
                    _gen_custom,
                    inputs=[custom_prompt, custom_models, session_id],
                    outputs=[custom_resp[m] for m in AVAILABLE_MODELS],
                )

                custom_verify = gr.Button("🔬 Verify All", variant="primary")

                def _verify_custom(ref, vt, selected, *resps):
                    selected = selected or DEFAULT_MODELS
                    out = []
                    for model, r in zip(AVAILABLE_MODELS, resps):
                        if model not in selected:
                            out.append({"verdict": "skipped", "reason": "model not selected"})
                            continue
                        if _is_blank(r):
                            out.append({"verdict": "abstain", "reason": "no response"})
                            continue
                        out.append(_verify(vt, _extract(r, vt), ref, r))
                    return out

                custom_verify.click(
                    _verify_custom,
                    inputs=[custom_ref, custom_vtype, custom_models] + [custom_resp[m] for m in AVAILABLE_MODELS],
                    outputs=[custom_verdict[m] for m in AVAILABLE_MODELS],
                )

            # ═══ Tab 3: Manual Test ═══
            with gr.Tab("🔍 手动 / Manual"):
                gr.Markdown("## 🔍 手动验证 / Manual Verification\n直接测试确定性验证器，无需模型调用。")
                with gr.Row():
                    si_c = gr.Textbox("9.8 m/s^2", label="candidate")
                    si_r = gr.Textbox("9.8 m/s", label="reference")
                gr.Button("🔍 Check").click(verify_si, [si_c, si_r], gr.JSON(label="verdict"))
                with gr.Row():
                    sy_c = gr.Textbox("(x-1)^2", label="candidate")
                    sy_r = gr.Textbox("(x+1)^2", label="reference")
                gr.Button("🔍 Check").click(verify_symbolic, [sy_c, sy_r], gr.JSON(label="verdict"))
                gr.Markdown("### 病态检测 / Ill-Posed")
                ill_in = gr.Textbox("x + y = 3, x + y = 5", label="problem")
                gr.Button("🔍 Check").click(lambda t: verify_ill_posed(t).to_dict(), [ill_in], gr.JSON(label="verdict"))
                gr.Markdown("### 🪜 步骤验证 / Step-Verify any reasoning")
                step_in = gr.Textbox(
                    "1. p = 3*4 = 12 kg*m/s\n2. total mass = 3 + 2 = 5 kg\n3. v = 12 / 5 = 2.6 m/s",
                    label="reasoning (one step per line)", lines=4,
                )
                step_md = gr.Markdown()
                gr.Button("🪜 Check steps").click(render_step_report, [step_in], step_md)

            # ═══ Tab 4: Log ═══
            with gr.Tab("📋 日志 / Log"):
                gr.Markdown("每一次模型调用都被记录 / Every model call is logged.")
                with gr.Row():
                    st_btn = gr.Button("🔄 状态")
                    st_out = gr.JSON(label="Status", value=lambda: model_status())
                    sl_btn = gr.Button("📋 本会话")
                    sl_out = gr.JSON(label="Session Log")
                    gl_btn = gr.Button("🌐 全部")
                    gl_out = gr.JSON(label="Global Log")
                st_btn.click(lambda: model_status(), outputs=st_out)
                sl_btn.click(lambda sid: get_session_log(sid) or [{"note": "no calls yet"}],
                             inputs=[session_id], outputs=sl_out)
                gl_btn.click(lambda: get_global_log(15), outputs=gl_out)

            # ═══ Tab 5: Results ═══
            with gr.Tab("📊 结果 / Results"):
                gr.Markdown("""
                ## 📊 证据汇总 / Evidence Summary

                > ⚠️ **每个数字都要读它的限定 / Read each number with its caveat.**
                > 这些是**仪器证据**（验证器是真实且失效闭合的），**不是**模型能力、能力提升或竞赛成绩。
                > These are **instrument** results — evidence that the verifiers are real and
                > fail-closed. They are **not** model-capability, capability-uplift, or
                > contest-performance claims.

                > 🔑 **核心结果 / Central result — 实测可判定边界 (measured boundary).**
                > 在**三个外部语料**上测量，全程无模型参与：
                > 自然语言推理（PRM800K，24,254 条 OpenAI 人工标签）**~0.1%**；
                > OlympiadBench 物理（ACL 2024，对归一化器为**留出集**）**58.1%**；
                > 带单位的物理量（SciBench，409 道题）**83.4%**。
                > **覆盖率随材料的「带量纲比例」变化。**
                > Three external corpora, no model in the loop: **~0.1 %** on
                > natural-language reasoning, **58.1 %** on OlympiadBench physics
                > (held out), **83.4 %** on unit-bearing quantities.
                > Reach tracks the **dimensional fraction** of the material.

                | 指标 / Metric | 结果 / Result | 这个数字的限定 / What limits it |
                |---|---|---|
                | **外部：自然语言推理 / External: NL reasoning** | **~0.1%** (4/6,080) | PRM800K 人工标注，弃权 99.67%，误拒率仅 0.016%。稳健，但几乎没有召回。<br>External human labels; abstains 99.67%; false rejections 0.016%. Sound, almost no recall. |
                | **外部：带单位的量 / External: unit-bearing** | **83.4%** (341/409) | SciBench 教科书答案；可判定率**等于**可表示率——凡能解析者判定全对。原始 LaTeX 仅 22.7%：**限制来自格式而非物理**。<br>Decidable **equals** representable. Raw LaTeX scores 22.7% — format, not physics, is the limit. |
                | 构念效度梯度 / Construct-validity gradient | 100% → 73.4% → **~0.1%** | 我们自己植入 → 盲写留出 → 外部人工标签。此前的数字描述的是我们自己的出题方式。<br>Our own categories → blind-authored → external. The earlier numbers described our own test-writing. |
                | 植入错误自检 / Planted self-test | 67/67 (100%) | 错误由我们植入，且属于验证器**设计要检测**的类别。这是仪器正确性，不是对未见模型错误的捕获率。<br>Errors planted by us in categories the verifiers were built to detect — instrument correctness, **not** a catch-rate on unseen model errors. |
                | 病态问题弃权率 / Ill-posed abstention | **30/30 (100%)** | 同一检测器对 **10/10 良构对照**也弃权（误报率 1.0，审计 status=FAIL）。检测器能识别病态，**不能**确认良构。<br>The same detector also abstains on **10/10 well-posed controls** (false-alarm rate 1.0, audit status **FAIL**). It detects ill-posedness; it **cannot** confirm well-posedness. |
                | LLM-judge vs 确定性 / vs deterministic | 40% vs 95%（并集 100%） | LLM-judge 是**模拟的**，不是真实评判模型的实测基线。<br>The LLM judge is **simulated** — an illustrative contrast, **not** a measured baseline against a real judge model. |
                | 自我修正错误下降 / Self-correction | 83.6% | 仅**修正**模式：模型可修复被捕获的错误，但 `canSelfAccept:false` —— 永不自行确认。<br>Revision-only: the model may fix a **caught** error but `canSelfAccept:false` — it never confirms a step itself. |
                | 判定覆盖率 / Decision coverage | **15.66%** | 其余 84% 报告为 `abstain`，从不报告为"未发现错误"。这是诚实的边界，不是隐藏的通过。<br>The other 84% is reported `abstain`, never "no error found". |
                | Stage A (GPU, Qwen2.5-7B) | 23/24 | **结构化输出/模式/策略合规**证据，单次运行、单模型、单种子。1 条格式错误的 Lean 响应被**保留**且未重跑。**不是**能力或竞赛成绩。<br>Structured-output/schema/policy compliance only; single run, single model, single seed. One malformed Lean response **retained, not re-run**. |

                `candidateOnly:true` · `canClaimAGI:false` · `winnerLevelEligible:false` · `capabilityClaim:false`

                🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)
                """)

        gr.Markdown(
            "---\n⚠️ 本 Demo 通过 HF Inference API 进行**实时模型调用**；确定性验证器本身离线运行。\n"
            "This demo makes **live model calls** via the HF Inference API; the deterministic "
            "verifiers themselves run offline.\n\n"
            "`candidateOnly:true` · `canClaimAGI:false` · "
            "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)"
        )
    return app


if __name__ == "__main__":
    build_app().launch()
