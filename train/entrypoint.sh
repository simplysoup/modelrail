#!/bin/sh
# ModelRail training entrypoint: prepare the data if it is not there
# yet, then run the command the Job passes (train by default).
# Keeps the Job manifest simple: it only has to name the training step.
set -e
if [ ! -f /app/data/processed/train-images.npy ]; then
  echo "entrypoint: preparing CIFAR-10 into /app/data/processed"
  python -m data.prepare --params /app/data/params.yaml --out /app/data/processed
fi
exec "$@"
