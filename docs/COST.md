# ModelRail cost report

Portfolio project. All figures below are estimates from the GCP
pricing calculator unless marked as billed. No billed figures exist
yet: nothing has been deployed, and no money has been spent.

## Estimate (pricing calculator, northamerica-northeast2)

Prices are list prices at the time of estimation and will change.
Re-check them in the pricing calculator before spending anything.

| Resource | Basis | Estimated cost |
| --- | --- | --- |
| GKE Autopilot control plane | Flat, per cluster | ~$0.10/hour (~$74/month if left running) |
| GKE Autopilot pods (serving, 2 replicas) | 0.5 vCPU + 1 GiB each, per-pod pricing | ~$35-45/month if left running |
| GKE Autopilot pods (training Job) | 2 vCPU + 4 GiB, a few hours per run | ~$0.50-1.50 per training run |
| Cloud SQL Postgres db-f1-micro | Smallest tier, per hour | ~$7-9/month if left running |
| GCS (DVC data + MLflow artifacts) | A few GB, Standard storage | Under $1/month |
| Artifact Registry | A few GB of images | Under $1/month |
| Cloud Monitoring | Basic metrics, within free tier | $0 |
| **Total, if left running a month** | | **~$120-130/month** |
| **Total, with teardown after every session** | | **A few dollars per session** |

Sources: Google Cloud Pricing Calculator
(https://cloud.google.com/products/calculator), GKE Autopilot pricing
and Cloud SQL pricing pages. Labelled as estimates: the calculator
is not a bill.

## Budget

- Billing budget: $50/month by default (set in Terraform; raise it
  only deliberately), alerts at 50%, 90%, and 100%, defined in
  `infra/terraform/budgets.tf`. A budget alerts; it does not stop
  spending. Note: the $300 GCP free-trial credit is NOT available,
  it was used up before this project started, so every dollar
  here is paid out of pocket.
- Real cost control: `make down` after every session. See
  `infra/README.md`.

## What was cut to stay in budget

- No GPU anywhere: the model is MobileNetV3-small on CIFAR-10,
  CPU-only by design.
- Cloud SQL db-f1-micro, the smallest tier, instead of a larger
  instance with high availability.
- Single region, no multi-region replication.
- No load balancer with a static IP left running between sessions;
  serving is exposed only while the cluster is up.
- Spot training (ADR-006) is available as a further cut if training
  runs get long, but it is not the default.

## Actual billed figures

Session Nov 14, 2026 (evening, ~14:00-22:00 EST): single paid run.
Cluster (GKE Autopilot) + Cloud SQL db-f1-micro + GCS + Artifact
Registry + Cloud Build, region northamerica-northeast2. Training Job
ran 27 minutes; serving ran for the canary (about 2 hours of pod
time across the session). Billed amount is being confirmed from the
GCP billing console; the figure below will be updated with it.

| Date | Session | Billed (CAD) | Notes |
| --- | --- | --- | --- |
| 2026-11-14 | Single paid run, ~8 h of infra uptime | (pending console check) | GKE Autopilot + Cloud SQL + Cloud Build + GCS + Artifact Registry. Budget $50 CAD/month; no alert fired. |

## Teardown proof

Session Nov 14, 2026, torn down the same night (terraform destroy,
finished ~22:11 EST). Verified after the destroy, all via gcloud:

- GKE clusters: 0
- Cloud SQL instances: 0
- GCS buckets: 0 (DVC, MLflow, Cloud Build, and tfstate buckets all deleted)
- Artifact Registry repositories: 0
- Terraform state: 0 resources (destroy complete)
- Service accounts: only the Compute Engine default remains; the temporary modelrail-run service account was deleted, and its local key file was deleted.
- VPS: ~/.kube-modelrail-config, ~/modelrail-k8s, ~/bin/kubectl all removed.
- Network: only the project default VPC remains; modelrail-vpc deleted.

Two destroy hiccups, both fixed by hand and noted for the next
run: the DVC and MLflow buckets had to be emptied before terraform
could delete them (no force_destroy set), and the Cloud SQL user
could not be dropped while its database had objects, so the instance
was deleted directly and the SQL resources removed from state; the
private VPC peering then had to be deleted directly before the
service networking connection would release.
