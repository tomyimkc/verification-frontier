# Hugging Face Space — deploy guide (owner-only)

This deploys the public no-login demo. It is an **owner-only external action**;
the AI does not perform it. The `hf-space/` directory is the self-contained Space
(verified to build a Gradio Blocks with zero network / zero model calls).

## What the Space shows

A bilingual (中文 + EN) Gradio app exposing:

1. project status + claim ceiling + synthetic-rehearsal seal validation;
2. **SI physics verification** (try `9.8 m/s^2` vs `9.8 m/s` → REJECTED dimension mismatch);
3. **symbolic verification** (try `x^2+2*x+1` vs `(x+1)^2` → ACCEPTED);
4. a **reference episode** (e.g. `free-fall` × `scripted-refine`);
5. a **frontier gate preview** on a public synthetic example — toggle owner / expert / tests
   and watch abstention persist until every gate passes.

It is a deterministic **environment/instrument demo**, not a confirmatory result,
capability claim, verifier extension, or contest score. Claim ceiling:
`candidateOnly:true`, `canClaimAGI:false`.

## Deploy steps (owner)

1. Create a free Hugging Face account if you don't have one; log in.
2. **New Space** → name it `verification-frontier` → SDK **Gradio** → license **Apache-2.0** → Public.
3. Upload the contents of this repo's `hf-space/` directory to the Space root
   (or push the `hf-space/` subdir to the Space's git: `git clone https://huggingface.co/spaces/<your-user>/verification-frontier`,
   copy `hf-space/*` in, commit, push).
4. The Space builds automatically. The **Demo 链接 / Demo URL** is then:

   ```
   https://<your-user>-verification-frontier.hf.space
   ```

   (e.g. for user `tomyimkc`: `https://tomyimkc-verification-frontier.hf.space`)

## Local preview before deploying

```bash
cd hf-space
pip install gradio sympy
python app.py
```

The Space requires no secrets, no GPU, and no model credentials.
