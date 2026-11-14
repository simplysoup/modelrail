# Artifact Registry: one Docker repository for serving and training images.
# Images are pushed by CI only, via Workload Identity Federation (iam.tf).
# No JSON service-account keys anywhere.

resource "google_artifact_registry_repository" "modelrail" {
  location      = var.region
  project       = var.project_id
  repository_id = var.artifact_registry_repo
  description   = "ModelRail container images (training, serving, MCP)."
  format        = "DOCKER"

  docker_config {
    immutable_tags = false
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}
