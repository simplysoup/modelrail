# serve/

Portfolio project. FastAPI + ONNX Runtime inference service.

## Run locally

```bash
pip install -r requirements.txt
MODEL_PATH=models/run/model-int8.onnx MODEL_VERSION=candidate \
  uvicorn serve.app:app --host 127.0.0.1 --port 8000
```

## Endpoints

- `GET /healthz` - liveness
- `GET /readyz` - readiness, 200 only after the model loads
- `POST /predict` - `{"image_b64": "<base64 PNG/JPEG>"}` or `{"pixels": [...3072 floats...]}`; returns the predicted class, confidence, top 5, model version, and latency
- `GET /metrics` - Prometheus metrics

Every response carries an `X-Model-Version` header.

## Model loading

- `MODEL_PATH` - local ONNX file (default `models/run/model-int8.onnx`)
- `MODEL_GCS_URI` - `gs://...` model URI, downloaded once at startup; no GCP call is made unless this is set
- `MODEL_VERSION` - version label from the MLflow registry (default `candidate`)
