# ADR-001: GKE Autopilot as the default cluster

- Status: Accepted
- Date: 2026-11-14
- Context: ModelRail needs a Kubernetes cluster for MLflow, serving,
  training jobs, and drift detection, on a small paid budget (the
  GCP free-trial credit is already used up).

## Decision

Use GKE Autopilot. No node pools to manage, no node upgrades to
schedule, per-pod billing, and Workload Identity on by default.

## Alternatives considered

- GKE Standard with a Spot node pool: cheaper for long training runs
  and the only way to use Spot nodes directly, but it adds node
  management, autoscaling tuning, and upgrade work that is not the
  point of this project. Kept as the documented Spot alternative
  (ADR-006): if training cost dominates, replace the cluster with a
  Standard one and enable the guarded Spot pool in `infra/terraform/gke.tf`.
- Cloud Run: simpler, but the project needs Kubernetes Jobs,
  CronJobs, HPA, and Argo Rollouts, which are Kubernetes concepts.

## Consequences

- Training runs on regular Autopilot pods (CPU), billed per pod.
  That is acceptable for a small MobileNetV3-small fine-tune.
- Spot pricing for training is not available on Autopilot in the
  same way; ADR-006 documents the trade-off explicitly.
- Less to operate, which is the point for a portfolio project that
  must be torn down after every session.
