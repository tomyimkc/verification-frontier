#!/usr/bin/env python3
"""Hugging Face Space entry point for the Verification Frontier demo.

Self-contained: vendors demo.py, units.py, v2/, and demo_logic so the Space
runs without the rest of the repository. Zero network / zero model calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gradio as gr  # noqa: E402

from demo_logic import (  # noqa: E402
    frontier_gate_preview,
    public_status,
    reference_episode,
    verify_si,
    verify_symbolic,
)

HEADER = """
# 验证边界 · Verification Frontier

**安全扩展科学 Agent 的验证边界 / Safely Expanding the Verification Frontier of Scientific Agents**

GOAI 2026 AI for Research · Open Exploration · 公开免登录演示 (public no-login demo)

> 这是一个**确定性环境/工具演示**，不是确认性结果、能力声明、验证器扩展或竞赛成绩。
> 零网络调用，零模型调用。
"""


def build_app() -> gr.Blocks:
    with gr.Blocks(title="验证边界 · Verification Frontier") as app:
        gr.Markdown(HEADER)
        status = public_status()
        gr.JSON(status, label="状态 / Status (claim ceiling + seal)")

        gr.Markdown("## SI 物理验证 / SI physics verification")
        with gr.Row():
            si_cand = gr.Textbox(value="9.8 m/s^2", label="候选 / candidate")
            si_ref = gr.Textbox(value="9.8 m/s", label="参考 / reference")
        si_out = gr.JSON(label="裁决 / verdict")
        si_btn = gr.Button("验证 / Verify")
        si_btn.click(verify_si, inputs=[si_cand, si_ref], outputs=si_out)

        gr.Markdown("## 符号验证 / Symbolic verification")
        with gr.Row():
            sy_cand = gr.Textbox(value="x^2+2*x+1", label="候选 / candidate")
            sy_ref = gr.Textbox(value="(x+1)^2", label="参考 / reference")
        sy_out = gr.JSON(label="裁决 / verdict")
        sy_btn = gr.Button("验证 / Verify")
        sy_btn.click(verify_symbolic, inputs=[sy_cand, sy_ref], outputs=sy_out)

        gr.Markdown("## 参照回合 / Reference episode")
        with gr.Row():
            ep_problem = gr.Textbox(value="free-fall", label="问题 / problem")
            ep_policy = gr.Dropdown(
                ["always-answer", "abstain-all", "single-shot", "scripted-refine"],
                value="scripted-refine",
                label="策略 / policy",
            )
        ep_out = gr.JSON(label="回合步骤 / episode steps")
        ep_btn = gr.Button("运行回合 / Run episode")
        ep_btn.click(reference_episode, inputs=[ep_problem, ep_policy], outputs=ep_out)

        gr.Markdown("## 前沿门预览 / Frontier gate preview (synthetic)")
        gr.Markdown(
            "公开合成示例上的门机制预览。未通过的门保持弃权。 / Gate mechanics on a "
            "public synthetic example. Abstention is preserved unless every gate passes."
        )
        with gr.Row():
            owner = gr.Checkbox(value=False, label="所有者审批 / owner approve")
            expert = gr.Checkbox(value=False, label="专家 AI 审批 / expert-AI approve")
            tests = gr.Checkbox(value=False, label="测试通过 / tests pass")
        gate_out = gr.JSON(label="门结果 / gate result")
        gate_btn = gr.Button("预览 / Preview")
        gate_btn.click(frontier_gate_preview, inputs=[owner, expert, tests], outputs=gate_out)

        gr.Markdown(
            "---\n`candidateOnly:true` · `canClaimAGI:false` · "
            "`winnerLevelEligible:false` · `winnerLevelGateMet:false`"
        )
    return app


if __name__ == "__main__":
    build_app().launch()
