# Two GCS buckets: one is the DVC remote, the other holds MLflow artifacts.
# Uniform bucket-level access, versioning on (checkpoints and artifacts
# are cheap insurance against a bad overwrite), no public access.

resource "google_storage_bucket" "dvc" {
  name                        = local.dvc_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  labels = merge(local.common_labels, { purpose = "dvc-data" })

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "mlflow" {
  name                        = local.mlflow_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  labels = merge(local.common_labels, { purpose = "mlflow-artifacts" })

  depends_on = [google_project_service.apis]
}
