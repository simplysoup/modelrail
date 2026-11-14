# ModelRail MCP server

Portfolio project. A small MCP server over the ModelRail platform,
stdio transport, standard library only. It reuses the read/write/delete
separation from the Environics MCP layer: reads are free, writes are
gated and audited, and there is no delete family at all.

## Tools

Read (no approval needed):

- `list_models` - registered models and aliases (candidate, champion)
- `compare_runs` - two MLflow runs: params, metrics, git SHA, data hash
- `get_deploy_status` - serving rollout status
- `get_slo_status` - availability/latency SLOs and error budget

Write (gated):

- `promote_model` - move a model version to `candidate` or `champion`
- `rollback` - roll serving back to the previous model version

Write tools require `approval: true` and a non-empty `reason` in the
call arguments. Without both, the call is rejected before anything
happens. Every accepted write appends one JSON line to the audit log
(`mcp/audit.log` by default, `MODELRAIL_AUDIT_LOG` to override).

## Running

```sh
python mcp/server.py
```

It speaks JSON-RPC 2.0 over stdio (`initialize`, `ping`,
`tools/list`, `tools/call`). Send one JSON object per line.

## Backends

- `MODELRAIL_BACKEND=fake` (default): in-memory demo data. Used by
  tests and local demos. Never touches GCP.
- `MODELRAIL_BACKEND=real`: talks to MLflow over HTTP
  (`MLFLOW_TRACKING_URI`) and to the cluster via `kubectl` for deploy
  status and rollback. Anything it cannot reach returns an error
  instead of invented data. `get_slo_status` and `promote_model` on
  the real backend are explicitly not wired yet and say so; the
  release pipeline (`.github/workflows/main.yml`) owns promotion.

## Tests

```sh
python -m pytest mcp/tests/ -q
# or, with no pytest installed:
python -m unittest discover -s mcp/tests -v
```

Tests cover permission gating: writes without approval are rejected,
writes with approval succeed and land in the audit log, read tools
need no approval, and no delete tool is listed.
