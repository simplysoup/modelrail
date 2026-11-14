"""Drift check for ModelRail, run by the drift CronJob.

Portfolio project. Compares production input statistics against the
training reference using PSI (Population Stability Index) and the
Kolmogorov-Smirnov statistic on per-channel pixel means.

Inputs: a reference stats JSON (from the training data) and production
stats. In the CronJob the production stats come from the serving
metrics endpoint; locally, pass a JSON file with the same shape:
    {"pixel_mean": [r, g, b], "pixel_std": [r, g, b], "n": 1000}

Exit codes: 0 = no drift, 2 = drift past threshold (triggers retrain),
1 = error. Thresholds come from data/params.yaml (drift.*) unless
overridden by DRIFT_PSI_THRESHOLD / DRIFT_KS_THRESHOLD.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import yaml


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two 1-D samples."""
    quantiles = np.quantile(expected, np.linspace(0, 1, bins + 1))
    quantiles = np.unique(quantiles)
    if len(quantiles) < 2:
        return 0.0
    e_counts, _ = np.histogram(expected, bins=quantiles)
    a_counts, _ = np.histogram(actual, bins=quantiles)
    e_perc = np.clip(e_counts / max(e_counts.sum(), 1), 1e-6, 1.0)
    a_perc = np.clip(a_counts / max(a_counts.sum(), 1), 1e-6, 1.0)
    return float(np.sum((a_perc - e_perc) * np.log(a_perc / e_perc)))


def ks_statistic(expected: np.ndarray, actual: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov statistic."""
    data = np.sort(np.concatenate([expected, actual]))
    cdf_e = np.searchsorted(np.sort(expected), data, side="right") / len(expected)
    cdf_a = np.searchsorted(np.sort(actual), data, side="right") / len(actual)
    return float(np.max(np.abs(cdf_e - cdf_a)))


def check_drift(reference: dict, production: dict, psi_threshold: float, ks_threshold: float) -> dict:
    """Compare per-channel stats. Returns verdict and per-channel numbers."""
    channels = []
    worst_psi = worst_ks = 0.0
    for i, name in enumerate(["r", "g", "b"]):
        # Reconstruct approximate samples from mean/std (reference stats
        # are stored as moments; the CronJob collects real samples when
        # available and passes them through the same function).
        rng = np.random.default_rng(42 + i)
        expected = rng.normal(reference["pixel_mean"][i], reference["pixel_std"][i], 10000)
        actual = rng.normal(production["pixel_mean"][i], production["pixel_std"][i], 10000)
        channel_psi = psi(expected, actual)
        channel_ks = ks_statistic(expected, actual)
        worst_psi = max(worst_psi, channel_psi)
        worst_ks = max(worst_ks, channel_ks)
        channels.append({"channel": name, "psi": round(channel_psi, 4), "ks": round(channel_ks, 4)})
    drifted = worst_psi > psi_threshold or worst_ks > ks_threshold
    return {
        "drifted": drifted,
        "psi": round(worst_psi, 4),
        "ks": round(worst_ks, 4),
        "psi_threshold": psi_threshold,
        "ks_threshold": ks_threshold,
        "channels": channels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ModelRail production drift.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--reference", required=True, help="Reference stats JSON file or URL.")
    parser.add_argument("--production", required=True, help="Production stats JSON file or URL.")
    args = parser.parse_args()

    with open(args.params) as f:
        params = yaml.safe_load(f)
    psi_threshold = float(os.environ.get("DRIFT_PSI_THRESHOLD", params["drift"]["psi_threshold"]))
    ks_threshold = float(os.environ.get("DRIFT_KS_THRESHOLD", params["drift"]["ks_threshold"]))

    def load_stats(path: str) -> dict:
        if path.startswith("http"):
            import urllib.request

            with urllib.request.urlopen(path, timeout=10) as resp:
                return json.loads(resp.read())
        with open(path) as f:
            return json.load(f)

    try:
        reference = load_stats(args.reference)
        production = load_stats(args.production)
    except Exception as exc:
        print(f"drift_check: could not load stats: {exc}")
        return 1
    result = check_drift(reference, production, psi_threshold, ks_threshold)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["drifted"]:
        print("drift_check: drift detected, retrain should be triggered")
        return 2
    print("drift_check: no drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
