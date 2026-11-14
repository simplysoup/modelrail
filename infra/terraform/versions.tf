# ModelRail - Terraform configuration
# Portfolio project. Nothing here has been applied to GCP.
# Region: northamerica-northeast2 (Toronto). One GCP project, set via
# the project_id variable. No real project id is committed anywhere.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Remote state in GCS. Bootstrap first (see infra/README.md):
  #   gsutil mb -p <PROJECT_ID> -l northamerica-northeast2 gs://<PROJECT_ID>-tfstate
  #   gsutil versioning set on gs://<PROJECT_ID>-tfstate
  # Then replace the placeholder bucket name below with the real bucket.
  # The bucket name is intentionally a placeholder: no real GCP resource
  # name is committed in this repo.
  backend "gcs" {
    bucket = "REPLACE-ME-modelrail-tfstate"
    prefix = "modelrail/terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
