#!/usr/bin/env python3
"""验证边界 · Verification Frontier — Hugging Face Space app.

GOAI 2026 AI for Research / Open Exploration.
A deterministic, provider-free verification-environment demo.
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

HEADER = """
# 验证边界 · Verification Frontier

**安全扩展科学 Agent 的验证边界 / Safely Expanding the Verification Frontier of Scientific Agents**

GOAI 2026 · AI for Research · Open Exploration — 公开免登录演示 / public no-login demo

> 这是一个**确定性环境/工具演示**：不是确认性结果、能力声明、验证器扩展或竞赛成绩。
> 零网络调用，零模型调用。
>
> This is a **deterministic environment/instrument demo**: not a confirmatory result,
> capability claim, verifier extension, or contest score. Zero network, zero model calls.

🔗 源代码 / Source: [github.com/tomyimkc/verification-frontier](https://github.com/tomyimkc/verification-frontier)
"""


def build_app() -> gr.Blocks:
    with gr.Blocks(title="验证边界 · Verification Frontier") as app:
        gr.Markdown(HEADER)
        gr.JSON(public_status(), label="状态 / Status (claim ceiling + seal)")

        gr.Markdown("---\n## 1 · SI 物理验证 / SI physics verification")
        with gr.Row():
            si_cand = gr.Textbox(value="9.8 m/s^2", label="候选 / candidate")
            si_ref = gr.Textbox(value="9.8 m/s", label="参考 / reference")
        si_out = gr.JSON(label="裁决 / verdict")
        gr.Button("验证 / Verify").click(verify_si, [si_cand, si_ref], si_out)
        gr.Markdown(
            "<sub>试 `9.8 m/s^2` vs `9.8 m/s` → REJECTED (量纲不符 / dimension mismatch). "
            "试 `8.91 J` vs `9.0 J` → ACCEPTED.</sub>"
        )

        gr.Markdown("## 2 · 符号验证 / Symbolic verification")
        with gr.Row():
            sy_cand = gr.Textbox(value="x^2+2*x+1", label="候选 / candidate")
            sy_ref = gr.Textbox(value="(x+1)^2", label="参考 / reference")
        sy_out = gr.JSON(label="裁决 / verdict")
        gr.Button("验证 / Verify").click(verify_symbolic, [sy_cand, sy_ref], sy_out)
        gr.Markdown(
            "<sub>试 `x^2+2*x+1` vs `(x+1)^2` → ACCEPTED (符号等价 / equivalent).</sub>"
        )

        gr.Markdown("## 3 · 参照回合 / Reference episode")
        with gr.Row():
            ep_problem = gr.Textbox(value="free-fall", label="问题 / problem")
            ep_policy = gr.Dropdown(
                ["always-answer", "abstain-all", "single-shot", "scripted-refine"],
                value="scripted-refine",
                label="策略 / policy",
            )
        ep_out = gr.JSON(label="回合步骤 / episode steps")
        gr.Button("运行回合 / Run episode").click(
            reference_episode, [ep_problem, ep_policy], ep_out
        )

        gr.Markdown(
            "## 4 · 前沿门预览 / Frontier gate preview (公开合成示例 / public synthetic)"
        )
        gr.Markdown(
            "门机制预览：任一门未通过则保持弃权（abstain）。 / "
            "Gate mechanics: abstention is preserved unless **every** gate passes."
        )
        with gr.Row():
            owner = gr.Checkbox(value=False, label="所有者审批 / owner approve")
            expert = gr.Checkbox(value=False, label="专家 AI 审批 / expert-AI approve")
            tests = gr.Checkbox(value=False, label="测试通过 / tests pass")
        gate_out = gr.JSON(label="门结果 / gate result")
        gr.Button("预览 / Preview").click(
            frontier_gate_preview, [owner, expert, tests], gate_out
        )

        gr.Markdown(
            "---\n`candidateOnly:true` · `canClaimAGI:false` · "
            "`winnerLevelEligible:false` · `winnerLevelGateMet:false`"
        )
    return app


if __name__ == "__main__":
    build_app().launch()
