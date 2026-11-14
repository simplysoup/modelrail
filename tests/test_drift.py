"""Tests for train/drift_check.py: PSI and KS drift detection."""

import numpy as np

from train.drift_check import check_drift, ks_statistic, psi


def _stats(mean, std):
    return {"pixel_mean": mean, "pixel_std": std, "n": 1000}


def test_no_drift_when_stats_match():
    ref = _stats([0.49, 0.48, 0.45], [0.25, 0.24, 0.26])
    result = check_drift(ref, ref, psi_threshold=0.2, ks_threshold=0.1)
    assert result["drifted"] is False


def test_drift_when_brightness_shifts():
    ref = _stats([0.49, 0.48, 0.45], [0.25, 0.24, 0.26])
    shifted = _stats([0.85, 0.84, 0.82], [0.25, 0.24, 0.26])
    result = check_drift(ref, shifted, psi_threshold=0.2, ks_threshold=0.1)
    assert result["drifted"] is True
    assert result["psi"] > 0.2 or result["ks"] > 0.1


def test_psi_is_zero_for_identical_samples():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 10000)
    assert psi(x, x) == 0.0


def test_ks_is_zero_for_identical_samples():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 1000)
    assert ks_statistic(x, x) == 0.0


def test_ks_is_large_for_shifted_samples():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 1000)
    y = rng.normal(3, 1, 1000)
    assert ks_statistic(x, y) > 0.5
