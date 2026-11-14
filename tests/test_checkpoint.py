"""Tests for train/checkpoint.py: manifest-as-commit-point logic."""

import json
import os

import pytest

from train.checkpoint import LocalCheckpointStore, sha256_file


def test_save_writes_manifest_after_checkpoint(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    manifest = store.save(b"fake-checkpoint-bytes", {"epoch": 2, "val_accuracy": 0.81})
    assert os.path.exists(os.path.join(tmp_checkpoint_dir, "checkpoint.pt"))
    assert os.path.exists(os.path.join(tmp_checkpoint_dir, "manifest.json"))
    assert manifest["epoch"] == 2
    assert manifest["sha256"] == sha256_file(os.path.join(tmp_checkpoint_dir, "checkpoint.pt"))
    assert manifest["size_bytes"] == len(b"fake-checkpoint-bytes")


def test_load_returns_saved_bytes(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    store.save(b"hello-checkpoint", {"epoch": 0})
    assert store.load() == b"hello-checkpoint"


def test_verify_passes_for_good_checkpoint(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    store.save(b"good", {"epoch": 1})
    assert store.verify() is True


def test_verify_fails_when_checkpoint_is_tampered(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    store.save(b"good", {"epoch": 1})
    with open(os.path.join(tmp_checkpoint_dir, "checkpoint.pt"), "wb") as f:
        f.write(b"tampered")
    assert store.verify() is False


def test_load_refuses_tampered_checkpoint(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    store.save(b"good", {"epoch": 1})
    with open(os.path.join(tmp_checkpoint_dir, "checkpoint.pt"), "wb") as f:
        f.write(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.load()


def test_load_manifest_returns_none_when_absent(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    assert store.load_manifest() is None
    assert store.verify() is False
    with pytest.raises(FileNotFoundError):
        store.load()


def test_no_manifest_means_no_commit(tmp_checkpoint_dir):
    # A checkpoint file with no manifest is not a committed checkpoint:
    # simulate a crash between the file write and the manifest write.
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    with open(os.path.join(tmp_checkpoint_dir, "checkpoint.pt"), "wb") as f:
        f.write(b"half-written")
    assert store.load_manifest() is None
    assert store.verify() is False


def test_second_save_overwrites_manifest_atomically(tmp_checkpoint_dir):
    store = LocalCheckpointStore(tmp_checkpoint_dir)
    store.save(b"epoch-0", {"epoch": 0})
    manifest = store.save(b"epoch-1-longer", {"epoch": 1})
    assert manifest["epoch"] == 1
    assert store.load() == b"epoch-1-longer"
    assert not os.path.exists(os.path.join(tmp_checkpoint_dir, "manifest.json.tmp"))
    assert not os.path.exists(os.path.join(tmp_checkpoint_dir, "checkpoint.pt.tmp"))
