# VPC for ModelRail. Private nodes, no public IPs on the cluster nodes,
# Cloud NAT for outbound access (image pulls, package installs).

resource "google_compute_network" "modelrail" {
  name                    = "modelrail-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "modelrail" {
  name          = "modelrail-subnet"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.modelrail.id
  ip_cidr_range = "10.10.0.0/20"

  # Secondary ranges for GKE pods and services.
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }

  private_ip_google_access = true
}

# Private service access range for Cloud SQL private IP.
resource "google_compute_global_address" "private_service_range" {
  name          = "modelrail-private-service-range"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.modelrail.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.modelrail.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]

  depends_on = [google_project_service.apis]
}

resource "google_compute_router" "modelrail" {
  name    = "modelrail-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.modelrail.id
}

resource "google_compute_router_nat" "modelrail" {
  name                               = "modelrail-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.modelrail.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
