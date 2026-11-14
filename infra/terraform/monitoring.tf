# Cloud Monitoring: dashboard plus alert policies for the SLOs in
# docs/SLOs.md. Availability SLO 99%, latency SLO p95 under 100 ms.
# Alerts fire on error-budget burn, not on single spikes, so a brief
# blip does not page anyone at 3am.

resource "google_monitoring_dashboard" "modelrail" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "ModelRail"
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "Prediction request rate"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter      = "metric.type=\"custom.googleapis.com/modelrail/predict_requests_total\" resource.type=\"k8s_container\""
                  aggregation = { perSeriesAligner = "ALIGN_RATE" }
                }
              }
              plotType = "LINE"
            }]
          }
        },
        {
          title = "p95 prediction latency (ms)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/modelrail/predict_latency_ms\" resource.type=\"k8s_container\""
                  aggregation = {
                    perSeriesAligner   = "ALIGN_PERCENTILE_95"
                    crossSeriesReducer = "REDUCE_PERCENTILE_95"
                  }
                }
              }
              plotType = "LINE"
            }]
          }
        },
        {
          title = "Prediction error rate"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter      = "metric.type=\"custom.googleapis.com/modelrail/predict_errors_total\" resource.type=\"k8s_container\""
                  aggregation = { perSeriesAligner = "ALIGN_RATE" }
                }
              }
              plotType = "LINE"
            }]
          }
        },
        {
          title = "Training jobs (running / failed)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter      = "metric.type=\"kubernetes.io/container/cpu/core_usage_time\" resource.type=\"k8s_container\" resource.label.namespace_name=\"modelrail\""
                  aggregation = { perSeriesAligner = "ALIGN_RATE" }
                }
              }
              plotType = "LINE"
            }]
          }
        },
      ]
    }
  })

  depends_on = [google_project_service.apis]
}

# Notification channel: email. Add real addresses via
# var.budget_alert_emails or a second channel here. The channel is
# created only when at least one email is provided.
resource "google_monitoring_notification_channel" "email" {
  count        = length(var.budget_alert_emails) > 0 ? 1 : 0
  project      = var.project_id
  display_name = "ModelRail alerts"
  type         = "email"

  labels = {
    email_address = var.budget_alert_emails[0]
  }
}

locals {
  notification_channels = length(var.budget_alert_emails) > 0 ? [google_monitoring_notification_channel.email[0].name] : []
}

# Fast-burn alert: error rate above 5% for 5 minutes. This is the
# canary auto-rollback signal as well as the paging signal.
resource "google_monitoring_alert_policy" "high_error_rate" {
  project      = var.project_id
  display_name = "ModelRail high prediction error rate"
  combiner     = "OR"

  conditions {
    display_name = "Error rate above 5% for 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/modelrail/predict_errors_total\" resource.type=\"k8s_container\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = local.notification_channels
  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Prediction error rate above 5% for 5 minutes. Check the canary status and the model gate results. Runbook: docs/DRILLS.md."
    mime_type = "text/markdown"
  }
}

# Latency SLO burn: p95 above 100 ms for 10 minutes.
resource "google_monitoring_alert_policy" "high_latency" {
  project      = var.project_id
  display_name = "ModelRail p95 latency above SLO"
  combiner     = "OR"

  conditions {
    display_name = "p95 latency above 100 ms for 10 minutes"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/modelrail/predict_latency_ms\" resource.type=\"k8s_container\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 100
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_PERCENTILE_95"
      }
    }
  }

  notification_channels = local.notification_channels
  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "p95 prediction latency above the 100 ms SLO for 10 minutes. Check pod CPU, HPA state, and model version. Runbook: docs/DRILLS.md."
    mime_type = "text/markdown"
  }
}

# Availability: serving pods unavailable. Uses the Kubernetes
# container uptime metric as a proxy until the service exposes its own
# availability metric; the custom metric replaces it once serving ships.
resource "google_monitoring_alert_policy" "serving_down" {
  project      = var.project_id
  display_name = "ModelRail serving unavailable"
  combiner     = "OR"

  conditions {
    display_name = "No serving pods reporting for 5 minutes"
    condition_absent {
      filter   = "metric.type=\"kubernetes.io/container/uptime\" resource.type=\"k8s_container\" resource.label.namespace_name=\"modelrail\" resource.label.container_name=\"serving\""
      duration = "300s"
    }
  }

  notification_channels = local.notification_channels
  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "No serving container has reported uptime for 5 minutes. Check the Deployment, the rollout status, and GKE events. Runbook: docs/DRILLS.md."
    mime_type = "text/markdown"
  }
}
