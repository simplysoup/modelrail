# ModelRail Makefile
# Portfolio project. `make up` provisions GCP; `make down` destroys it.
# Teardown discipline: run `make down` after every work session.
# Nothing here has been applied to GCP yet.

TF_DIR := infra/terraform
CLUSTER ?= modelrail
REGION ?= northamerica-northeast2
NAMESPACE ?= modelrail

.PHONY: help up down plan validate fmt test mcp-test web-serve clean

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-12s %s\n", $$1, $$2}'

plan: ## Terraform plan (no changes applied)
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) plan

validate: ## Terraform fmt check + validate
	terraform fmt -check -recursive $(TF_DIR)
	terraform -chdir=$(TF_DIR) init -backend=false
	terraform -chdir=$(TF_DIR) validate

fmt: ## Format Terraform files
	terraform fmt -recursive $(TF_DIR)

up: ## Provision infra, then deploy MLflow to GKE
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) apply
	gcloud container clusters get-credentials $(CLUSTER) --region $(REGION)
	kubectl apply -k k8s/base
	kubectl rollout status deployment/mlflow -n $(NAMESPACE)

down: ## Destroy everything (teardown discipline: run after every session)
	terraform -chdir=$(TF_DIR) destroy
	@echo "Confirm teardown with: gcloud container clusters list --project \$${GCP_PROJECT_ID}"
	@echo "Then record the proof in docs/COST.md."

test: ## Run MCP gating tests (stdlib unittest, no pytest needed)
	python -m unittest discover -s mcp/tests -v

mcp-test: test ## Alias for test

web-serve: ## Serve the in-browser demo locally (needs web/model-int8.onnx)
	python -m http.server -d web 8000

clean: ## Remove local build and cache artefacts (never touches GCP)
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
