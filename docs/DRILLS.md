# ModelRail failure drills

Portfolio project. Every drill below is a procedure with a pass
condition. Status: **NOT YET RUN**. No evidence exists yet, and no
evidence is invented here. When a drill runs, add a dated entry with
a timeline, the observed evidence, and the fix (if any).

## How to record a drill

For each run, append:

- Date and who ran it.
- Timeline (times in Toronto time, minute precision).
- What was observed (commands run, output, links to logs).
- Pass or fail against the pass condition.
- Fix, if the drill found something broken.

## Drill 1: Pod killed mid-training

- Procedure: start a training Job, wait for the first checkpoint to
  land in GCS, then `kubectl delete pod -n modelrail -l job-name=modelrail-train`.
  The Job restarts the pod; training resumes from the last good
  checkpoint (manifest-as-commit-point, conditional GCS writes).
- Pass condition: training completes and the final metric is
  identical to an uninterrupted run of the same commit and data hash.
- Status: NOT YET RUN.

## Drill 2: Spot preemption

- Procedure: only applies if the Spot node pool is in use (ADR-006).
  Start a training Job on the Spot pool, then simulate preemption
  (or wait for a real one) and confirm the Job resumes from the last
  checkpoint on a new node.
- Pass condition: same as Drill 1 (identical final metric), plus the
  resume is automatic with no manual intervention.
- Status: NOT YET RUN. Not applicable while training on Autopilot.

## Drill 3: Bad model blocked by the gate

- Procedure: train a deliberately bad model (for example, one epoch
  on a shuffled-label subset) and push it through the release
  pipeline. The model gate must fail it on accuracy.
- Pass condition: the pipeline stops at the model-gate job, the
  model is never registered as candidate, and nothing is deployed.
- Status: NOT YET RUN.

## Drill 4: Schema-violating dataset blocked in CI

- Procedure: open a PR that changes the data so the pandera schema
  check fails (for example, a class missing from the training split,
  or a train/test leakage between splits). The PR checks must fail.
- Pass condition: the data-check job fails, the PR is blocked, and
  the failure message names the violated check.
- Status: NOT YET RUN.

## Drill 5: Canary auto-rollback

- Procedure: deploy a canary that breaches the error-rate threshold
  (for example, a serving image that returns 500 on a fraction of
  requests). Argo Rollouts must roll it back automatically.
- Pass condition: the rollout returns to the previous version with
  no manual step, and the error rate returns to baseline. Record
  time-to-recover (first bad request to full rollback).
- Status: NOT YET RUN.

## Drill 6: Manual rollback via the MCP tool

- Procedure: with a known-good champion deployed, call the MCP
  `rollback` tool with `approval: true` and a reason. Confirm the
  serving version moves back, the audit log gains one entry, and the
  same call without approval is rejected.
- Pass condition: rollback completes, audit log entry exists with
  timestamp/tool/reason, and the unauthenticated call fails.
  Record time-to-recover (tool call to serving the old version).
- Status: NOT YET RUN.

## Drill log

| Date | Drill | Result | Time-to-recover | Notes |
| --- | --- | --- | --- | --- |
| (none yet) | | | | No drills run yet |
