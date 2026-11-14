output "project_id" {
  description = "GCP project id."
  value       = var.project_id
}

output "region" {
  description = "GCP region."
  value       = var.region
}

output "cluster_name" {
  description = "GKE cluster name."
  value       = google_container_cluster.modelrail.name
}

output "cluster_endpoint" {
  description = "GKE cluster endpoint. Use gcloud container clusters get-credentials to connect."
  value       = google_container_cluster.modelrail.endpoint
  sensitive   = true
}

output "artifact_registry_repo" {
  description = "Artifact Registry repository path for images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.modelrail.repository_id}"
}

output "dvc_bucket" {
  description = "GCS bucket for the DVC remote."
  value       = google_storage_bucket.dvc.url
}

output "mlflow_bucket" {
  description = "GCS bucket for MLflow artifacts."
  value       = google_storage_bucket.mlflow.url
}

output "cloudsql_instance" {
  description = "Cloud SQL instance name for the MLflow backend."
  value       = google_sql_database_instance.mlflow.name
}

output "cloudsql_private_ip" {
  description = "Cloud SQL private IP. MLflow connects over the VPC, never publicly."
  value       = google_sql_database_instance.mlflow.private_ip_address
}

output "service_accounts" {
  description = "Least-privilege service account emails, one per workload."
  value = {
    training = google_service_account.training.email
    serving  = google_service_account.serving.email
    mlflow   = google_service_account.mlflow.email
    ci       = google_service_account.ci.email
    drift    = google_service_account.drift.email
  }
}

output "wif_pool" {
  description = "Workload Identity Federation pool for GitHub Actions."
  value       = google_iam_workload_identity_pool.github.name
}

output "wif_provider" {
  description = "WIF provider resource name, for the google-github-actions/auth step in CI."
  value       = google_iam_workload_identity_pool_provider.github.name
}
