FROM python:3.12-slim

WORKDIR /app
COPY demo.py units.py requirements.txt /app/
COPY v2/__init__.py v2/frontier.py /app/v2/
COPY v2/artifacts/synthetic-rehearsal-seal.manifest.json /app/v2/artifacts/
COPY hosted-demo/app.py hosted-demo/demo_logic.py hosted-demo/healthcheck.py \
     hosted-demo/requirements.txt /app/hosted-demo/

RUN python -m pip install --no-cache-dir \
    -r requirements.txt \
    -r hosted-demo/requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python hosted-demo/healthcheck.py >/dev/null || exit 1

CMD ["python", "hosted-demo/app.py", "--host", "0.0.0.0", "--port", "7860"]
