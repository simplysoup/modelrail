"""Static int8 quantization of a ModelRail ONNX model.

Portfolio project. Run via DVC (`dvc repro`, stage `export`) or directly:
    python -m train.quantize --params data/params.yaml \
        --model models/run/model.onnx --data data/processed \
        --out models/run/model-int8.onnx

Static quantization needs calibration data: a subset of the training set
(params.quantize.calibration_samples) is run through the model so the
quantizer can measure activation ranges. The result is the model served
to the in-browser demo and compared against fp32 in docs/BENCHMARKS.md
(owned by another agent). Accuracy is re-checked by train/evaluate.py
style parity tests; see tests/test_parity.py for the tolerance used in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


from onnxruntime.quantization import CalibrationDataReader as _ORTCalibrationDataReader


class CalibrationDataReader(_ORTCalibrationDataReader):
    """Feeds calibration batches to onnxruntime static quantization."""

    def __init__(self, data_dir: str, params: dict, n_samples: int):
        super().__init__()
        images = np.load(os.path.join(data_dir, "train-images.npy"))[:n_samples]
        mean = np.array(params["data"]["mean"], dtype=np.float32).reshape(1, 3, 1, 1)
        std = np.array(params["data"]["std"], dtype=np.float32).reshape(1, 3, 1, 1)
        x = images.astype(np.float32).transpose(0, 3, 1, 2) / 255.0
        self.batches = [((x[i:i + 1] - mean) / std).astype(np.float32) for i in range(len(x))]
        self._index = 0

    def get_next(self):
        if self._index >= len(self.batches):
            return None
        batch = {"input": self.batches[self._index]}
        self._index += 1
        return batch

    def rewind(self):
        self._index = 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Quantize a ModelRail ONNX model to int8.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--model", required=True)
    parser.add_argument("--data", default="data/processed")
    parser.add_argument("--out", default="models/run/model-int8.onnx")
    args = parser.parse_args()

    params = load_params(args.params)
    quant_cfg = params["quantize"]

    from onnxruntime.quantization import QuantType, quantize_static

    reader = CalibrationDataReader(args.data, params, quant_cfg["calibration_samples"])
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    quantize_static(
        model_input=args.model,
        model_output=args.out,
        calibration_data_reader=reader,
        quant_format=__import__("onnxruntime.quantization", fromlist=["QuantFormat"]).QuantFormat.QDQ,
        activation_type=QuantType.QInt8,
        weight_type=QuantType.QInt8,
        per_channel=quant_cfg["per_channel"],
        reduce_range=quant_cfg["reduce_range"],
    )
    fp32_mb = os.path.getsize(args.model) / (1024 * 1024)
    int8_mb = os.path.getsize(args.out) / (1024 * 1024)
    metrics = {
        "fp32_size_mb": round(fp32_mb, 2),
        "int8_size_mb": round(int8_mb, 2),
        "size_ratio": round(int8_mb / max(fp32_mb, 1e-9), 3),
        "calibration_samples": quant_cfg["calibration_samples"],
    }
    metrics_path = os.path.join(os.path.dirname(args.out) or ".", "quantize-metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"quantize: {fp32_mb:.2f} MB fp32 -> {int8_mb:.2f} MB int8 (ratio {metrics['size_ratio']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
