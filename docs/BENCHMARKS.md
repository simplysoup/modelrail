# ModelRail benchmarks

Portfolio project. No benchmarks have been measured yet: nothing has
been deployed and no model has been trained. The tables below define
exactly what will be measured, so the numbers are comparable when
they exist. Do not fill them in from estimates or from other
projects' numbers.

## Quantization comparison

Model: fine-tuned MobileNetV3-small on CIFAR-10. Host: the serving
pod (record the actual node type and CPU below when measured).

| Variant | Size (MB) | p50 latency (ms) | p95 latency (ms) | Throughput (req/s/pod) | Accuracy | Accuracy delta vs fp32 |
| --- | --- | --- | --- | --- | --- | --- |
| PyTorch fp32 | (not measured) | (not measured) | (not measured) | (not measured) | (not measured) | - |
| ONNX fp32 | (not measured) | (not measured) | (not measured) | (not measured) | (not measured) | (not measured) |
| ONNX int8 (static quant, calibrated) | (not measured) | (not measured) | (not measured) | (not measured) | (not measured) | (not measured) |

Method, to be followed when measuring:

- Latency: single-image requests, warm pod, 1,000 requests, CPU only.
- Throughput: k6 load test, ramp until p95 exceeds 100 ms or errors
  appear; record the saturation point.
- Accuracy: CIFAR-10 test split, same split for all three variants.
- Calibration set for int8: record its size and source here when run.
- Cost per 1M predictions: derived from the actual node/pod price at
  measurement time, shown with the price source and date.

## Load test (k6)

| Metric | Value |
| --- | --- |
| Requests per second per pod | (not measured) |
| Saturation point (req/s, pods) | (not measured) |
| p95 latency at saturation (ms) | (not measured) |
| Cost per 1M predictions (USD) | (not measured) |
| Node/pod price basis | (not measured - record price source and date) |

## Host and node specs (fill in when measured)

- Serving pod requests/limits: (not measured)
- Node type: (not measured)
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
