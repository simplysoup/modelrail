# k8s/

Portfolio project. Kubernetes manifests for ModelRail. Nothing is deployed.

## Layout

- `base/` - namespace, serving Deployment, Service, HPA, PodDisruptionBudget, training Job, drift CronJob, Argo Rollouts canary Rollout, Prometheus AnalysisTemplate
- `overlays/dev/` - 1 replica, dev model version, smaller resources
- `overlays/prod/` - 3 replicas, champion model version

## Apply

```bash
kubectl apply -k k8s/overlays/dev
kubectl apply -k k8s/overlays/prod
```

## Canary

The Rollout in `base/rollout.yaml` steps 10% -> 50% -> 100%, running the
Prometheus analysis in `base/analysis-template.yaml` at each step
(error rate under 1%, p95 latency under 100 ms). A failed analysis aborts
the rollout and rolls back automatically.

## Fallback if Argo Rollouts is absent

If the Rollouts controller is not installed in the cluster:

1. Remove `rollout.yaml` and `analysis-template.yaml` from the `resources`
   list in `base/kustomization.yaml`.
2. Apply the overlays as normal. The plain Deployment in
   `base/deployment.yaml` serves traffic with a rolling update
   (`maxSurge: 1`, `maxUnavailable: 0`) instead of a canary.
3. Run the smoke-test Job after each deploy (defined in CI, owned by
   another agent) before promoting the model to champion.

Only one of Deployment or Rollout should manage the serving pods at a
time. Do not apply both.
