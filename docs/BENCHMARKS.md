# ModelRail benchmarks

Portfolio project. Measured Nov 14, 2026, in the single paid GCP
session (region northamerica-northeast2). The tables below record
what was actually measured; anything marked "not measured" was not
run in that session. Do not fill those in from estimates or from
other projects' numbers.

## Quantization comparison

Model: fine-tuned MobileNetV3-small on CIFAR-10. Trained Nov 14, 2026
on the full CIFAR-10 split (50,000 train / 10,000 test), 10 epochs,
pretrained weights, Adam lr 0.001, cosine schedule. Training Job took
27 minutes wall time on the cluster (2-4 CPUs). Best validation
accuracy 0.7258; test accuracy 0.7219 (PyTorch checkpoint, 10,000
test images). The model did NOT meet the 0.80 release-gate floor, so
it was registered as a candidate and canaried for the deployment
demonstration, but never promoted to champion.

| Variant | Size (MB) | p50 latency (ms) | p95 latency (ms) | Throughput (req/s/pod) | Accuracy | Accuracy delta vs fp32 |
| --- | --- | --- | --- | --- | --- | --- |
| PyTorch fp32 | 18.58 (checkpoint.pt) | not measured | not measured | not measured | 0.7219 (test) | - |
| ONNX fp32 | 5.84 | 2.3 | 55.7 | not measured | not measured separately (parity vs PyTorch: max abs diff 0.000020, mean abs diff 0.000004 on the eval set) | - |
| ONNX int8 (static quant, calibrated) | 1.80 | not measured separately | not measured separately | not measured | not measured separately (the served model; accuracy quoted is the PyTorch checkpoint's) | not measured |

Latency for ONNX fp32 is from the release gate (train/gate.py), 100
single-image requests, ONNX Runtime CPU, measured on the build VM
Nov 14, 2026: p50 2.3 ms, p95 55.7 ms. A single live /predict call
to the canary pod returned in 12.2 ms. The int8 latency was not
measured separately from fp32; the 55.7 ms p95 is the fp32 figure.

Method, to be followed when measuring:

- Latency: single-image requests, warm pod, 1,000 requests, CPU only.
- Throughput: k6 load test, ramp until p95 exceeds 100 ms or errors
  appear; record the saturation point.
- Accuracy: CIFAR-10 test split, same split for all three variants.
- Calibration set for int8: record its size and source here when run.
- Cost per 1M predictions: derived from the actual node/pod price at
  measurement time, shown with the price source and date.

## Load test (k6)

Not run. No saturation test was done in the single paid session, so
throughput and cost per 1M predictions are not measured. The serving
pod handled a steady 1 request per 5 seconds during the canary
analysis windows without errors; that is a smoke level, not a load
test.

| Metric | Value |
| --- | --- |
| Requests per second per pod | (not measured) |
| Saturation point (req/s, pods) | (not measured) |
| p95 latency at saturation (ms) | (not measured) |
| Cost per 1M predictions (USD) | (not measured) |
| Node/pod price basis | (not measured - record price source and date) |

## Host and node specs (fill in when measured)

- Serving pod requests/limits: 500m CPU / 512 MiB requests, 1000m CPU / 1 GiB limits.
- Node type: GKE Autopilot (node type managed by Google; not recorded).
- Region: northamerica-northeast2
- k6 runner location: (not measured)

## What this does not prove

- These numbers are for a small model on synthetic CIFAR-10 images
  and synthetic k6 traffic. They say nothing about real production
  traffic, real image distributions, or larger models.
- In-browser latency (web demo) depends on the visitor's machine
  and browser; it is not comparable to server-side latency.
- Cost per 1M predictions assumes the pod is saturated. At low
  traffic, the per-prediction cost is higher because the pod still
  bills while idle.
- A single load-test run is not a capacity plan. Re-run before
  trusting any of these numbers for a real decision.
