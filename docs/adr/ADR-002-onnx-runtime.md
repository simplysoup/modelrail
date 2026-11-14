# ADR-002: ONNX Runtime for inference serving

- Status: Accepted
- Date: 2026-11-14
- Context: The serving layer needs to run a fine-tuned MobileNetV3-small
  on CPU, with a quantized variant for web and mobile, and the model
  must be comparable across PyTorch, ONNX fp32, and ONNX int8.

## Decision

Serve with ONNX Runtime (CPU execution provider) behind FastAPI.
Export PyTorch to ONNX, then statically quantize to int8 with
calibration data.

## Alternatives considered

- TorchServe: heavier, more moving parts, and no direct path to an
  in-browser demo.
- TensorFlow Serving: wrong stack for a PyTorch-trained model.
- Raw PyTorch in the serving container: simplest, but no quantization
  story and a larger image.

## Consequences

- One model artifact (ONNX) serves the API, the load tests, and the
  in-browser demo via onnxruntime-web, so benchmarks compare the
  same artifact across runtimes.
- The model gate checks ONNX vs PyTorch outputs match within
  tolerance, so an export bug is caught in CI, not in production.
- Static quantization needs calibration data; the calibration set and
  its size are recorded in `docs/BENCHMARKS.md` so the int8 numbers
  are reproducible.
