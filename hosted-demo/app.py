#!/usr/bin/env python3
"""No-login Gradio interface for the public GOAI verification environment."""
from __future__ import annotations

import argparse
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


def build_app() -> gr.Blocks:
    with gr.Blocks(title="GOAI Verification Frontier") as app:
        gr.Markdown(
            """
# Human-Gated Scientific Verification Frontier

Public, no-login instrument demo for GOAI 2026 AI for Research / Open
Exploration.

**Claim boundary:** this demonstrates deterministic verification and gate
mechanics. It does not demonstrate scientific discovery, model capability,
frontier-expansion efficacy, AGI, or a contest result.
"""
        )
        with gr.Tab("Project status"):
            status = gr.JSON(label="Public seal and claim ceiling")
            refresh = gr.Button("Refresh public status")
            refresh.click(public_status, outputs=status)
            app.load(public_status, outputs=status)

        with gr.Tab("SI verifier"):
            with gr.Row():
                si_candidate = gr.Textbox(value="9.8 m/s", label="Candidate")
                si_reference = gr.Textbox(value="9.8 m/s", label="Reference contract")
            si_run = gr.Button("Verify SI candidate")
            si_output = gr.JSON(label="Deterministic verdict")
            si_run.click(
                verify_si,
                inputs=(si_candidate, si_reference),
                outputs=si_output,
            )

        with gr.Tab("Symbolic verifier"):
            with gr.Row():
                sym_candidate = gr.Textbox(value="x^2+2*x+1", label="Candidate")
                sym_reference = gr.Textbox(value="(x+1)^2", label="Reference")
            sym_run = gr.Button("Verify symbolic equivalence")
            sym_output = gr.JSON(label="Deterministic verdict")
            sym_run.click(
                verify_symbolic,
                inputs=(sym_candidate, sym_reference),
                outputs=sym_output,
            )

        with gr.Tab("Reference episode"):
            problem = gr.Dropdown(
                choices=(
                    "free-fall",
                    "kinetic-energy",
                    "expand-square",
                    "hf01-quad",
                    "hf02-linear",
                    "riemann-zeros",
                ),
                value="free-fall",
                label="Problem",
            )
            policy = gr.Dropdown(
                choices=(
                    "always-answer",
                    "abstain-all",
                    "single-shot",
                    "scripted-refine",
                ),
                value="scripted-refine",
                label="Deterministic reference policy",
            )
            episode_run = gr.Button("Run propose → verify → act episode")
            episode_output = gr.JSON(label="JSONL-compatible steps")
            episode_run.click(
                reference_episode,
                inputs=(problem, policy),
                outputs=episode_output,
            )

        with gr.Tab("Human gate preview"):
            gr.Markdown(
                "This uses a public synthetic example, never a sealed task."
            )
            owner = gr.Checkbox(label="Owner approves candidate", value=False)
            expert = gr.Checkbox(label="Independent expert-AI approves", value=False)
            tests = gr.Checkbox(label="All declared extension tests pass", value=False)
            gate_run = gr.Button("Evaluate gate")
            gate_output = gr.JSON(label="Expansion receipt")
            gate_run.click(
                frontier_gate_preview,
                inputs=(owner, expert, tests),
                outputs=gate_output,
            )
    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    build_app().launch(
        server_name=args.host,
        server_port=args.port,
        footer_links=["gradio", "settings"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
