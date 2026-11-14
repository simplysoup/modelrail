# ModelRail training image. Portfolio project.
# Multi-stage, slim, non-root. Runs the full local pipeline stages
# (prepare -> train -> evaluate -> export -> quantize) inside the
# training Job; checkpoints go to the GCS URI passed as --checkpoint-uri.
# Build from the repo root: docker build -f train/Dockerfile -t modelrail-train .
# The entrypoint prepares the data first if data/processed is missing,
# then runs whatever command the Job passes (train by default).

FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /install /usr/local
COPY train/ ./train/
COPY data/params.yaml data/dvc.yaml ./data/
COPY data/schemas/ ./data/schemas/
COPY data/prepare.py ./data/prepare.py
COPY data/__init__.py ./data/__init__.py
COPY train/entrypoint.sh ./train/entrypoint.sh
RUN chmod +x ./train/entrypoint.sh \
    && groupadd -r modelrail && useradd -r -g modelrail -d /app modelrail \
    && mkdir -p /app/data/processed /app/models/run \
    && chown -R modelrail:modelrail /app
USER modelrail
ENTRYPOINT ["/app/train/entrypoint.sh"]
CMD ["python", "-m", "train.train", "--params", "/app/data/params.yaml", "--data", "/app/data/processed", "--out", "/app/models/run"]
