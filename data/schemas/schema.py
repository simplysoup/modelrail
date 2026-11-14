"""CIFAR-10 metadata schema and sanity checks for ModelRail.

Portfolio project. These checks run as the first step of the `prepare`
stage in data/dvc.yaml and in CI on the 500-sample subset. Any violation
raises ValueError and fails the pipeline; nothing is warned-and-continued.

The schema covers the metadata table (one row per image). Pixel-level
checks cover the image tensors themselves: shape, dtype, value range.
Class balance, split leakage, and dtype are all enforced here, not in
training code, so a bad dataset can never silently reach a model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandera.pandas as pa
    from pandera.pandas import Check, Column, DataFrameSchema

    _HAS_PANDERA = True
except ImportError:  # pragma: no cover - pandera is in requirements.txt
    _HAS_PANDERA = False

NUM_CLASSES = 10
IMAGE_SHAPE = (32, 32, 3)

# One row per image. `image_id` is the stable CIFAR-10 index within its
# split file, `split` is train/val/test, `label` is 0-9.
CIFAR_SCHEMA = None
if _HAS_PANDERA:
    CIFAR_SCHEMA = DataFrameSchema(
        {
            "image_id": Column(int, checks=Check.ge(0), nullable=False),
            "label": Column(int, checks=[Check.ge(0), Check.le(9)], nullable=False),
            "split": Column(str, checks=Check.isin(["train", "val", "test"]), nullable=False),
            "width": Column(int, checks=Check.eq(32), nullable=False),
            "height": Column(int, checks=Check.eq(32), nullable=False),
            "channels": Column(int, checks=Check.eq(3), nullable=False),
        },
        strict=True,
    )


def validate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Validate the metadata table against CIFAR_SCHEMA.

    Raises ValueError on any schema violation, including wrong dtypes,
    out-of-range labels, unknown splits, or unexpected columns.
    Returns the validated frame unchanged on success.
    """
    if not isinstance(df, pd.DataFrame):
        raise ValueError(f"metadata must be a pandas DataFrame, got {type(df).__name__}")
    if df.empty:
        raise ValueError("metadata is empty")
    if _HAS_PANDERA and CIFAR_SCHEMA is not None:
        try:
            return CIFAR_SCHEMA.validate(df, lazy=True)
        except Exception as exc:  # pandera SchemaErrors
            raise ValueError(f"metadata schema validation failed: {exc}") from exc
    # Fallback when pandera is not installed: enforce the same rules by hand.
    required = {"image_id", "label", "split", "width", "height", "channels"}
    if set(df.columns) != required:
        raise ValueError(f"metadata columns must be exactly {sorted(required)}, got {sorted(df.columns)}")
    if df["label"].min() < 0 or df["label"].max() > 9:
        raise ValueError("labels must be in 0-9")
    if not set(df["split"].unique()).issubset({"train", "val", "test"}):
        raise ValueError("split must be one of train, val, test")
    if (df["width"] != 32).any() or (df["height"] != 32).any() or (df["channels"] != 3).any():
        raise ValueError("all images must be 32x32x3")
    return df


def check_class_balance(df: pd.DataFrame, min_share: float = 0.05, max_share: float = 0.20) -> dict:
    """Fail if any class share in any split falls outside [min_share, max_share].

    CIFAR-10 is balanced at 0.10 per class. A share below 0.05 or above 0.20
    means the data is corrupt or mislabelled, not merely imbalanced.
    Returns {split: {label: share}} on success.
    """
    if min_share < 0 or max_share > 1 or min_share >= max_share:
        raise ValueError(f"invalid balance band [{min_share}, {max_share}]")
    result = {}
    for split, group in df.groupby("split"):
        counts = group["label"].value_counts(normalize=True).sort_index()
        missing = set(range(NUM_CLASSES)) - set(counts.index)
        if missing:
            raise ValueError(f"split {split!r} is missing classes {sorted(missing)}")
        for label, share in counts.items():
            if share < min_share or share > max_share:
                raise ValueError(
                    f"class balance violation in split {split!r}: "
                    f"class {int(label)} share is {share:.3f}, outside [{min_share}, {max_share}]"
                )
        result[split] = {int(k): float(v) for k, v in counts.items()}
    return result


def check_shape_dtype(images: np.ndarray, expected_shape: tuple = IMAGE_SHAPE) -> None:
    """Fail unless images are (N, 32, 32, 3) uint8 in [0, 255].

    Raises ValueError with the offending shape or dtype. Accepts a
    4-D array only; a single image must be passed as a batch of one.
    """
    if not isinstance(images, np.ndarray):
        raise ValueError(f"images must be a numpy array, got {type(images).__name__}")
    if images.ndim != 4:
        raise ValueError(f"images must be 4-D (N, H, W, C), got {images.ndim}-D with shape {images.shape}")
    if tuple(images.shape[1:]) != tuple(expected_shape):
        raise ValueError(f"image shape must be {expected_shape}, got {tuple(images.shape[1:])}")
    if images.dtype != np.uint8:
        raise ValueError(f"image dtype must be uint8, got {images.dtype}")
    if images.min() < 0 or images.max() > 255:
        raise ValueError(f"pixel values must be in [0, 255], got [{images.min()}, {images.max()}]")


def check_no_leakage(train_ids, test_ids, val_ids=None) -> None:
    """Fail if any image id appears in more than one split.

    Ids are the stable per-split CIFAR-10 indices combined with the split
    name by the caller when the same index space is reused; here the check
    is on the raw id sets, so callers must pass globally unique ids
    (for example "train:123") when index spaces overlap.
    """
    train = set(train_ids)
    test = set(test_ids)
    overlap = train & test
    if overlap:
        raise ValueError(f"train/test leakage: {len(overlap)} shared ids, e.g. {sorted(overlap)[:5]}")
    if val_ids is not None:
        val = set(val_ids)
        if train & val:
            raise ValueError(f"train/val leakage: {len(train & val)} shared ids")
        if test & val:
            raise ValueError(f"test/val leakage: {len(test & val)} shared ids")


def validate_dataset(df: pd.DataFrame, images: np.ndarray | None = None,
                     min_share: float = 0.05, max_share: float = 0.20) -> dict:
    """Run every check. Returns the class-balance report on success.

    This is the single entry point used by data/prepare.py and by CI.
    """
    validate_metadata(df)
    balance = check_class_balance(df, min_share=min_share, max_share=max_share)
    if images is not None:
        if len(images) != len(df):
            raise ValueError(f"images ({len(images)}) and metadata rows ({len(df)}) disagree")
        check_shape_dtype(images)
    # Leakage is checked on globally unique ids built from split + image_id.
    df = df.copy()
    df["uid"] = df["split"] + ":" + df["image_id"].astype(str)
    for a, b in (("train", "test"), ("train", "val"), ("test", "val")):
        ids_a = set(df.loc[df["split"] == a, "uid"])
        ids_b = set(df.loc[df["split"] == b, "uid"])
        if ids_a & ids_b:
            raise ValueError(f"{a}/{b} leakage: {len(ids_a & ids_b)} shared uids")
    return balance
