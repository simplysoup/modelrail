# ADR-006: Spot training (documented alternative)

- Status: Accepted (as a documented alternative, not the default)
- Date: 2026-11-14
- Context: Training on Spot VMs is much cheaper than on-demand, but
  Spot VMs can be preempted at any time. The default cluster is GKE
  Autopilot (ADR-001), where Spot node pools are not available the
  same way as on Standard.

## Decision

- Default: train on Autopilot pods. The MobileNetV3-small fine-tune
  is small and CPU-bound, so on-demand Autopilot cost is acceptable
  inside the small paid budget (a few dollars per session).
- Alternative: if training cost or training time dominates, replace
  the Autopilot cluster with a Standard cluster and enable the
  guarded Spot node pool in `infra/terraform/gke.tf`
  (`enable_spot_node_pool = true`). The pool taints nodes
  `workload=training:NoSchedule` so only training jobs land there.

## Why Spot is safe here (when used)

- Training checkpoints to GCS after every epoch, with the
  manifest-as-commit-point protocol (conditional GCS writes with
  `ifGenerationMatch`). A preempted pod resumes from the last good
  checkpoint instead of restarting.
- The drill in `docs/DRILLS.md` (Spot preemption) proves the resume
  path before any long run depends on it.
- The final metric must be identical after a resume; if it is not,
  the checkpoint protocol is broken and Spot is off the table.

## Consequences

- Switching to Spot is a deliberate cluster replacement, not a flag
  flip: the Spot pool resource is guarded and will fail against the
  Autopilot cluster by design, so nobody enables it by accident.
- Preemption during a run adds wall-clock time (resume plus
  re-scheduling). For this model size that is minutes, not hours.
- Spot prices vary by zone and time; the cost report in
  `docs/COST.md` records the actual price paid when Spot is used,
  not the list price.
