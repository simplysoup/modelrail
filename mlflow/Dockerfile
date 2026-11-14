# ModelRail MLflow tracking server image. Portfolio project.
# The upstream mlflow image does not bundle a Postgres driver, and the
# backend store here is Cloud SQL Postgres, so install psycopg2-binary
# on top. Nothing else changes: the entrypoint stays the image default,
# and k8s/base/mlflow.yaml runs `mlflow server` with the Postgres URI.
FROM ghcr.io/mlflow/mlflow:v2.20.1
RUN pip install --no-cache-dir psycopg2-binary==2.9.10
