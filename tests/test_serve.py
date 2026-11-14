"""Tests for serve/app.py request validation (no model file needed).

/healthz must answer even when no model is loaded. /predict validation
is exercised through _decode_image, which is the pure validation step
before any ONNX call, so these tests do not need a model file.
"""

import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from serve.app import _decode_image, PredictRequest, app


def test_healthz_answers_without_model():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers["X-Model-Version"] == "candidate"


def test_readyz_is_503_without_model():
    client = TestClient(app)
    resp = client.get("/readyz")
    assert resp.status_code == 503


def test_decode_pixels_accepts_valid_input():
    req = PredictRequest(pixels=[128.0] * (32 * 32 * 3))
    arr = _decode_image(req)
    assert arr.shape == (32, 32, 3)
    assert arr.dtype == np.float32


def test_decode_pixels_rejects_wrong_length():
    req = PredictRequest(pixels=[1.0] * 100)
    with pytest.raises(Exception):
        _decode_image(req)


def test_decode_pixels_rejects_out_of_range():
    req = PredictRequest(pixels=[999.0] * (32 * 32 * 3))
    with pytest.raises(Exception):
        _decode_image(req)


def test_decode_image_b64_accepts_valid_png():
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8)).save(buf, format="PNG")
    req = PredictRequest(image_b64=base64.b64encode(buf.getvalue()).decode())
    arr = _decode_image(req)
    assert arr.shape == (32, 32, 3)


def test_decode_image_b64_rejects_garbage():
    req = PredictRequest(image_b64="not-base64!!!")
    with pytest.raises(Exception):
        _decode_image(req)


def test_predict_request_requires_exactly_one_input():
    with pytest.raises(Exception):
        PredictRequest(image_b64="abc", pixels=[1.0] * (32 * 32 * 3))
    with pytest.raises(Exception):
        PredictRequest()
