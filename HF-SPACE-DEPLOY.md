# Hugging Face Space — deploy / update guide

> **Status: DEPLOYED.** The Space is live at
> **https://tomyimkc-sophia-agi.hf.space** (HF repo `tomyimkc/sophia-agi`).
> It runs the lean 9-file Gradio demo with zero network / zero model calls.

# Hugging Face Space — 部署 / 更新指南

> **状态：已部署。** Space 已上线于
> **https://tomyimkc-sophia-agi.hf.space**（HF 仓库 `tomyimkc/sophia-agi`）。
> 运行精简的 9 文件 Gradio 演示，零网络 / 零模型调用。

## What the Space shows / Space 展示内容

A bilingual (中文 + EN) Gradio app exposing:

1. project status + claim ceiling + synthetic-rehearsal seal validation;
2. **SI physics verification** (try `9.8 m/s^2` vs `9.8 m/s` → REJECTED dimension mismatch);
3. **symbolic verification** (try `x^2+2*x+1` vs `(x+1)^2` → ACCEPTED);
4. a **reference episode** (e.g. `free-fall` × `scripted-refine`);
5. a **frontier gate preview** — toggle owner / expert / tests and watch abstention
   persist until every gate passes.

It is a deterministic **environment/instrument demo**, not a confirmatory result,
capability claim, verifier extension, or contest score. Claim ceiling:
`candidateOnly:true`, `canClaimAGI:false`.

## Space contents (9 files — lean) / Space 内容（9 文件 — 精简）

```
README.md                                 # HF metadata frontmatter (sdk: gradio)
app.py                                    # Gradio Blocks (bilingual UI)
demo.py, units.py, demo_logic.py          # deterministic verification environment
v2/__init__.py, v2/frontier.py            # frontier-expansion gate logic
synthetic-rehearsal-seal.manifest.json    # public seal metadata
requirements.txt                          # gradio + sympy
```

## How to update the Space / 如何更新 Space

```bash
# 1. clone the Space (needs HF login: huggingface-cli login)
git clone https://huggingface.co/spaces/tomyimkc/sophia-agi
cd sophia-agi

# 2. copy the lean package from this repo's hf-space/ over the clone
cp -R /path/to/verification-frontier/hf-space/* .

# 3. commit + push (HF auto-rebuilds on push)
git add -A
git commit -m "update demo"
git push
```

The Space rebuilds automatically (~2-3 min) and returns to `RUNNING`.

## Local preview / 本地预览

```bash
cd hf-space
pip install -r requirements.txt
python app.py
```

The Space requires no secrets, no GPU, and no model credentials.
Space 无需密钥、无需 GPU、无需模型凭证。
