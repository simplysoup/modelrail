# ModelRail

A small but complete ML lifecycle on GCP, from data versioning through
canary deploy and rollback. Portfolio project, not production: it runs
one small model, on synthetic-scale traffic, in a single region.

Model: fine-tune MobileNetV3-small on CIFAR-10, CPU-only. The model is
deliberately boring. The platform is what is being judged.

## What it demonstrates

| Posting requirement | Where it is proven |
| --- | --- |
| GCP | GKE, GCS, Artifact Registry, Cloud SQL, Cloud Monitoring, Workload Identity |
| IaC | 100% Terraform, remote state in GCS, plan on every PR |
| MLflow / DVC | DVC remote on GCS, MLflow tracking and registry on GKE |
| Docker and Kubernetes | Training Jobs, serving Deployment, HPA, CronJob, Argo Rollouts |
| CI/CD for data, models, code | GitHub Actions with gates for each artifact type |
| High-throughput inference | ONNX Runtime service, k6 load tests, cost per 1M predictions |
| Optimize models for web and mobile | Quantized ONNX model, in-browser demo, size/latency/accuracy table |
| LLM-controllable tools | MCP server over the platform with read/write separation |
| Reliability and cost | SLOs, alerts, failure drills, budgets, a measured cost report |

## Layout

```text
modelrail/
  infra/        terraform: network, gke, gcs, artifact-registry, cloudsql, iam, monitoring, budgets
  data/         dvc.yaml, params.yaml, schemas/ (pandera)
  train/        train.py, evaluate.py, export_onnx.py, quantize.py, gate.py, checkpoint.py, drift_check.py
  serve/        FastAPI + ONNX Runtime, Dockerfile
  k8s/          kustomize base + overlays, argo-rollouts, hpa, cronjobs
  mcp/          platform MCP server
  web/          static onnxruntime-web demo
  .github/workflows/
  docs/         ADRs, SLOs.md, COST.md, DRILLS.md, BENCHMARKS.md
```

## Run it locally (no GCP, no spend)

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m data.prepare --subset          # 500-sample splits, schema checks included
python -m train.train --data data/processed --out models/run
python -m train.evaluate --checkpoint models/run/checkpoint.pt --out models/run/eval.json
python -m train.export_onnx --checkpoint models/run/checkpoint.pt --out models/run/model.onnx
python -m train.quantize --model models/run/model.onnx --out models/run/model-int8.onnx
python train/gate.py --checkpoint models/run/checkpoint.pt --onnx models/run/model-int8.onnx
MODEL_PATH=models/run/model-int8.onnx uvicorn serve.app:app --port 8000
pytest tests/ mcp/tests
```

The full local run was verified Nov 14, 2026: 50 tests pass, a real
500-sample CIFAR-10 run trains and resumes from checkpoint, ONNX fp32
is 5.84 MB, int8 is 1.80 MB, ONNX vs PyTorch parity max diff 0.000048,
and the serve smoke test answers /predict in a few ms per request.
Accuracy after 2 epochs on 500 samples is 0.11 (near chance), so the
model gate correctly fails on accuracy: that run was a pipeline smoke
test, not a trained model. The full 10-epoch run on GCP is what the
single paid run is for.

## The one GCP run

The GCP free-trial credit is already used up, so the deploy is paid.
Decision (Nov 14, 2026): exactly one paid run at current estimated
costs, teardown immediately once all features are built and run. No
second run without a new decision. Default billing budget is $50/month
with alerts at 50/90/100%; the real cost control is `make down` after
the session. See [docs/COST.md](docs/COST.md).

```sh
make up     # terraform apply, deploy MLflow, run the pipeline
make down   # terraform destroy; then paste the teardown proof into docs/COST.md
```

## Architecture

```text
GitHub Actions (WIF, no keys)
  PR: lint, test, terraform plan, dvc repro on 500 samples, schema checks
  main: build image -> training Job on GKE -> model gate -> register candidate
        -> Argo Rollouts canary 10% -> 50% -> 100% -> promote to champion

GKE Autopilot (northamerica-northeast2)
  MLflow (Cloud SQL backend, GCS artifacts)   Serving (ONNX Runtime, HPA)
  Training Job (Spot)                         Drift CronJob (daily PSI/KS)

MCP server (stdio)
  read: list_models, compare_runs, get_deploy_status, get_slo_status
  write (approval-gated, audited): promote_model, rollback
  no delete tools
```

## Limits

- Single region, one small model, no real production traffic.
- Drift is a synthetic simulation (corrupted CIFAR-10), not real drift.
- The load-test and cost numbers in docs/BENCHMARKS.md and
  docs/COST.md are empty until the GCP run measures them; nothing
  there is a billed figure yet.
- The merge pipeline has one known wiring gap, documented in
  .github/workflows/main.yml: the training Job must upload
  models/run/* to GCS before the gate job can download it.

## Docs

- [docs/adr/](docs/adr/) - six short ADRs, including why Autopilot, why
  ONNX Runtime, why aliases over stages, why WIF over keys.
- [docs/SLOs.md](docs/SLOs.md) - 99% availability, p95 under 100 ms.
- [docs/DRILLS.md](docs/DRILLS.md) - failure drills, all marked not yet run.
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) - quantization and load-test tables.
- [docs/COST.md](docs/COST.md) - estimates, budget, teardown proof.
