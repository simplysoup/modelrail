"""Register a ModelRail model version and set an MLflow alias.

Used by the release pipeline (.github/workflows/main.yml) after the
model gate passes. Finds the training run by its git SHA tag, creates
a model version from that run's artifact URI, and sets the requested
alias (candidate or champion).

Standard library only. Needs MLFLOW_TRACKING_URI.
Run from the repo root:

  python -m mcp.register_model --git-sha <SHA> --alias candidate
  python -m mcp.register_model --git-sha <SHA> --alias champion

Environment:
  MLFLOW_TRACKING_URI   MLflow tracking server URL (required)
  MODELRAIL_MODEL_NAME  registered model name (default: mobilenetv3-cifar10)
  MODELRAIL_MODEL_PATH  artifact path inside the run (default: model)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

MODEL_NAME = os.environ.get("MODELRAIL_MODEL_NAME", "mobilenetv3-cifar10")
MODEL_PATH = os.environ.get("MODELRAIL_MODEL_PATH", "model")


def mlflow_request(base, path, payload=None):
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()[:500]
        raise SystemExit("MLflow request failed (%s %s): %s" % (exc.code, url, body))


def find_run_by_git_sha(base, git_sha):
    result = mlflow_request(base, "/api/2.0/mlflow/runs/search", {
        "experiment_ids": ["0"],
        "filter": "tags.git_sha = '%s'" % git_sha,
        "max_results": 1,
        "order_by": ["attributes.start_time DESC"],
    })
    runs = result.get("runs", [])
    if not runs:
        raise SystemExit("no MLflow run found with git_sha tag " + git_sha)
    return runs[0]


def main():
    parser = argparse.ArgumentParser(description="Register a model version and set an alias.")
    parser.add_argument("--git-sha", required=True, help="git SHA logged as a tag on the training run")
    parser.add_argument("--alias", required=True, choices=["candidate", "champion"])
    parser.add_argument("--model", default=MODEL_NAME, help="registered model name")
    args = parser.parse_args()

    base = os.environ.get("MLFLOW_TRACKING_URI")
    if not base:
        raise SystemExit("MLFLOW_TRACKING_URI is not set")

    run = find_run_by_git_sha(base, args.git_sha)
    run_id = run["info"]["run_id"]
    artifact_uri = run["info"]["artifact_uri"].rstrip("/")
    source = artifact_uri + "/" + MODEL_PATH

    version = mlflow_request(base, "/api/2.0/mlflow/model-versions/create", {
        "name": args.model,
        "source": source,
        "run_id": run_id,
    })
    version_number = version["model_version"]["version"]
    mlflow_request(base, "/api/2.0/mlflow/registered-models/alias", {
        "name": args.model,
        "alias": args.alias,
        "version": version_number,
    })
    print("registered %s version %s from run %s, alias=%s" % (
        args.model, version_number, run_id, args.alias))


if __name__ == "__main__":
    main()
