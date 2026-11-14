"""Evaluate a trained ModelRail checkpoint on the CIFAR-10 test set.

Portfolio project. Run via DVC (`dvc repro`, stage `evaluate`) or directly:
    python -m train.evaluate --params data/params.yaml \
        --checkpoint models/run/checkpoint.pt --data data/processed \
        --out models/run/eval.json

Writes accuracy overall and per class, plus a pass/fail verdict against
params.evaluate.min_accuracy. Exit code is non-zero when accuracy is
below the threshold, so the CI model gate fails the pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from train.train import build_model  # noqa: E402

CLASS_NAMES = ["airplane", "automobile", "bird", "cat", "deer",
               "dog", "frog", "horse", "ship", "truck"]


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a ModelRail checkpoint.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data", default="data/processed")
    parser.add_argument("--out", default="models/run/eval.json")
    parser.add_argument("--min-accuracy", type=float, default=None)
    args = parser.parse_args()

    params = load_params(args.params)
    data_cfg, eval_cfg = params["data"], params["evaluate"]
    min_accuracy = args.min_accuracy if args.min_accuracy is not None else eval_cfg["min_accuracy"]

    import torch
    from torch.utils.data import DataLoader, TensorDataset

    images = np.load(os.path.join(args.data, "test-images.npy"))
    labels = np.load(os.path.join(args.data, "test-labels.npy"))
    mean = torch.tensor(data_cfg["mean"]).view(1, 3, 1, 1)
    std = torch.tensor(data_cfg["std"]).view(1, 3, 1, 1)
    x = torch.from_numpy(images).permute(0, 3, 1, 2).float() / 255.0
    x = (x - mean) / std
    loader = DataLoader(
        TensorDataset(x, torch.from_numpy(labels)), batch_size=256, shuffle=False
    )

    model = build_model(data_cfg["num_classes"], pretrained=False)
    payload = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model_state"] if "model_state" in payload else payload)
    model.eval()

    correct = np.zeros(10, dtype=int)
    total = np.zeros(10, dtype=int)
    with torch.no_grad():
        for batch_x, batch_y in loader:
            preds = model(batch_x).argmax(1).numpy()
            for pred, label in zip(preds, batch_y.numpy()):
                total[label] += 1
                if pred == label:
                    correct[label] += 1
    accuracy = float(correct.sum() / max(total.sum(), 1))
    per_class = {
        CLASS_NAMES[i]: round(float(correct[i] / max(total[i], 1)), 4) for i in range(10)
    }
    result = {
        "accuracy": round(accuracy, 4),
        "per_class_accuracy": per_class,
        "n_test": int(total.sum()),
        "min_accuracy": min_accuracy,
        "passed": accuracy >= min_accuracy,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"evaluate: accuracy {accuracy:.4f} (threshold {min_accuracy}); passed={result['passed']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
