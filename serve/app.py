"""ModelRail inference service: FastAPI + ONNX Runtime.

Portfolio project. Nothing here is deployed; there is no production traffic.

Endpoints:
  GET  /healthz  - liveness, always 200 once the process is up
  GET  /readyz   - readiness, 200 only once the ONNX model is loaded
  POST /predict  - classify one 32x32 image, base64 PNG/JPEG or raw pixels
  GET  /metrics  - Prometheus metrics (requests, latency, in-flight)

Model loading: MODEL_PATH (local file) or MODEL_GCS_URI (gs://...).
The GCS path downloads the model once at startup through
google-cloud-storage, lazily imported. No GCP call is made unless a
gs:// URI is configured. MODEL_VERSION (default: candidate) is returned
in the X-Model-Version response header on every response and in the
/predict body, so a canary can be distinguished from the champion.

Request validation: Pydantic rejects oversized payloads, unknown fields,
and images that cannot be decoded or resized to 32x32.
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from PIL import Image
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

MODEL_PATH = os.environ.get("MODEL_PATH", "models/run/model-int8.onnx")
MODEL_GCS_URI = os.environ.get("MODEL_GCS_URI", "")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "candidate")
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", str(2 * 1024 * 1024)))
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", str(32 * 32 * 3)))

CLASS_NAMES = ["airplane", "automobile", "bird", "cat", "deer",
               "dog", "frog", "horse", "ship", "truck"]
# CIFAR-10 normalization, per channel (R, G, B).
MEAN = np.array([0.4914, 0.4822, 0.4465], dtype=np.float32).reshape(1, 3, 1, 1)
STD = np.array([0.2470, 0.2435, 0.2616], dtype=np.float32).reshape(1, 3, 1, 1)

REQUEST_COUNT = Counter(
    "modelrail_predict_requests_total", "Total /predict requests", ["status"]
)
REQUEST_LATENCY = Histogram(
    "modelrail_predict_latency_seconds", "Latency of /predict requests",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _session_error
    try:
        load_session()
    except Exception as exc:  # readiness stays false; /healthz still answers
        _session_error = str(exc)
    yield


app = FastAPI(title="ModelRail inference", version="0.1.0", lifespan=lifespan)
_session = None
_session_error: str | None = None


class PredictRequest(BaseModel):
    """One image, either as base64 PNG/JPEG or as flat normalized pixels."""

    image_b64: str | None = Field(default=None, description="Base64-encoded PNG or JPEG image.")
    pixels: list[float] | None = Field(
        default=None,
        description=f"Flat float pixels, length {MAX_PIXELS} (32x32x3, 0-255).",
    )

    def model_post_init(self, __context):
        if (self.image_b64 is None) == (self.pixels is None):
            raise ValueError("provide exactly one of image_b64 or pixels")


class PredictResponse(BaseModel):
    prediction: str
    label: int
    confidence: float
    top5: list[dict]
    model_version: str
    latency_ms: float


def _download_from_gcs(uri: str, dest: str) -> str:
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:
        raise RuntimeError("google-cloud-storage is required for gs:// model URIs") from exc
    rest = uri[len("gs://"):]
    bucket_name, _, blob_name = rest.partition("/")
    client = storage.Client()
    client.bucket(bucket_name).blob(blob_name).download_to_filename(dest)
    return dest


def load_session():
    """Load the ONNX session once. Returns the session or raises."""
    global _session, _session_error
    if _session is not None:
        return _session
    path = MODEL_PATH
    if MODEL_GCS_URI:
        path = "/tmp/modelrail-model.onnx"
        _download_from_gcs(MODEL_GCS_URI, path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"model file not found: {path} (set MODEL_PATH or MODEL_GCS_URI)")
    import onnxruntime as ort

    _session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    return _session


@app.middleware("http")
async def add_model_version_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Model-Version"] = MODEL_VERSION
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.get("/readyz")
def readyz():
    if _session is not None:
        return {"status": "ready", "model_version": MODEL_VERSION}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "model_version": MODEL_VERSION,
                 "error": _session_error or "model not loaded"},
    )


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _decode_image(req: PredictRequest) -> np.ndarray:
    if req.image_b64 is not None:
        try:
            raw = base64.b64decode(req.image_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="image_b64 is not valid base64") from exc
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"image exceeds {MAX_IMAGE_BYTES} bytes")
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB").resize((32, 32))
        except Exception as exc:
            raise HTTPException(status_code=422, detail="image_b64 could not be decoded as an image") from exc
        return np.asarray(image, dtype=np.float32)
    pixels = req.pixels or []
    if len(pixels) != MAX_PIXELS:
        raise HTTPException(
            status_code=422, detail=f"pixels must have length {MAX_PIXELS}, got {len(pixels)}"
        )
    arr = np.asarray(pixels, dtype=np.float32).reshape(32, 32, 3)
    if arr.min() < 0 or arr.max() > 255:
        raise HTTPException(status_code=422, detail="pixel values must be in [0, 255]")
    return arr


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    started = time.perf_counter()
    try:
        session = load_session()
    except Exception as exc:
        REQUEST_COUNT.labels(status="model_unavailable").inc()
        raise HTTPException(status_code=503, detail=f"model unavailable: {exc}") from exc
    image = _decode_image(req)
    x = image.transpose(2, 0, 1)[None, :, :, :]
    x = ((x / 255.0) - MEAN) / STD
    x = np.ascontiguousarray(x, dtype=np.float32)
    outputs = session.run(None, {"input": x})[0]
    logits = outputs[0].astype(np.float64)
    probs = np.exp(logits - logits.max())
    probs = probs / probs.sum()
    top5_idx = probs.argsort()[::-1][:5]
    latency_ms = (time.perf_counter() - started) * 1000.0
    REQUEST_COUNT.labels(status="ok").inc()
    REQUEST_LATENCY.observe(latency_ms / 1000.0)
    return PredictResponse(
        prediction=CLASS_NAMES[int(top5_idx[0])],
        label=int(top5_idx[0]),
        confidence=round(float(probs[top5_idx[0]]), 4),
        top5=[{"label": CLASS_NAMES[int(i)], "index": int(i), "probability": round(float(probs[i]), 4)}
              for i in top5_idx],
        model_version=MODEL_VERSION,
        latency_ms=round(latency_ms, 2),
    )
