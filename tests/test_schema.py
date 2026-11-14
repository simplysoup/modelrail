"""Tests for data/schemas/schema.py: schema, balance, shape, leakage."""

import numpy as np
import pandas as pd
import pytest

from data.schemas.schema import (
    check_class_balance,
    check_no_leakage,
    check_shape_dtype,
    validate_dataset,
    validate_metadata,
)


def test_validate_metadata_passes_on_balanced_data(balanced_metadata):
    out = validate_metadata(balanced_metadata)
    assert len(out) == len(balanced_metadata)


def test_validate_metadata_rejects_bad_label(balanced_metadata):
    bad = balanced_metadata.copy()
    bad.loc[0, "label"] = 10
    with pytest.raises(ValueError):
        validate_metadata(bad)


def test_validate_metadata_rejects_bad_split(balanced_metadata):
    bad = balanced_metadata.copy()
    bad.loc[0, "split"] = "holdout"
    with pytest.raises(ValueError):
        validate_metadata(bad)


def test_validate_metadata_rejects_wrong_image_size(balanced_metadata):
    bad = balanced_metadata.copy()
    bad.loc[0, "width"] = 28
    with pytest.raises(ValueError):
        validate_metadata(bad)


def test_validate_metadata_rejects_empty():
    with pytest.raises(ValueError):
        validate_metadata(pd.DataFrame(columns=["image_id", "label", "split", "width", "height", "channels"]))


def test_class_balance_passes_when_balanced(balanced_metadata):
    balance = check_class_balance(balanced_metadata, min_share=0.05, max_share=0.20)
    assert balance["train"][0] == pytest.approx(0.10)


def test_class_balance_fails_when_one_class_dominates(balanced_metadata):
    skewed = balanced_metadata.copy()
    train_idx = skewed.index[skewed["split"] == "train"][:30]
    skewed.loc[train_idx, "label"] = 0
    with pytest.raises(ValueError, match="class balance violation"):
        check_class_balance(skewed)


def test_class_balance_fails_when_class_missing(balanced_metadata):
    missing = balanced_metadata[balanced_metadata["label"] != 9].copy()
    with pytest.raises(ValueError, match="missing classes"):
        check_class_balance(missing)


def test_shape_dtype_passes(synthetic_images):
    check_shape_dtype(synthetic_images)


def test_shape_dtype_rejects_wrong_shape():
    bad = np.zeros((10, 28, 28, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape must be"):
        check_shape_dtype(bad)


def test_shape_dtype_rejects_float_dtype():
    bad = np.zeros((10, 32, 32, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="dtype must be uint8"):
        check_shape_dtype(bad)


def test_no_leakage_passes_on_disjoint_ids():
    check_no_leakage([1, 2, 3], [4, 5, 6], val_ids=[7, 8])


def test_no_leakage_fails_on_overlap():
    with pytest.raises(ValueError, match="train/test leakage"):
        check_no_leakage([1, 2, 3], [3, 4, 5])


def test_validate_dataset_runs_all_checks(balanced_metadata, synthetic_images):
    balance = validate_dataset(balanced_metadata, images=synthetic_images[:100])
    assert set(balance) == {"train", "val", "test"}


def test_validate_dataset_fails_on_image_count_mismatch(balanced_metadata, synthetic_images):
    with pytest.raises(ValueError, match="disagree"):
        validate_dataset(balanced_metadata, images=synthetic_images[:10])
