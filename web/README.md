# ModelRail web demo

Portfolio project. A small static page that runs the quantized
MobileNetV3-small CIFAR-10 model in the browser with
onnxruntime-web, and reports in-browser latency and model size.

## Files

- `index.html` - the whole demo (page plus script). No build step.

## Model file

The page loads `model-int8.onnx` from the same directory. That file
is **not** bundled with this repo: it is produced by
`train/export_onnx.py` and `train/quantize.py` (another part of the
project). If the file is missing, the page says so plainly and the
Run button stays disabled, instead of failing silently or showing
fake numbers.

To try it locally once the model exists:

```sh
cp /path/to/model-int8.onnx web/
python -m http.server -d web 8000
# open http://localhost:8000
```

## What it measures

- Model load time and model size (from the `Content-Length` header).
- Per-inference latency in the browser, in milliseconds.
- Top-3 predicted CIFAR-10 classes.

The numbers are browser- and machine-specific. The server-side
benchmarks (PyTorch fp32 vs ONNX fp32 vs ONNX int8) live in
`docs/BENCHMARKS.md`; this page covers the "web and mobile" angle
credibly by showing the quantized model actually running on-device,
without claiming a mobile app exists.
