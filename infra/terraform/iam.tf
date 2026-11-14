# IAM: one least-privilege Google service account per workload, plus
# Workload Identity Federation for GitHub Actions. No JSON service
# account keys are created anywhere in this repo. See
# docs/adr/ADR-004-wif-over-keys.md for why.
#
# Workloads and their accounts:
#   training  - reads DVC data, writes checkpoints and MLflow artifacts
#   serving   - reads MLflow artifacts (model files) only
#   mlflow    - runs the MLflow tracking server, reads/writes its bucket
#   ci        - used only via WIF from GitHub Actions, pushes images and
#               applies Terraform (see the WIF pool below)
#   drift     - reads production input stats, writes drift metrics
# Each account gets only the roles its workload needs. The Kubernetes
# service accounts in k8s/ bind to these via Workload Identity; the
# bindings themselves live here so IAM stays in one place.

resource "google_service_account" "training" {
  account_id   = "modelrail-training"
  project      = var.project_id
  display_name = "ModelRail training jobs"
}

resource "google_service_account" "serving" {
  account_id   = "modelrail-serving"
  project      = var.project_id
  display_name = "ModelRail inference serving"
}

resource "google_service_account" "mlflow" {
  account_id   = "modelrail-mlflow"
  project      = var.project_id
  display_name = "ModelRail MLflow tracking server"
}

resource "google_service_account" "ci" {
  account_id   = "modelrail-ci"
  project      = var.project_id
  display_name = "ModelRail CI (GitHub Actions via WIF)"
}

resource "google_service_account" "drift" {
  account_id   = "modelrail-drift"
  project      = var.project_id
  display_name = "ModelRail drift detection CronJob"
}

# Training: read DVC data, write checkpoints and MLflow artifacts.
resource "google_storage_bucket_iam_member" "training_dvc_read" {
  bucket = google_storage_bucket.dvc.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.training.email}"
}

resource "google_storage_bucket_iam_member" "training_mlflow_write" {
  bucket = google_storage_bucket.mlflow.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.training.email}"
}

# Serving: read model artifacts only. No write access anywhere.
resource "google_storage_bucket_iam_member" "serving_mlflow_read" {
  bucket = google_storage_bucket.mlflow.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.serving.email}"
}

# MLflow server: read/write its own artifact bucket, connect to Cloud SQL.
resource "google_storage_bucket_iam_member" "mlflow_bucket_admin" {
  bucket = google_storage_bucket.mlflow.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.mlflow.email}"
}

resource "google_project_iam_member" "mlflow_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.mlflow.email}"
}

# Drift job: read the MLflow artifact bucket (training reference stats).
resource "google_storage_bucket_iam_member" "drift_mlflow_read" {
  bucket = google_storage_bucket.mlflow.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.drift.email}"
}

# CI: push images to Artifact Registry, read/write state-adjacent buckets
# only through the training job it launches, not directly. Terraform
# apply from CI uses this account; keep its project roles narrow and
# review any addition in a PR.
resource "google_artifact_registry_repository_iam_member" "ci_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.modelrail.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "ci_gke_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

# Workload Identity bindings: Kubernetes service accounts (created in
# k8s/) impersonate these Google service accounts. Namespace and
# service-account names must match k8s/base/*.
resource "google_service_account_iam_member" "training_wi" {
  service_account_id = google_service_account.training.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[modelrail/training]"
}

resource "google_service_account_iam_member" "serving_wi" {
  service_account_id = google_service_account.serving.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[modelrail/serving]"
}

resource "google_service_account_iam_member" "mlflow_wi" {
  service_account_id = google_service_account.mlflow.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[modelrail/mlflow]"
}

resource "google_service_account_iam_member" "drift_wi" {
  service_account_id = google_service_account.drift.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[modelrail/drift]"
}

# Workload Identity Federation for GitHub Actions. The pool trusts the
# GitHub OIDC issuer; the provider restricts tokens to this repo only
# (simplysoup/modelrail). No JSON keys: GitHub mints a short-lived OIDC token per
# run and exchanges it for a GCP access token.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  project                   = var.project_id
  display_name              = "GitHub Actions"
  description               = "Federated identity for ModelRail GitHub Actions. No JSON keys."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  project                            = var.project_id
  display_name                       = "GitHub OIDC"
  description                        = "GitHub Actions OIDC provider, restricted to the ModelRail repo."

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == 'simplysoup/modelrail'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# GitHub Actions (via WIF) may impersonate the CI service account, and
# only from this repo. The attribute condition on the provider plus this
# binding is the whole trust boundary: there is no long-lived credential.
resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/simplysoup/modelrail"
}
