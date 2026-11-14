# ModelRail infrastructure

Portfolio project. Nothing in this directory has been applied to GCP.
Region: `northamerica-northeast2` (Toronto). One GCP project, set via
`var.project_id`. No real project id, billing account, or credential is
committed anywhere in this repo.

## Layout

| File | What it owns |
| --- | --- |
| `versions.tf` | Providers, GCS remote-state backend (placeholder bucket) |
| `variables.tf` | All inputs, with sane defaults |
| `apis.tf` | APIs to enable |
| `network.tf` | VPC, subnet, private service access, Cloud NAT |
| `gke.tf` | GKE Autopilot cluster, guarded Spot pool option |
| `artifact_registry.tf` | Docker repository |
| `gcs.tf` | DVC data bucket, MLflow artifact bucket |
| `cloudsql.tf` | Cloud SQL Postgres `db-f1-micro` for MLflow |
| `iam.tf` | Least-privilege service accounts, Workload Identity, WIF |
| `monitoring.tf` | Dashboard, error-rate / latency / availability alerts |
| `budgets.tf` | Billing budget, alerts at 50/90/100% |
| `outputs.tf` | Cluster, buckets, registry, service accounts, WIF pool |

## Bootstrap (day 1, once)

1. Create the GCP project and note its id.
2. Create the Terraform state bucket and turn on versioning:
   ```sh
   gsutil mb -p <PROJECT_ID> -l northamerica-northeast2 gs://<PROJECT_ID>-tfstate
   gsutil versioning set on gs://<PROJECT_ID>-tfstate
   ```
3. Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in
   the real project id, billing account id, and alert email.
4. Replace the placeholder bucket in `versions.tf` backend block with
   the real state bucket name.
5. Replace `REPLACE-ME-modelrail` in `iam.tf` with the real GitHub
   repo (`owner/repo`) so the WIF provider trusts only this repo.
6. Run:
   ```sh
   terraform init
   terraform plan
   ```

## Teardown discipline

This is the TrainStore rule, applied here: **tear down after every
work session.** A GKE cluster and a Cloud SQL instance bill by the
hour whether anything runs or not. There is no free-trial credit
left to absorb this, so every hour left running is paid.

```sh
make down    # terraform destroy, from the repo root
```

Before closing a session, run `make down` and confirm the destroy
completes. The teardown proof (a `gcloud` resource listing showing
nothing running) goes in `docs/COST.md`. Rebuilding from scratch is
the point: `make up` must work from a clean state, every time.

## Cost notes

- GKE Autopilot bills per pod request, so idle time costs little, but
  the cluster control plane and Cloud SQL still bill while they exist.
- Cloud SQL `db-f1-micro` is the smallest tier on purpose.
- The billing budget in `budgets.tf` alerts at 50/90/100% of $50
  by default. A budget alerts; it does not stop spending. `make down` is the
  actual cost control.

## Credentials

There are no JSON service-account keys anywhere in this repo, by
design. GitHub Actions authenticates via Workload Identity Federation
(see `iam.tf` and `docs/adr/ADR-004-wif-over-keys.md`). Workloads on
GKE use Workload Identity with one least-privilege service account
each. If you find a `.json` key file in this repo, delete it and
rotate the key: it does not belong here.
