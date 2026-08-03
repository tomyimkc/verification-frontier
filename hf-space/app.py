#!/usr/bin/env python3
"""验证边界 · Verification Frontier — multi-model comparison demo.

One prompt → multiple LLMs answer in parallel → extract & verify each.
Clean, judge-friendly UI. Shows how different models make different errors.
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
from model_runner import generate_multi, self_judge_single, get_session_log, get_global_log, model_status, DEFAULT_MODELS

CUSTOM_CSS = """
.gradio-container {max-width: 1200px !important;}
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


def _strip_latex(text):
    text = text.replace("\\[","").replace("\\]","").replace("\\boxed{","")
    text = text.replace("\\(","").replace("\\)","").replace("\\text{"," ")
    text = text.replace("\\,"," ").replace("\\cdot","*").replace("\\frac","")
    text = text.replace("\\times","*").replace("\\approx","=").replace("\\gamma","")
    text = text.replace("\\varepsilon","").replace("\\Phi","Phi").replace("\\Delta","")
    text = text.replace("\\left","").replace("\\right","").replace("{","").replace("}","")
    text = text.replace("\\\\","\\")
    return text


def _extract(text, vtype):
    if not text or not text.strip(): return ""
    cleaned = _strip_latex(text)
    lines = [l.strip() for l in cleaned.strip().splitlines() if l.strip()]
    # number + unit
    for line in reversed(lines[-5:]):
        m = re.search(r"([-+]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*(m/s\^?2|m/s²|m/s|km/h|J|N|W|kg|Pa|s\b|m\b|V\b|T\b|Wb|°C)", line)
        if m: return f"{m.group(1)} {m.group(2).replace('²','^2')}"
    # bare number after =
    for line in reversed(lines[-5:]):
        m = re.search(r"=\s*([-+]?\d+\.?\d*)\s*$", line)
        if m: return m.group(1)
    # bare number in short line
    for line in reversed(lines[-5:]):
        c = _strip_latex(line).strip().rstrip(".")
        m = re.search(r"([-+]?\d+\.?\d*)\s*$", c)
        if m and len(c) < 30: return m.group(1)
    # symbolic
    for line in reversed(lines[-5:]):
        c = _strip_latex(line).replace(" ","")
        if re.search(r"[a-z]\^?2|[a-z]\*\*2", c, re.I):
            c = re.sub(r"^(.*?[:=])","",c).replace("\\","")
            if c: return c[:40]
    last = lines[-1] if lines else cleaned.strip()
    return last[:60]


def _verify(vtype, candidate, reference, full_text):
    if vtype == "ill_posed":
        return verify_ill_posed(_strip_latex(full_text)).to_dict()
    if not candidate or not candidate.strip():
        return {"verdict":"abstain","reasonCode":"no_answer","reason":"No answer extracted."}
    candidate = _strip_latex(candidate).strip()
    if vtype == "si":
        return verify_si(candidate, reference)
    if vtype == "symbolic":
        return verify_symbolic(candidate, _strip_latex(reference).strip())
    return {"verdict":"abstain","reason":"unknown"}


def _short_name(model_id):
    parts = model_id.split("/")
    name = parts[-1] if len(parts)>1 else model_id
    return name.replace("-Instruct","").replace("-it","")


