variable "project_id" {
  description = "GCP project id for ModelRail. No real value is committed; pass it with -var or TF_VAR_project_id."
  type        = string
  default     = ""
}

variable "region" {
  description = "GCP region. Toronto."
  type        = string
  default     = "northamerica-northeast2"
}

variable "zone" {
  description = "Primary zone within the region, used where a zonal resource is required."
  type        = string
  default     = "northamerica-northeast2-a"
}

variable "environment" {
  description = "Environment label applied to resources."
  type        = string
  default     = "dev"
}

variable "cluster_name" {
  description = "Name of the GKE cluster."
  type        = string
  default     = "modelrail"
}

variable "gke_release_channel" {
  description = "GKE release channel for the Autopilot cluster."
  type        = string
  default     = "REGULAR"
}

variable "enable_spot_node_pool" {
  description = "If true, also create a Standard-style Spot node pool for training jobs. Autopilot is the default; see docs/adr/ADR-001-autopilot-vs-standard.md and docs/adr/ADR-006-spot-training.md. Enabling this requires switching the cluster to Standard mode, so this flag is documentation plus a guarded resource, not a silent mode switch."
  type        = bool
  default     = false
}

variable "spot_machine_type" {
  description = "Machine type for the optional Spot training node pool."
  type        = string
  default     = "e2-standard-4"
}

variable "spot_min_nodes" {
  description = "Minimum nodes in the optional Spot training node pool."
  type        = number
  default     = 0
}

variable "spot_max_nodes" {
  description = "Maximum nodes in the optional Spot training node pool."
  type        = number
  default     = 3
}

variable "artifact_registry_repo" {
  description = "Artifact Registry repository id for container images."
  type        = string
  default     = "modelrail"
}

variable "dvc_bucket_name" {
  description = "GCS bucket for DVC data. Leave empty to derive from project id."
  type        = string
  default     = ""
}

variable "mlflow_bucket_name" {
  description = "GCS bucket for MLflow artifacts. Leave empty to derive from project id."
  type        = string
  default     = ""
}

variable "cloudsql_instance_name" {
  description = "Cloud SQL instance name for the MLflow backend store."
  type        = string
  default     = "modelrail-mlflow"
}

variable "cloudsql_tier" {
  description = "Cloud SQL machine tier for the MLflow backend."
  type        = string
  default     = "db-f1-micro"
}

variable "cloudsql_database_version" {
  description = "Cloud SQL database version."
  type        = string
  default     = "POSTGRES_15"
}

variable "cloudsql_database_name" {
  description = "Database name inside Cloud SQL for MLflow."
  type        = string
  default     = "mlflow"
}

variable "mlflow_db_user" {
  description = "Database user for MLflow. Password is generated, never committed."
  type        = string
  default     = "mlflow"
}

variable "billing_account_id" {
  description = "Billing account id the budget attaches to. Required for the budget resource; pass with -var."
  type        = string
  default     = ""
}

variable "monthly_budget_amount" {
  description = "Monthly budget amount in USD. No free-trial credit remains (already used up), so this is paid spend; default 50."
  type        = number
  default     = 50
}

variable "budget_alert_emails" {
  description = "Email addresses notified by budget alerts."
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "Extra labels applied to resources that support them."
  type        = map(string)
  default     = {}
}

locals {
  common_labels = merge(
    {
      project     = "modelrail"
      environment = var.environment
      managed_by  = "terraform"
    },
    var.labels,
  )

  dvc_bucket_name    = var.dvc_bucket_name != "" ? var.dvc_bucket_name : "${var.project_id}-modelrail-dvc"
  mlflow_bucket_name = var.mlflow_bucket_name != "" ? var.mlflow_bucket_name : "${var.project_id}-modelrail-mlflow"
}
