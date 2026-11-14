# ModelRail inference service. Portfolio project.
# Multi-stage, slim, non-root. The model file is NOT baked into the image:
# it is mounted at runtime (MODEL_PATH) or fetched from GCS (MODEL_GCS_URI),
# so a new model version ships without rebuilding the image.
# Build from the repo root: docker build -f serve/Dockerfile -t modelrail-serve .
# Run: docker run -p 8000:8000 -e MODEL_PATH=/models/model-int8.onnx \
#        -v $PWD/models/run:/models modelrail-serve

FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
# hadolint: pinned base image tag above; no apt packages are installed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_PATH=/models/model-int8.onnx \
    MODEL_VERSION=candidate
WORKDIR /app
COPY --from=builder /install /usr/local
COPY serve/app.py ./serve/app.py
RUN groupadd -r modelrail && useradd -r -g modelrail -d /app modelrail \
    && mkdir -p /models /tmp/modelrail-model \
    && chown -R modelrail:modelrail /app /models /tmp/modelrail-model \
    && chmod -R a+rX /app
USER modelrail
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# Graceful shutdown: uvicorn handles SIGTERM and drains in-flight requests.
CMD ["uvicorn", "serve.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