def build_app():
    with gr.Blocks(title="验证边界 · Verification Frontier", css=CUSTOM_CSS, theme=gr.themes.Soft()) as app:
        session_id = gr.State(value=lambda: uuid.uuid4().hex)

        gr.Markdown("""
        # 🛡️ 验证边界 · Verification Frontier
        ### 安全捕获 LLM 科学推理中的逻辑错误
        **一个提示 → 多个 LLM 同时回答 → 提取与验证每个回答**
        评委可以看到不同模型犯不同的错误，以及确定性验证器如何捕获它们。
        **One prompt → multiple LLMs answer in parallel → extract & verify each response.**
        GOAI 2026 · AI for Research · Open Exploration
        """)

        with gr.Tabs():
            # ═══ Tab 1: Multi-Model Challenge ═══
            with gr.Tab("🎯 多模型对比 / Multi-Model"):
                gr.Markdown("""
                ## 🎯 同一问题，多个 LLM 同时回答 / Same Question, Multiple LLMs
                选择一个挑战题，点击「生成」后 3 个模型同时回答。然后点击「验证」看每个回答的裁决。
                Pick a challenge, click Generate — 3 models answer in parallel. Then click Verify to see each verdict.
                """)

                with gr.Row():
                    challenge = gr.Dropdown(
                        choices=CHALLENGE_PROMPTS,
                        value=CHALLENGE_PROMPTS[0],
                        label="📝 选择挑战题 / Select Challenge",
                        scale=4,
                    )
                    gen_btn = gr.Button("🤖 生成 / Generate All", variant="primary", scale=1)

                # Reference + verifier type (hidden, set by challenge selection)
                ref_box = gr.Textbox("2.4 m/s", label="参考答案 / Reference", visible=True, scale=1)
                vtype_box = gr.Textbox("si", label="验证器 / Verifier", visible=True, scale=1)

                def _on_challenge_change(prompt):
                    refs = {
                        CHALLENGE_PROMPTS[0]: ("2.4 m/s", "si"),
                        CHALLENGE_PROMPTS[1]: ("125400 J", "si"),
                        CHALLENGE_PROMPTS[2]: ("1.6667", "si"),
                        CHALLENGE_PROMPTS[3]: ("", "ill_posed"),
                        CHALLENGE_PROMPTS[4]: ("40 W", "si"),
                        CHALLENGE_PROMPTS[5]: ("", "ill_posed"),
                    }
                    ref, vt = refs.get(prompt, ("", "si"))
                    return ref, vt

                challenge.change(_on_challenge_change, inputs=[challenge], outputs=[ref_box, vtype_box])

                # Model output columns
                model_responses = {}
                model_extracts = {}
                model_verdicts = {}

                with gr.Row():
                    for model in DEFAULT_MODELS:
                        with gr.Column():
                            short = _short_name(model)
                            gr.Markdown(f"### 🤖 {short}")
                            resp_box = gr.Textbox(label="回答 / Response", lines=10, interactive=False,
                                                   placeholder=f"等待 {short} 回答...")
                            extract_box = gr.Textbox(label="提取 / Extracted", interactive=False,
                                                      placeholder="自动提取", visible=False)
                            verdict_box = gr.JSON(label="裁决 / Verdict")
                            judge_btn = gr.Button(f"🔎 自检 / Self-Judge", size="sm")
                            judge_box = gr.Textbox(label="自检 / Self-Assessment", lines=4,
                                                    interactive=False, visible=False)
                            model_responses[model] = resp_box
                            model_extracts[model] = extract_box
                            model_verdicts[model] = verdict_box

                # Generate handler
                def _gen(prompt, sid):
                    results = generate_multi(prompt, DEFAULT_MODELS, session_id=sid)
                    outputs = []
                    for model in DEFAULT_MODELS:
                        r = results.get(model, {})
                        resp = r.get("response", "[no response]")
                        outputs.append(resp)
                        outputs.append(_extract(resp, "si"))  # placeholder, real extract on verify
                    return outputs

                gen_outputs = []
                for model in DEFAULT_MODELS:
                    gen_outputs.append(model_responses[model])
                    gen_outputs.append(model_extracts[model])
                gen_btn.click(_gen, inputs=[challenge, session_id], outputs=gen_outputs)

                # Verify handler — verify each model's response
                verify_btn = gr.Button("🔬 验证全部 / Verify All", variant="primary")

                def _verify_all(*args):
                    # args = [prompt, ref, vtype, resp1, resp2, resp3, sid]
                    prompt = args[0]
                    ref = args[1]
                    vtype = args[2]
                    sid = args[-1]
                    responses = args[3:3+len(DEFAULT_MODELS)]
                    outputs = []
                    for resp in responses:
                        if not resp or resp.startswith("[") or resp.startswith("等待"):
                            outputs.append({"verdict":"abstain","reasonCode":"no_response","reason":"Generate first."})
                            continue
                        candidate = _extract(resp, vtype)
                        verdict = _verify(vtype, candidate, ref, resp)
                        outputs.append(verdict)
                    return outputs

                verify_inputs = [challenge, ref_box, vtype_box] + [model_responses[m] for m in DEFAULT_MODELS] + [session_id]
                verify_outputs = [model_verdicts[m] for m in DEFAULT_MODELS]
                verify_btn.click(_verify_all, inputs=verify_inputs, outputs=verify_outputs)

                # Self-judge handlers
                for model in DEFAULT_MODELS:
                    def _make_judge(mid):
                        def _j(prompt, resp, sid):
                            if not resp or resp.startswith("[") or resp.startswith("等待"):
                                return "[Generate first]"
                            return self_judge_single(mid, prompt, resp, session_id=sid)
                        return _j
                    judge_btn_for_model = [w for w in app.children if hasattr(w, 'children') and any(
                        hasattr(c, 'click') for c in (w.children if isinstance(w.children, list) else [w.children])
                    )]
                    # Simplified: just use the last created judge_btn reference
                    # (Gradio builds these linearly so the last judge_btn is for the last model)

            # ═══ Tab 2: Custom Prompt ═══
            with gr.Tab("✏️ 自定义 / Custom"):
                gr.Markdown("## ✏️ 自定义提示 / Custom Prompt\n输入任何问题，3 个模型同时回答。")
                custom_prompt = gr.Textbox(
                    label="提示 / Prompt",
                    value="Solve: -2x > 6. Show your work.",
                    lines=2,
                )
                custom_gen = gr.Button("🤖 生成 / Generate", variant="primary")
                custom_ref = gr.Textbox("-3", label="参考 / Reference")
                custom_vtype = gr.Dropdown(["si","symbolic","ill_posed"], value="si", label="验证器")

                with gr.Row():
                    custom_outs = {}
                    for model in DEFAULT_MODELS:
                        with gr.Column():
                            gr.Markdown(f"### {_short_name(model)}")
                            cb = gr.Textbox(label="Response", lines=8, interactive=False)
                            cv = gr.JSON(label="Verdict")
                            custom_outs[model] = (cb, cv)

                def _gen_custom(prompt, sid):
                    results = generate_multi(prompt, DEFAULT_MODELS, session_id=sid)
                    return [results.get(m,{}).get("response","[error]") for m in DEFAULT_MODELS]

                custom_gen.click(_gen_custom, inputs=[custom_prompt, session_id],
                                 outputs=[custom_outs[m][0] for m in DEFAULT_MODELS])

                custom_verify = gr.Button("🔬 Verify All")
                def _verify_custom(prompt, ref, vt, *resps):
                    outs = []
                    for r in resps:
                        if not r or r.startswith("["): outs.append({"verdict":"abstain","reason":"no response"}); continue
                        c = _extract(r, vt)
                        outs.append(_verify(vt, c, ref, r))
                    return outs
                custom_verify.click(_verify_custom,
                    inputs=[custom_prompt, custom_ref, custom_vtype] + [custom_outs[m][0] for m in DEFAULT_MODELS],
                    outputs=[custom_outs[m][1] for m in DEFAULT_MODELS])

            # ═══ Tab 3: Manual Test ═══
            with gr.Tab("🔍 手动 / Manual"):
                gr.Markdown("## 🔍 手动验证 / Manual Verification")
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

            # ═══ Tab 4: Log ═══
            with gr.Tab("📋 日志 / Log"):
                with gr.Row():
                    st_btn = gr.Button("🔄 状态")
                    st_out = gr.JSON(label="Status", value=lambda: model_status())
                    sl_btn = gr.Button("📋 本会话")
                    sl_out = gr.JSON(label="Session Log")
                    gl_btn = gr.Button("🌐 全部")
                    gl_out = gr.JSON(label="Global Log")
                st_btn.click(lambda: model_status(), outputs=st_out)
                sl_btn.click(lambda sid: get_session_log(sid) or [{"note":"no calls yet"}], inputs=[session_id], outputs=sl_out)
                gl_btn.click(lambda: get_global_log(15), outputs=gl_out)

            # ═══ Tab 5: Results ═══
            with gr.Tab("📊 结果 / Results"):
                gr.Markdown("""
                ## 📊 证据汇总 / Evidence Summary
                | 指标 | 结果 |
                |---|---|
                | 逻辑错误捕获率 | **67/67 (100%)** |
                | 病态问题弃权率 | **30/30 (100%)** |
                | LLM-judge vs 确定性 | 40% vs 95% (union 100%) |
                | 自我修正错误下降 | 83.6% |
                | Stage A (GPU, Qwen2.5-7B) | 23/24 |

                `candidateOnly:true` · `canClaimAGI:false`
                🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)
                """)

        gr.Markdown("---\n`candidateOnly:true` · `canClaimAGI:false` · "
                     "🔗 [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)")
    return app


if __name__ == "__main__":
    build_app().launch()
