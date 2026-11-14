"""ModelRail platform MCP server (stdio, standard library only).

Portfolio project. This is a small control plane over the ModelRail
platform: read tools report on models, runs, deploys, and SLOs; write
tools promote a model or roll back a deploy. Write tools are gated
behind an explicit approval parameter and every write is appended to
an audit log.

Protocol: JSON-RPC 2.0 over stdio, MCP-style methods:
  initialize, ping, tools/list, tools/call.
Run it with:  python mcp/server.py

Backends, selected by MODELRAIL_BACKEND:
  fake  (default) - in-memory demo data, used by tests and local demos.
                      Never talks to GCP.
  real  - talks to MLflow over HTTP (MLFLOW_TRACKING_URI) and to the
          cluster via kubectl for deploy status. Requires those
          endpoints to be reachable; otherwise the tool returns a
          clear error instead of invented data.

Environment:
  MODELRAIL_BACKEND       fake | real (default: fake)
  MLFLOW_TRACKING_URI     MLflow tracking server URL (real backend)
  MODELRAIL_AUDIT_LOG     audit log path (default: mcp/audit.log)
  MODELRAIL_NAMESPACE     Kubernetes namespace (default: modelrail)
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

AUDIT_LOG = os.environ.get("MODELRAIL_AUDIT_LOG", "mcp/audit.log")
NAMESPACE = os.environ.get("MODELRAIL_NAMESPACE", "modelrail")

READ_TOOLS = ["list_models", "compare_runs", "get_deploy_status", "get_slo_status"]
WRITE_TOOLS = ["promote_model", "rollback"]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS

TOOL_DESCRIPTIONS = {
    "list_models": "List registered models and their aliases (candidate, champion). Read-only.",
    "compare_runs": "Compare two MLflow runs by id: params, metrics, git SHA, data hash. Read-only.",
    "get_deploy_status": "Current serving rollout status: model version, canary step, replica health. Read-only.",
    "get_slo_status": "Availability and latency SLO status and remaining error budget. Read-only.",
    "promote_model": "Move a model version to an alias (candidate or champion). Write: requires approval=true and a reason; audited.",
    "rollback": "Roll back serving to the previous model version. Write: requires approval=true and a reason; audited.",
}


class ToolError(Exception):
    """A tool call failed for a reason the caller should see."""


# ---------------------------------------------------------------- backends

class FakeBackend:
    """In-memory demo backend. Deterministic, no network, no GCP."""

    def __init__(self):
        self.models = {
            "mobilenetv3-cifar10": {
                "versions": ["3", "2", "1"],
                "aliases": {"champion": "2", "candidate": "3"},
            }
        }
        self.runs = {
            "run-a": {"accuracy": 0.912, "git_sha": "abc123", "data_hash": "dvc:aaa", "params": {"lr": 0.001}},
            "run-b": {"accuracy": 0.905, "git_sha": "def456", "data_hash": "dvc:bbb", "params": {"lr": 0.002}},
        }
        self.deploy = {"model_version": "2", "alias": "champion", "canary_step": "100%", "replicas_ready": "2/2"}
        self.slo = {"availability_slo": 0.99, "availability_observed": 0.999, "p95_latency_ms": 62,
                    "p95_slo_ms": 100, "error_budget_remaining": 0.82}

    def list_models(self, args):
        return {"models": self.models}

    def compare_runs(self, args):
        run_ids = args.get("run_ids")
        if not run_ids or len(run_ids) != 2:
            raise ToolError("compare_runs needs exactly two run_ids")
        missing = [r for r in run_ids if r not in self.runs]
        if missing:
            raise ToolError("unknown run(s): " + ", ".join(missing))
        return {"runs": {r: self.runs[r] for r in run_ids}}

    def get_deploy_status(self, args):
        return self.deploy

    def get_slo_status(self, args):
        return self.slo

    def promote_model(self, args):
        model = args.get("model")
        version = str(args.get("version"))
        alias = args.get("alias")
        if alias not in ("candidate", "champion"):
            raise ToolError("alias must be 'candidate' or 'champion'")
        if model not in self.models:
            raise ToolError("unknown model: " + str(model))
        self.models[model]["aliases"][alias] = version
        return {"model": model, "version": version, "alias": alias, "status": "promoted"}

    def rollback(self, args):
        current = self.deploy["model_version"]
        previous = str(int(current) - 1) if current.isdigit() and int(current) > 1 else "1"
        self.deploy = dict(self.deploy, model_version=previous, alias="champion", canary_step="100%")
        return {"rolled_back_from": current, "rolled_back_to": previous, "status": "rolled back"}


class RealBackend:
    """Talks to MLflow over HTTP and to the cluster via kubectl.

    Anything it cannot reach returns a ToolError, never invented data.
    """

    def __init__(self):
        self.mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "").rstrip("/")
        if not self.mlflow_uri:
            raise ToolError("real backend needs MLFLOW_TRACKING_URI set")

    def _mlflow_get(self, path):
        url = self.mlflow_uri + path
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as exc:
            raise ToolError("MLflow unreachable at " + url + ": " + str(exc))

    def _kubectl(self, *argv):
        try:
            out = subprocess.run(["kubectl", *argv, "-n", NAMESPACE],
                                 capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            raise ToolError("kubectl not found on PATH")
        if out.returncode != 0:
            raise ToolError("kubectl failed: " + out.stderr.strip())
        return out.stdout.strip()

    def list_models(self, args):
        data = self._mlflow_get("/api/2.0/mlflow/registered-models/search")
        return {"models": data.get("registered_models", [])}

    def compare_runs(self, args):
        run_ids = args.get("run_ids")
        if not run_ids or len(run_ids) != 2:
            raise ToolError("compare_runs needs exactly two run_ids")
        runs = {}
        for run_id in run_ids:
            runs[run_id] = self._mlflow_get("/api/2.0/mlflow/runs/get?run_id=" + run_id)
        return {"runs": runs}

    def get_deploy_status(self, args):
        status = self._kubectl("argo", "rollouts", "get", "rollout", "modelrail-serve", "-o", "json")
        return {"rollout": json.loads(status)}

    def get_slo_status(self, args):
        raise ToolError(
            "get_slo_status on the real backend is not wired yet: "
            "Cloud Monitoring has no stdlib client here. Check the "
            "dashboard in Terraform (infra/terraform/monitoring.tf) "
            "or wire a Monitoring API call before using this tool live."
        )

    def promote_model(self, args):
        raise ToolError(
            "promote_model on the real backend is not wired yet: "
            "alias updates must go through the release pipeline "
            "(.github/workflows/main.yml) or an MLflow client call. "
            "Refusing to guess at the registry API."
        )

    def rollback(self, args):
        self._kubectl("argo", "rollouts", "undo", "rollout", "modelrail-serve")
        return {"status": "rollback requested via Argo Rollouts"}


def get_backend():
    kind = os.environ.get("MODELRAIL_BACKEND", "fake").lower()
    if kind == "real":
        return RealBackend()
    if kind == "fake":
        return FakeBackend()
    raise ToolError("unknown MODELRAIL_BACKEND: " + kind)


# ---------------------------------------------------------------- gating

def require_approval(tool, args):
    """Write tools need approval=true and a non-empty reason. No exceptions."""
    if args.get("approval") is not True:
        raise ToolError(
            "tool '%s' is a write tool and needs approval=true "
            "(explicit approval parameter) plus a reason" % tool
        )
    reason = args.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ToolError("tool '%s' needs a non-empty reason for the audit log" % tool)


def append_audit(tool, args, result):
    """Append one JSON line per write. Best effort: a failed audit write
    fails the tool call, so a write is never silent."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": {k: v for k, v in args.items()},
        "result": result,
    }
    os.makedirs(os.path.dirname(os.path.abspath(AUDIT_LOG)), exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- JSON-RPC

def handle_request(request, backend):
    method = request.get("method")
    req_id = request.get("id")

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({"protocolVersion": "2024-11-05",
                   "serverInfo": {"name": "modelrail-mcp", "version": "0.1.0"}})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [
            {"name": name, "description": TOOL_DESCRIPTIONS[name],
             "inputSchema": {"type": "object", "properties": {}}}
            for name in ALL_TOOLS
        ]})
    if method == "tools/call":
        params = request.get("params") or {}
        tool = params.get("name")
        args = params.get("arguments") or {}
        if tool not in ALL_TOOLS:
            return err(-32602, "unknown tool: " + str(tool) + " (no delete tools exist)")
        try:
            if tool in WRITE_TOOLS:
                require_approval(tool, args)
            result = getattr(backend, tool)(args)
            if tool in WRITE_TOOLS:
                append_audit(tool, args, result)
            return ok({"content": [{"type": "text", "text": json.dumps(result, indent=2)}]})
        except ToolError as exc:
            return err(-32603, str(exc))
        except Exception as exc:  # noqa: BLE001 - surface, do not crash the loop
            return err(-32603, "tool failed: " + str(exc))
    return err(-32601, "unknown method: " + str(method))


def main():
    try:
        backend = get_backend()
    except ToolError as exc:
        sys.stderr.write("modelrail-mcp: " + str(exc) + "\n")
        sys.exit(1)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(handle_request(request, backend)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
