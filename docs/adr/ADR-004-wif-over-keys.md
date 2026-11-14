# ADR-004: Workload Identity Federation over JSON service-account keys

- Status: Accepted
- Date: 2026-11-14
- Context: GitHub Actions needs GCP access to plan Terraform, push
  images, and launch training jobs. The usual shortcut is a JSON
  service-account key stored as a repo secret.

## Decision

Use Workload Identity Federation (WIF). GitHub mints a short-lived
OIDC token per run; GCP exchanges it for an access token scoped to
the CI service account. No JSON keys are created, stored, or
committed anywhere. The WIF pool trusts only this repo
(`attribute.repository` condition in `infra/terraform/iam.tf`).

## Alternatives considered

- JSON service-account key in GitHub secrets: works, but the key is
  long-lived, can be exfiltrated, and has to be rotated by hand.
  It is also exactly the kind of credential that ends up committed
  by accident.
- Running everything from a local machine: no audit trail, and the
  pipeline would not be reproducible by anyone else.

## Consequences

- A leaked workflow log contains no credential that outlives the run.
- The trust boundary is one Terraform resource plus one IAM binding;
  review those two places if access ever looks wrong.
- Local development still needs `gcloud auth application-default
  login`; that is a personal credential on a personal machine, not a
  repo secret.
- If WIF is ever misconfigured, CI fails at the auth step with a
  clear error, before any GCP resource is touched.
