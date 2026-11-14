# ADR-005: Canary analysis thresholds

- Status: Accepted
- Date: 2026-11-14
- Context: The canary deploys 10% -> 50% -> 100% with Argo Rollouts
  and a Prometheus analysis template. The thresholds decide when a
  canary rolls back automatically, so they need reasons, not vibes.

## Decision

- Error rate: roll back if the error rate exceeds 5% for 5 minutes.
- Latency: roll back if p95 exceeds 100 ms for 10 minutes.
- Steps: 10% for 5 minutes, 50% for 10 minutes, then 100%.

## Why these numbers

- The latency SLO is p95 under 100 ms (docs/SLOs.md), so the canary
  latency threshold is the SLO itself: a canary that breaches the
  SLO is not a canary, it is an outage in miniature.
- 5% error rate is far above the baseline error rate of a healthy
  service (near zero for a deterministic image classifier), so a
  breach means something is actually wrong, not noise. At 10% of
  traffic, 5% errors is still a small absolute number of failed
  requests.
- The 5-minute error window is short enough to limit blast radius
  and long enough to avoid rolling back on a single bad pod start.
  The 10-minute latency window is longer because latency is noisier
  than errors, especially on shared CPU.
- Step durations (5 and 10 minutes) give the analysis template at
  least one full evaluation window per step.

## Consequences

- A slow-burn regression (error rate 2-3%) will not trip the canary
  and must be caught by the SLO burn alerts instead. That is a
  known gap, accepted: the canary catches big breaks fast, and the
  SLO alerts catch slow ones.
- Thresholds are tuned for synthetic load-test traffic, not real
  production traffic. They must be re-tuned before any real traffic
  exists; see the Limits section in `docs/BENCHMARKS.md`.
