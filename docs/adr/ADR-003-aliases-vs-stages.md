# ADR-003: MLflow aliases instead of stages

- Status: Accepted
- Date: 2026-11-14
- Context: Models need a promotion path (newly trained -> tested ->
  live) and a rollback path. MLflow offers both the old stage model
  (Staging/Production/Archived) and aliases.

## Decision

Use aliases: `candidate` and `champion`. The release pipeline
registers a gated model as `candidate`, the canary proves it, and
promotion moves `champion` to the new version. Rollback moves
`champion` back to the previous version.

## Alternatives considered

- MLflow stages (Staging/Production): the older model, still
  supported, but stages are a fixed three-state enum with no room
  for a canary state, and the MLflow docs now recommend aliases.
- A version-number convention with no registry state: fragile, and
  it puts release state in people's heads instead of the registry.

## Consequences

- Serving loads the model by alias, never by a hardcoded version, so
  promotion and rollback are registry operations, not redeploys.
- The MCP `promote_model` and `rollback` tools operate on aliases,
  which keeps the control plane small and auditable.
- Aliases are per-model, so a bad alias change affects one model,
  not the whole registry.
