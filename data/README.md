# data/

Portfolio project. CIFAR-10 preparation, DVC pipeline, and validation.

## Layout

- `dvc.yaml` - stages prepare -> train -> evaluate -> export
- `params.yaml` - every hyperparameter and gate threshold, single source of truth
- `prepare.py` - download CIFAR-10, train/val split, schema checks, write processed data
- `schemas/schema.py` - pandera metadata schema plus class-balance, shape, dtype, and leakage checks
- `.dvc/config` - GCS remote (`gs://modelrail-modelrail-dvc`), configuration only, never run against real GCS yet

## Reproduce

```bash
dvc repro
```

CI runs the same pipeline on a 500-sample subset (`data.ci_subset_samples`).

## Validation rules

Any violation fails the pipeline:

- metadata must match the pandera schema exactly (labels 0-9, split in train/val/test, 32x32x3)
- every class share in every split must be inside `[min_class_share, max_class_share]` (default 0.05-0.20)
- images must be `(N, 32, 32, 3)` uint8 in `[0, 255]`
- no image id may appear in more than one split

## Data hash

`prepare.py` writes a SHA-256 per split into `prepare-metrics.json`. `train.py`
logs the same hash to MLflow, so any model version traces back to exact code
(git SHA) and exact data (data hash).
