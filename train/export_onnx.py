"""Export a trained ModelRail checkpoint to ONNX.

Portfolio project. Run via DVC (`dvc repro`, stage `export`) or directly:
    python -m train.export_onnx --params data/params.yaml \
        --checkpoint models/run/checkpoint.pt --out models/run/model.onnx

Exports MobileNetV3-small with a dynamic batch axis at the opset in
params.yaml, then verifies the file with onnx.checker and records the
file size in export-metrics.json. The ONNX file is what serve/ loads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from train.train import build_model  # noqa: E402


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a ModelRail checkpoint to ONNX.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", default="models/run/model.onnx")
    args = parser.parse_args()

    params = load_params(args.params)
    data_cfg, export_cfg = params["data"], params["export"]

    import torch

    model = build_model(data_cfg["num_classes"], pretrained=False)
    payload = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model_state"] if "model_state" in payload else payload)
    model.eval()

    dummy = torch.randn(1, 3, data_cfg["image_size"], data_cfg["image_size"])
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    torch.onnx.export(
        model, dummy, args.out,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=export_cfg["onnx_opset"],
    )

    import onnx

    onnx_model = onnx.load(args.out)
    onnx.checker.check_model(onnx_model)
    size_mb = os.path.getsize(args.out) / (1024 * 1024)
    metrics = {
        "onnx_path": args.out,
        "opset": export_cfg["onnx_opset"],
        "size_mb": round(size_mb, 2),
        "size_ok": size_mb <= params["serve"]["max_model_size_mb"],
    }
    metrics_path = os.path.join(os.path.dirname(args.out) or ".", "export-metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"export_onnx: wrote {args.out} ({size_mb:.2f} MB, opset {export_cfg['onnx_opset']}); onnx.checker passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
