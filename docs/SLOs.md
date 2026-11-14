# ModelRail SLOs

Portfolio project. These SLOs are defined for the serving path and
enforced by the alert policies in `infra/terraform/monitoring.tf`.
They are set for synthetic load-test traffic, not real production
traffic, and must be re-tuned before any real traffic exists.

## Service level objectives

| SLO | Target | Window |
| --- | --- | --- |
| Availability | 99% of prediction requests succeed | 30-day rolling |
| Latency | p95 prediction latency under 100 ms | 30-day rolling |

Availability means: a request to `/predict` returns a 2xx response.
Latency is measured server-side, from request receipt to response
send, excluding network time to the client.

## Error budget

- Availability budget: 1% of requests may fail per 30 days.
  At 1,000 requests/day of synthetic traffic, that is 300 failed
  requests per month before the budget is exhausted.
- Latency budget: 5% of requests may exceed 100 ms p95 per 30 days
  (the p95 definition already allows 5% above the threshold; the
  budget tracks sustained breach, not single requests).

Error budget remaining is exposed by the MCP `get_slo_status` tool
and on the Cloud Monitoring dashboard.

## Alerts (error-budget burn)

| Alert | Condition | Response |
| --- | --- | --- |
| High error rate | Error rate above 5% for 5 minutes | Page; check canary status, then roll back via MCP `rollback` |
| High latency | p95 above 100 ms for 10 minutes | Page; check pod CPU, HPA state, model version |
| Serving unavailable | No serving pods reporting for 5 minutes | Page; check Deployment and rollout status |

Alerts fire on sustained burn, not single spikes: a brief blip does
not page anyone. The canary analysis (ADR-005) uses the same
thresholds, so a bad canary rolls back before the SLO alert fires.

## What is not covered

- Training jobs have no SLO: they are batch work, and their
  reliability is covered by checkpoint/resume and the drills in
  `docs/DRILLS.md`, not by an SLO.
- MLflow availability has no SLO: it is a dev-time tool, not the
  serving path. If MLflow is down, training logs locally and retries.
- Drift detection has no SLO: it is a CronJob, and its reliability
  is measured by "did the alert fire when drift was injected", which
  is a drill, not an SLO.
