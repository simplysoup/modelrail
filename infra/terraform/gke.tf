# GKE Autopilot cluster. Autopilot is the default for ModelRail
# (see docs/adr/ADR-001-autopilot-vs-standard.md): no node management,
# per-pod billing, and Spot pricing via pod-level tolerations is not
# available the same way as on Standard, so training on Spot is handled
# as a documented alternative below.
#
# Spot alternative: a Standard cluster with a Spot node pool is the
# documented alternative for training (see ADR-006). This file keeps
# the Autopilot cluster as the only cluster. The Spot node pool resource
# below is guarded by var.enable_spot_node_pool and is a deliberate
# no-op by default: a Spot pool cannot attach to an Autopilot cluster,
# so enabling it requires first replacing this cluster with a Standard
# one. That replacement is a conscious, reviewed change, not a flag flip.

resource "google_container_cluster" "modelrail" {
  name     = var.cluster_name
  project  = var.project_id
  location = var.region

  enable_autopilot = true

  network    = google_compute_network.modelrail.id
  subnetwork = google_compute_subnetwork.modelrail.id

  release_channel {
    channel = var.gke_release_channel
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Workload Identity is on by default on Autopilot; set explicitly so
  # the intent is visible. Workloads use their own Kubernetes service
  # accounts bound to least-privilege Google service accounts (iam.tf).
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Autopilot manages logging/monitoring; keep the standard components.
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }

  deletion_protection = false

  resource_labels = local.common_labels

  depends_on = [
    google_project_service.apis,
    google_service_networking_connection.private_vpc_connection,
  ]
}

# Spot node pool, documented alternative for training on a Standard
# cluster. Guarded off by default. Do NOT enable this flag against the
# Autopilot cluster above: terraform will fail, by design, because a
# node pool cannot be added to an Autopilot cluster. To use Spot
# training, replace the Autopilot cluster with a Standard cluster
# (see docs/adr/ADR-006-spot-training.md), then set
# enable_spot_node_pool = true.
resource "google_container_node_pool" "spot_training" {
  count = var.enable_spot_node_pool ? 1 : 0

  name     = "spot-training"
  project  = var.project_id
  location = var.region
  cluster  = google_container_cluster.modelrail.name

  autoscaling {
    min_node_count = var.spot_min_nodes
    max_node_count = var.spot_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.spot_machine_type
    spot         = true

    # Training jobs tolerate preemption and resume from checkpoints
    # (see docs/DRILLS.md). Taint keeps non-training pods off Spot nodes.
    taint {
      key    = "workload"
      value  = "training"
      effect = "NO_SCHEDULE"
    }

    labels = merge(local.common_labels, { pool = "spot-training" })

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }
}
