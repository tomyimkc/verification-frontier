# Public hosted demo

This directory provides a no-login Gradio interface for the public GOAI
verification environment.

It exposes only:

- the public SI and symbolic verifiers;
- deterministic v1 reference episodes;
- a synthetic preview of the owner + expert-AI + executable-test gate;
- public confirmatory seal metadata.

It does **not** contain the private confirmatory seed, exact task payload, gold
labels, model credentials, human decisions, or confirmatory outcomes.

## Local

From the submission-package root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r hosted-demo/requirements.txt
.venv/bin/python hosted-demo/healthcheck.py
.venv/bin/python hosted-demo/app.py
```

## Docker / Hugging Face Space

Use the submission-package root as the Docker build context:

```bash
docker build -f hosted-demo/Dockerfile -t goai-verification-frontier .
docker run --rm -p 7860:7860 goai-verification-frontier
```

The root `.dockerignore` excludes the private confirmatory boundary and build
artifacts. Deployment remains an owner-controlled external action.

`candidateOnly:true`; `canClaimAGI:false`.
