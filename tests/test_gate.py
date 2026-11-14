"""Tests for train/gate.py, the four-rule model gate.

Uses a randomly initialised model, so no accuracy claim is made: the
passing case feeds the gate an eval.json with accuracy above the floor,
and the failing case feeds one below it. Parity, latency, and size are
measured for real on the exported model. Skipped when the training
stack is not installed.
"""

import json
import sys

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from train.gate import main as gate_main  # noqa: E402
from train.train import build_model  # noqa: E402


@pytest.fixture()
def gate_inputs(tmp_path):
    model = build_model(num_classes=10, pretrained=False)
    model.eval()
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save({"model_state": model.state_dict()}, checkpoint)
    onnx_path = tmp_path / "model.onnx"
    dummy = torch.randn(1, 3, 32, 32)
    torch.onnx.export(
        model, dummy, str(onnx_path),
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=13,
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rng = np.random.default_rng(0)
    images = rng.integers(0, 256, size=(200, 32, 32, 3), dtype=np.uint8)
    np.save(data_dir / "test-images.npy", images)
    eval_json = tmp_path / "eval.json"
    return {
        "checkpoint": str(checkpoint),
        "onnx": str(onnx_path),
        "data": str(data_dir),
        "eval_json": str(eval_json),
        "out": str(tmp_path / "gate.json"),
    }


def write_eval(path, accuracy):
    with open(path, "w") as f:
        json.dump({"accuracy": accuracy, "passed": accuracy >= 0.8}, f)


def run_gate(monkeypatch, inputs, accuracy, extra=None):
    write_eval(inputs["eval_json"], accuracy)
    argv = [
        "gate.py",
        "--checkpoint", inputs["checkpoint"],
        "--onnx", inputs["onnx"],
        "--onnx-fp32", inputs["onnx"],
        "--eval-json", inputs["eval_json"],
        "--data", inputs["data"],
        "--out", inputs["out"],
        "--champion-accuracy", "0.85",
        "--min-accuracy-delta", "0.01",
    ]
    if extra:
        argv += extra
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    return gate_main()


def test_gate_passes_when_all_rules_pass(monkeypatch, gate_inputs):
    assert run_gate(monkeypatch, gate_inputs, accuracy=0.9) == 0
    with open(gate_inputs["out"]) as f:
        result = json.load(f)
    assert result["passed"] is True
    assert result["onnx_parity"]["passed"] is True
    assert result["p95_latency"]["passed"] is True
    assert result["model_size"]["passed"] is True


def test_gate_fails_on_low_accuracy(monkeypatch, gate_inputs):
    assert run_gate(monkeypatch, gate_inputs, accuracy=0.1) == 1
    with open(gate_inputs["out"]) as f:
        result = json.load(f)
    assert result["passed"] is False
    assert result["accuracy"]["passed"] is False


def test_gate_fails_on_oversize_model(monkeypatch, gate_inputs):
    assert run_gate(monkeypatch, gate_inputs, accuracy=0.9,
                    extra=["--max-model-size-mb", "0.001"]) == 1
