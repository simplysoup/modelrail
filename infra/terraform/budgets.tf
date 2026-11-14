# Billing budget: alerts at 50%, 90%, and 100% of the monthly amount.
# Set on day 0, before any cluster exists. The default amount is $50.
# There is no free-trial credit left (already used up), so this is paid
# spend. A budget never stops spending by itself; it
# only alerts. The real cost control is `make down` after every session
# (see infra/README.md) plus the teardown proof in docs/COST.md.
#
# Note: google_billing_budget needs a billing account id. Pass
# var.billing_account_id. If it is empty, the budget is not created,
# so a missing billing account fails loudly in plan output instead of
# silently skipping the budget.

resource "google_billing_budget" "modelrail" {
  count = var.billing_account_id != "" ? 1 : 0

  billing_account = var.billing_account_id
  display_name    = "ModelRail monthly budget"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(floor(var.monthly_budget_amount))
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  dynamic "all_updates_rule" {
    for_each = length(var.budget_alert_emails) > 0 ? [1] : []
    content {
      schema_version                   = "1.0"
      monitoring_notification_channels = local.notification_channels
    }
  }
}
