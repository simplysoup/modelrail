"""Prepare CIFAR-10 for ModelRail: download, split, validate, write out.

Portfolio project. Run via DVC (`dvc repro`, stage `prepare`) or directly:
    python -m data.prepare --params data/params.yaml --out data/processed

Steps:
  1. Load CIFAR-10 with torchvision (downloads once, cached under data/raw).
  2. Split train into train/val by params.data.val_fraction.
  3. Run every check in data/schemas/schema.py; any failure aborts the run.
  4. Write train/val/test as .npy image arrays plus a metadata parquet,
     and a prepare-metrics.json with row counts, class balance, and hashes.

The data hash written here is the same hash train.py logs to MLflow, so
any model version traces back to the exact data it trained on.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.schemas.schema import validate_dataset  # noqa: E402


def data_hash(images: np.ndarray, labels: np.ndarray) -> str:
    """Stable SHA-256 over image bytes plus label bytes."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(images).tobytes())
    h.update(np.ascontiguousarray(labels).tobytes())
    return h.hexdigest()


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_cifar10(root: str):
    """Load CIFAR-10 via torchvision. Raises a clear error if unavailable."""
    try:
        from torchvision.datasets import CIFAR10
    except ImportError as exc:
        raise RuntimeError(
            "torchvision is required to download CIFAR-10. "
            "Install requirements.txt, or run the tests, which use a synthetic fixture instead."
        ) from exc
    train = CIFAR10(root=root, train=True, download=True)
    test = CIFAR10(root=root, train=False, download=True)
    train_images = np.stack([np.asarray(img) for img, _ in train]).astype(np.uint8)
    train_labels = np.array([label for _, label in train], dtype=np.int64)
    test_images = np.stack([np.asarray(img) for img, _ in test]).astype(np.uint8)
    test_labels = np.array([label for _, label in test], dtype=np.int64)
    return train_images, train_labels, test_images, test_labels


def build_metadata(images: np.ndarray, labels: np.ndarray, split: str, offset: int = 0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "image_id": np.arange(offset, offset + len(images), dtype=np.int64),
            "label": labels.astype(np.int64),
            "split": split,
            "width": 32,
            "height": 32,
            "channels": 3,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare CIFAR-10 for ModelRail.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--out", default="data/processed")
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument(
        "--subset",
        action="store_true",
        help="Cap the splits to data.ci_subset_samples (500) for fast CI runs. "
        "The cap is applied after the seeded shuffle, so class balance is kept.",
    )
    args = parser.parse_args()

    params = load_params(args.params)
    data_cfg = params["data"]
    rng = np.random.default_rng(data_cfg["seed"])

    train_images, train_labels, test_images, test_labels = load_cifar10(args.raw)

    # Train/val split, stratified by shuffling within each class is
    # unnecessary for balanced CIFAR-10; a single seeded shuffle is enough.
    perm = rng.permutation(len(train_images))
    n_val = int(len(train_images) * data_cfg["val_fraction"])
    val_idx, train_idx = perm[:n_val], perm[n_val:]

    if args.subset:
        # Every split is capped to the same n: with only 50 val rows the
        # per-class shares get noisy enough to trip the balance check
        # (e.g. 2/50 = 0.04, outside the [0.05, 0.20] band), while 500
        # rows per split keeps shares near 0.10. Still fast for CI.
        n = int(data_cfg["ci_subset_samples"])
        train_idx = train_idx[:n]
        val_idx = val_idx[:n]
        test_images = test_images[:n]
        test_labels = test_labels[:n]

    splits = {
        "train": (train_images[train_idx], train_labels[train_idx], 0),
        "val": (train_images[val_idx], train_labels[val_idx], 0),
        "test": (test_images, test_labels, 0),
    }

    os.makedirs(args.out, exist_ok=True)
    frames = []
    metrics = {"splits": {}, "data_hash": {}, "subset": bool(args.subset)}
    if args.subset:
        metrics["ci_subset_samples"] = int(data_cfg["ci_subset_samples"])
    for split, (images, labels, offset) in splits.items():
        meta = build_metadata(images, labels, split, offset)
        frames.append(meta)
        np.save(os.path.join(args.out, f"{split}-images.npy"), images)
        np.save(os.path.join(args.out, f"{split}-labels.npy"), labels)
        metrics["splits"][split] = {"rows": int(len(images))}
        metrics["data_hash"][split] = data_hash(images, labels)

    metadata = pd.concat(frames, ignore_index=True)
    balance = validate_dataset(metadata)
    metrics["class_balance"] = balance
    metadata.to_parquet(os.path.join(args.out, "metadata.parquet"), index=False)
    with open(os.path.join(args.out, "prepare-metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"prepare: wrote {len(metadata)} rows to {args.out}; schema and balance checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
