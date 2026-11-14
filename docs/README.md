# ModelRail docs

Portfolio project. Nothing described here has been deployed.

## Contents

- `adr/` - architecture decision records (6):
  - ADR-001 Autopilot vs Standard
  - ADR-002 ONNX Runtime
  - ADR-003 Aliases vs stages
  - ADR-004 Workload Identity Federation over JSON keys
  - ADR-005 Canary analysis thresholds
  - ADR-006 Spot training (documented alternative)
- `SLOs.md` - availability 99%, p95 latency under 100 ms, error-budget burn alerts
- `COST.md` - pricing-calculator estimates (labelled as estimates), billing budget, teardown proof (TODO)
- `DRILLS.md` - six failure drills, all marked NOT YET RUN
- `BENCHMARKS.md` - quantization and load-test table schemas, empty until measured

## Limits (read before quoting anything here)

Single region (`northamerica-northeast2`), a small model
(MobileNetV3-small on CIFAR-10), no real production traffic, and a
synthetic drift simulation. Benchmarks, costs, and drill results are
empty until they are measured on real runs; estimates are labelled
as estimates and must not be quoted as billed figures.
