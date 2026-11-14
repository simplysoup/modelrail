"""ModelRail model gate: fail the pipeline unless all four rules pass.

Portfolio project. Run in CI on merge to main, after training:

    python train/gate.py --git-sha "$GITHUB_SHA" \
        --checkpoint models/run/checkpoint.pt \
        --onnx models/run/model-int8.onnx \
        --eval-json models/run/eval.json --data data/processed

The four rules, thresholds from data/params.yaml unless overridden:
  1. accuracy >= champion accuracy - tolerance (default: the champion
     accuracy comes from --champion-accuracy / CHAMPION_ACCURACY; if
     none is given, params.evaluate.min_accuracy is the floor).
  2. ONNX vs PyTorch outputs match within tolerance (max abs diff and
     mean abs diff, measured live on test samples, not trusted from a file).
     Parity is checked on the fp32 ONNX export, not the quantized one:
     int8 quantization legitimately moves outputs by far more than the
     parity tolerance, so checking parity on the int8 model would fail
     a correct export. The quantized model is what latency and size check.
  3. p95 CPU latency of the ONNX model under the threshold (measured live
     with ONNX Runtime, single-image requests).
  4. Model file size under the threshold.

Also verifies the training run is logged in MLflow under the same git
SHA (train.py logs git_sha as a run param). That check only runs when
MLFLOW_TRACKING_URI is set; without a tracking URI it prints a warning
and judges on the files alone, so local runs still gate honestly.

Exit 0 only when every rule passes. Writes models/run/gate.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def check_mlflow_run(git_sha: str) -> tuple[bool, str]:
    """True when a run logged with this git SHA exists in MLflow.

    Returns (passed, note). Skipped (passed, with a warning note) when
    no tracking URI is configured or mlflow is not installed.
    """
    uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if not uri:
        return True, "no MLFLOW_TRACKING_URI set; MLflow check skipped"
    try:
        import mlflow
    except ImportError:
        return True, "mlflow not installed; MLflow check skipped"
    try:
        mlflow.set_tracking_uri(uri)
        runs = mlflow.search_runs(
            experiment_ids=None,
            filter_string=f"params.git_sha = '{git_sha}'",
            max_results=1,
        )
        if runs is None or len(runs) == 0:
            return False, f"no MLflow run logged with git_sha={git_sha}"
        return True, f"MLflow run found for git_sha={git_sha}"
    except Exception as exc:  # noqa: BLE001 - a failed lookup must fail loudly
        return False, f"MLflow lookup failed: {exc}"


def check_accuracy(eval_json: str, floor: float) -> tuple[bool, str, float]:
    with open(eval_json) as f:
        result = json.load(f)
    accuracy = float(result["accuracy"])
    return accuracy >= floor, (
        f"accuracy {accuracy:.4f} vs floor {floor:.4f}"
    ), accuracy


def load_test_sample(data_dir: str, n: int) -> np.ndarray:
    images = np.load(os.path.join(data_dir, "test-images.npy"))[:n]
    return images


def normalised(images: np.ndarray, mean, std) -> np.ndarray:
    import torch

    x = torch.from_numpy(images).permute(0, 3, 1, 2).float() / 255.0
    m = torch.tensor(mean).view(1, 3, 1, 1)
    s = torch.tensor(std).view(1, 3, 1, 1)
    return ((x - m) / s).numpy()


def check_parity(checkpoint: str, onnx_path: str, data_dir: str, params: dict,
                 max_abs: float, max_mean: float) -> tuple[bool, str]:
    import torch
    import onnxruntime

    from train.train import build_model

    data_cfg = params["data"]
    images = load_test_sample(data_dir, 200)
    x = normalised(images, data_cfg["mean"], data_cfg["std"])

    model = build_model(data_cfg["num_classes"], pretrained=False)
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model_state"] if "model_state" in payload else payload)
    model.eval()
    with torch.no_grad():
        expected = model(torch.from_numpy(x)).numpy()

    session = onnxruntime.InferenceSession(
        onnx_path, providers=["CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name
    actual = session.run(None, {input_name: x})[0]

    max_diff = float(np.abs(actual - expected).max())
    mean_diff = float(np.abs(actual - expected).mean())
    ok = max_diff <= max_abs and mean_diff <= max_mean
    return ok, (
        f"ONNX vs PyTorch: max abs diff {max_diff:.6f} (limit {max_abs}), "
        f"mean abs diff {mean_diff:.6f} (limit {max_mean})"
    )


def check_latency(onnx_path: str, data_dir: str, params: dict,
                  max_p95_ms: float, samples: int = 100) -> tuple[bool, str]:
    import onnxruntime

    data_cfg = params["data"]
    images = load_test_sample(data_dir, samples)
    x = normalised(images, data_cfg["mean"], data_cfg["std"])

    session = onnxruntime.InferenceSession(
        onnx_path, providers=["CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name
    for i in range(10):  # warmup, not timed
        session.run(None, {input_name: x[i : i + 1]})
    times = []
    for i in range(samples):
        start = time.perf_counter()
        session.run(None, {input_name: x[i : i + 1]})
        times.append((time.perf_counter() - start) * 1000.0)
    p50 = float(np.percentile(times, 50))
    p95 = float(np.percentile(times, 95))
    return p95 <= max_p95_ms, (
        f"ONNX CPU latency over {samples} requests: "
        f"p50 {p50:.1f} ms, p95 {p95:.1f} ms (limit {max_p95_ms:.0f} ms)"
    )


def check_size(onnx_path: str, max_mb: float) -> tuple[bool, str, float]:
    size_mb = os.path.getsize(onnx_path) / (1024 * 1024)
    return size_mb <= max_mb, (
        f"model size {size_mb:.2f} MB (limit {max_mb:.0f} MB)"
    ), size_mb


def main() -> int:
    parser = argparse.ArgumentParser(description="ModelRail model gate.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--git-sha", default="unknown")
    parser.add_argument("--checkpoint", default="models/run/checkpoint.pt")
    parser.add_argument("--onnx", default="models/run/model-int8.onnx")
    parser.add_argument("--onnx-fp32", default="models/run/model.onnx")
    parser.add_argument("--eval-json", default="models/run/eval.json")
    parser.add_argument("--data", default="data/processed")
    parser.add_argument("--out", default="models/run/gate.json")
    parser.add_argument("--champion-accuracy", type=float, default=None)
    parser.add_argument("--min-accuracy-delta", type=float, default=None)
    parser.add_argument("--max-onnx-mismatch", type=float, default=None)
    parser.add_argument("--max-p95-latency-ms", type=float, default=None)
    parser.add_argument("--max-model-size-mb", type=float, default=None)
    args = parser.parse_args()

    params = load_params(args.params)
    eval_cfg, serve_cfg = params["evaluate"], params["serve"]

    champion = args.champion_accuracy
    if champion is None:
        env_champion = os.environ.get("CHAMPION_ACCURACY", "").strip()
        champion = float(env_champion) if env_champion else None
    tolerance = (
        args.min_accuracy_delta
        if args.min_accuracy_delta is not None
        else eval_cfg["champion_tolerance"]
    )
    floor = (
        (champion - tolerance) if champion is not None else eval_cfg["min_accuracy"]
    )
    max_abs = (
        args.max_onnx_mismatch
        if args.max_onnx_mismatch is not None
        else eval_cfg["onnx_pytorch_max_abs_diff"]
    )
    max_mean = eval_cfg["onnx_pytorch_max_mean_diff"]
    max_p95 = (
        args.max_p95_latency_ms
        if args.max_p95_latency_ms is not None
        else serve_cfg["p95_latency_ms_cpu"]
    )
    max_mb = (
        args.max_model_size_mb
        if args.max_model_size_mb is not None
        else serve_cfg["max_model_size_mb"]
    )

    results: dict = {}
    all_pass = True

    def record(name: str, ok: bool, detail: str, **extra):
        nonlocal all_pass
        results[name] = {"passed": ok, "detail": detail, **extra}
        all_pass = all_pass and ok
        print(f"gate [{name}]: {'PASS' if ok else 'FAIL'} - {detail}")

    try:
        ok, detail, acc = check_accuracy(args.eval_json, floor)
        record("accuracy", ok, detail, accuracy=acc, floor=floor)
    except FileNotFoundError:
        record("accuracy", False, f"eval file not found: {args.eval_json}")

    try:
        ok, detail = check_parity(
            args.checkpoint, args.onnx_fp32, args.data, params, max_abs, max_mean
        )
        record("onnx_parity", ok, detail)
    except Exception as exc:  # noqa: BLE001 - any parity failure fails the gate
        record("onnx_parity", False, f"parity check error: {exc}")

    try:
        ok, detail = check_latency(args.onnx, args.data, params, max_p95)
        record("p95_latency", ok, detail)
    except Exception as exc:  # noqa: BLE001 - any latency failure fails the gate
        record("p95_latency", False, f"latency check error: {exc}")

    try:
        ok, detail, size_mb = check_size(args.onnx, max_mb)
        record("model_size", ok, detail, size_mb=size_mb)
    except FileNotFoundError:
        record("model_size", False, f"model file not found: {args.onnx}")

    ok, detail = check_mlflow_run(args.git_sha)
    record("mlflow_run", ok, detail)

    results["passed"] = all_pass
    results["git_sha"] = args.git_sha
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(f"gate: {'PASSED' if all_pass else 'FAILED'}; wrote {args.out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
