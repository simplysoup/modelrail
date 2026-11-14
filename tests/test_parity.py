"""Tests for ONNX vs PyTorch output parity.

Skipped when torch, onnx, or onnxruntime are not installed, so the suite
still runs on a machine without the training stack. When they are
installed, a randomly initialised MobileNetV3-small is exported and its
ONNX outputs are compared against PyTorch on synthetic inputs.

Gate thresholds (from data/params.yaml):
  max absolute logit difference 0.001 (checked here at 1e-3)
  max mean absolute difference 0.0005
Note: a randomly initialised model is used, so no accuracy claim is made.
"""

import numpy as np
import pytest

torch = pytest.importorskip("torch")
onnxruntime = pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from train.train import build_model  # noqa: E402


@pytest.fixture(scope="module")
def exported_model(tmp_path_factory):
    model = build_model(num_classes=10, pretrained=False)
    model.eval()
    path = str(tmp_path_factory.mktemp("onnx") / "model.onnx")
    dummy = torch.randn(1, 3, 32, 32)
    torch.onnx.export(
        model, dummy, path,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=13,
    )
    return model, path


def test_onnx_matches_pytorch_within_tolerance(exported_model):
    model, path = exported_model
    session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    x = rng.standard_normal((4, 3, 32, 32)).astype(np.float32)
    with torch.no_grad():
        expected = model(torch.from_numpy(x)).numpy()
    actual = session.run(None, {"input": x})[0]
    assert actual.shape == expected.shape
    max_diff = float(np.abs(actual - expected).max())
    mean_diff = float(np.abs(actual - expected).mean())
    assert max_diff < 0.001, f"max abs diff {max_diff} exceeds 0.001"
    assert mean_diff < 0.0005, f"mean abs diff {mean_diff} exceeds 0.0005"


def test_onnx_output_shape_is_batch_dynamic(exported_model):
    _, path = exported_model
    session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
    x = np.zeros((2, 3, 32, 32), dtype=np.float32)
    out = session.run(None, {"input": x})[0]
    assert out.shape == (2, 10)
