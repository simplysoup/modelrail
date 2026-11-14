"""Shared fixtures for ModelRail tests.

Portfolio project. All fixtures are synthetic: small random uint8 images
and balanced metadata, so the suite runs in seconds with no CIFAR-10
download and no GCP access.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def synthetic_images():
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, size=(100, 32, 32, 3), dtype=np.uint8)


@pytest.fixture
def balanced_metadata():
    rows = []
    for split, n in (("train", 60), ("val", 20), ("test", 20)):
        for i in range(n):
            rows.append({
                "image_id": i,
                "label": i % 10,
                "split": split,
                "width": 32,
                "height": 32,
                "channels": 3,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def tmp_checkpoint_dir(tmp_path):
    return str(tmp_path / "checkpoints")
