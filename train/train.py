"""Train MobileNetV3-small on CIFAR-10 for ModelRail.

Portfolio project. CPU-friendly by design: the model is deliberately
boring, the platform is what is being judged.

Run:
    python -m train.train --params data/params.yaml --data data/processed --out models/run
    python -m train.train --params data/params.yaml --data data/processed --out models/run --subset 500

Checkpoint/resume: every epoch writes a checkpoint through
train/checkpoint.py, whose manifest is the commit point. Killing the
training pod mid-run and restarting with the same --out resumes from the
last committed manifest, not from a half-written file. GCS checkpoint
URIs (gs://...) use the same protocol with conditional writes.

MLflow: imported lazily. If mlflow is installed and MLFLOW_TRACKING_URI
is set, runs log there; otherwise they log to a local ./mlruns directory.
If mlflow is not installed, params and metrics are written to
models/run/mlflow-fallback.json instead. Every run logs params, metrics,
the git SHA, and the DVC data hash from prepare-metrics.json.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from train.checkpoint import LocalCheckpointStore, store_for_uri  # noqa: E402


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def load_params(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_model(num_classes: int = 10, pretrained: bool = True):
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    weights = MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
    model = mobilenet_v3_small(weights=weights)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = __import__("torch").nn.Linear(in_features, num_classes)
    return model


def load_processed(data_dir: str, subset: int | None = None):
    def load(split: str):
        images = np.load(os.path.join(data_dir, f"{split}-images.npy"))
        labels = np.load(os.path.join(data_dir, f"{split}-labels.npy"))
        if subset is not None:
            images, labels = images[:subset], labels[:subset]
        return images, labels

    return load("train"), load("val")


def evaluate_accuracy(model, loader, device: str) -> float:
    import torch

    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            outputs = model(images.to(device))
            correct += (outputs.argmax(1).cpu() == labels).sum().item()
            total += len(labels)
    return correct / max(total, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train MobileNetV3-small on CIFAR-10.")
    parser.add_argument("--params", default="data/params.yaml")
    parser.add_argument("--data", default="data/processed")
    parser.add_argument("--out", default="models/run")
    parser.add_argument("--subset", type=int, default=None, help="Train on only N samples (CI smoke run).")
    parser.add_argument("--checkpoint-uri", default=None, help="gs:// URI for checkpoints; default is --out.")
    parser.add_argument("--epochs", type=int, default=None, help="Override params.train.epochs.")
    args = parser.parse_args()

    params = load_params(args.params)
    train_cfg, data_cfg = params["train"], params["data"]
    epochs = args.epochs if args.epochs is not None else train_cfg["epochs"]
    device = "cpu"  # CPU-only by design; Spot CPU nodes in the GKE plan.
    os.makedirs(args.out, exist_ok=True)

    # Data hash from the prepare stage, for MLflow lineage.
    data_hash = "unknown"
    prepare_metrics = os.path.join(args.data, "prepare-metrics.json")
    if os.path.exists(prepare_metrics):
        with open(prepare_metrics) as f:
            data_hash = json.load(f).get("data_hash", {}).get("train", "unknown")

    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    (train_images, train_labels), (val_images, val_labels) = load_processed(args.data, args.subset)
    mean = torch.tensor(data_cfg["mean"]).view(1, 3, 1, 1)
    std = torch.tensor(data_cfg["std"]).view(1, 3, 1, 1)

    def to_tensor(images, labels):
        x = torch.from_numpy(images).permute(0, 3, 1, 2).float() / 255.0
        x = (x - mean) / std
        return TensorDataset(x, torch.from_numpy(labels))

    train_loader = DataLoader(
        to_tensor(train_images, train_labels),
        batch_size=train_cfg["batch_size"], shuffle=True,
        num_workers=train_cfg["num_workers"],
    )
    val_loader = DataLoader(
        to_tensor(val_images, val_labels),
        batch_size=train_cfg["batch_size"], shuffle=False,
        num_workers=train_cfg["num_workers"],
    )

    model = build_model(data_cfg["num_classes"], train_cfg["pretrained"])
    optimizer = torch.optim.Adam(
        model.parameters(), lr=train_cfg["learning_rate"], weight_decay=train_cfg["weight_decay"]
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    store = store_for_uri(args.checkpoint_uri) if args.checkpoint_uri else LocalCheckpointStore(args.out)
    start_epoch = 0
    manifest = store.load_manifest() if isinstance(store, LocalCheckpointStore) else None
    if train_cfg.get("resume") and manifest is not None and store.verify(manifest):
        print(f"resuming from committed manifest: epoch {manifest.get('epoch')}")
        payload = torch.load(io.BytesIO(store.load(manifest)), map_location=device)
        model.load_state_dict(payload["model_state"])
        optimizer.load_state_dict(payload["optimizer_state"])
        start_epoch = int(payload["epoch"]) + 1
    elif manifest is not None:
        print("manifest present but checkpoint failed verification; starting from scratch")

    # MLflow, lazily. Local ./mlruns when no tracking URI is set.
    mlflow_run = None
    try:
        import mlflow

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "./mlruns"))
        mlflow.set_experiment("modelrail-cifar10")
        mlflow_run = mlflow.start_run()
        mlflow.log_params({
            "model": train_cfg["model"], "epochs": epochs,
            "batch_size": train_cfg["batch_size"],
            "learning_rate": train_cfg["learning_rate"],
            "weight_decay": train_cfg["weight_decay"],
            "pretrained": train_cfg["pretrained"],
            "subset": args.subset or "full",
        })
        mlflow.log_param("git_sha", git_sha())
        mlflow.log_param("data_hash", data_hash)
    except ImportError:
        print("mlflow not installed; logging params and metrics to mlflow-fallback.json")

    history = []
    best_val = 0.0
    epochs_without_improvement = 0
    try:
        for epoch in range(start_epoch, epochs):
            model.train()
            running_loss, seen = 0.0, 0
            t0 = time.time()
            for images, labels in train_loader:
                optimizer.zero_grad()
                loss = criterion(model(images), labels)
                loss.backward()
                optimizer.step()
                running_loss += loss.item() * len(labels)
                seen += len(labels)
            scheduler.step()
            val_acc = evaluate_accuracy(model, val_loader, device)
            train_loss = running_loss / max(seen, 1)
            record = {
                "epoch": epoch, "train_loss": round(train_loss, 4),
                "val_accuracy": round(val_acc, 4),
                "seconds": round(time.time() - t0, 1),
            }
            history.append(record)
            print(f"epoch {epoch}: train_loss={train_loss:.4f} val_accuracy={val_acc:.4f}")
            if mlflow_run is not None:
                import mlflow

                mlflow.log_metrics({"train_loss": train_loss, "val_accuracy": val_acc}, step=epoch)
            # Commit a checkpoint at the end of every epoch.
            buffer = io.BytesIO()
            torch.save({
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "epoch": epoch,
                "val_accuracy": val_acc,
            }, buffer)
            store.save(buffer.getvalue(), {
                "epoch": epoch, "val_accuracy": val_acc,
                "git_sha": git_sha(), "data_hash": data_hash,
            })
            if val_acc > best_val:
                best_val, epochs_without_improvement = val_acc, 0
            else:
                epochs_without_improvement += 1
            if epochs_without_improvement >= train_cfg["early_stopping_patience"]:
                print(f"early stopping after {epochs_without_improvement} epochs without improvement")
                break
    finally:
        if mlflow_run is not None:
            import mlflow

            mlflow.end_run()

    metrics = {
        "best_val_accuracy": round(best_val, 4),
        "final_val_accuracy": round(history[-1]["val_accuracy"], 4) if history else 0.0,
        "epochs_run": len(history),
        "git_sha": git_sha(),
        "data_hash": data_hash,
        "history": history,
    }
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    if mlflow_run is None:
        with open(os.path.join(args.out, "mlflow-fallback.json"), "w") as f:
            json.dump({"params": train_cfg, "metrics": metrics,
                       "git_sha": git_sha(), "data_hash": data_hash}, f, indent=2, sort_keys=True)
    print(f"train: best val accuracy {best_val:.4f}; metrics written to {args.out}/metrics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
