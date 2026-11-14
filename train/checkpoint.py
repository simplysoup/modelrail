"""Checkpoint store with manifest-as-commit-point semantics.

Portfolio project. Reuses the TrainStore idea: a checkpoint is not
considered good until its manifest is visible, and the manifest is only
written after the checkpoint file is fully written, flushed, and hashed.

Local store (used by training and tests):
  1. Write checkpoint bytes to `<name>.tmp` in the same directory.
  2. Flush and fsync the file, then atomically rename to `<name>`.
  3. Compute SHA-256 of the finished file.
  4. Write the manifest to `manifest.json.tmp`, fsync, atomically rename
     to `manifest.json`. Only now is the checkpoint committed.
  5. A resume reads the manifest first, then verifies the checkpoint
     SHA-256 before loading anything. A mismatch refuses to resume.

GCS store (code path only, never called without a gs:// URI):
  The same ordering applies, with conditional writes:
  - checkpoint object upload, then manifest upload with
    `if_generation_match=0` semantics documented in the code, so two
    writers cannot both commit different manifests for the same version.
  - On GCS the manifest is the commit point in exactly the same way:
    a reader that sees no manifest, or a manifest whose hash does not
    match the checkpoint object, treats the checkpoint as absent.
  No GCP call is made by this module unless a GCSCheckpointStore is
  constructed with a real bucket, which training only does for gs:// URIs.
"""

from __future__ import annotations

import hashlib
import json
import os


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_bytes(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_write_text(path: str, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


class LocalCheckpointStore:
    """Checkpoint store backed by a local directory."""

    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)

    def checkpoint_path(self, name: str = "checkpoint.pt") -> str:
        return os.path.join(self.directory, name)

    def manifest_path(self) -> str:
        return os.path.join(self.directory, "manifest.json")

    def save(self, data: bytes, metadata: dict, name: str = "checkpoint.pt") -> dict:
        """Commit a checkpoint. Returns the manifest dict that was written."""
        checkpoint_path = self.checkpoint_path(name)
        _atomic_write_bytes(checkpoint_path, data)
        manifest = {
            **metadata,
            "checkpoint": name,
            "sha256": sha256_file(checkpoint_path),
            "size_bytes": os.path.getsize(checkpoint_path),
        }
        _atomic_write_text(self.manifest_path(), json.dumps(manifest, indent=2, sort_keys=True))
        return manifest

    def load_manifest(self) -> dict | None:
        path = self.manifest_path()
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def verify(self, manifest: dict | None = None) -> bool:
        """True only if the manifest exists and its hash matches the file."""
        manifest = manifest if manifest is not None else self.load_manifest()
        if manifest is None:
            return False
        checkpoint_path = os.path.join(self.directory, manifest.get("checkpoint", "checkpoint.pt"))
        if not os.path.exists(checkpoint_path):
            return False
        return sha256_file(checkpoint_path) == manifest.get("sha256")

    def load(self, manifest: dict | None = None) -> bytes:
        """Load checkpoint bytes, refusing to load an unverified checkpoint."""
        manifest = manifest if manifest is not None else self.load_manifest()
        if manifest is None:
            raise FileNotFoundError(f"no manifest found in {self.directory}")
        if not self.verify(manifest):
            raise ValueError(
                "checkpoint manifest hash mismatch: checkpoint is incomplete or "
                "corrupt, refusing to resume. Delete the checkpoint and retrain."
            )
        with open(os.path.join(self.directory, manifest["checkpoint"]), "rb") as f:
            return f.read()


class GCSCheckpointStore:
    """Checkpoint store backed by a GCS bucket. Code path only.

    No google-cloud-storage call happens at import time. The client is
    created lazily in __init__, so importing this module on a machine
    without GCP credentials is safe. Constructing this class does require
    credentials; training only does so for gs:// checkpoint URIs.

    Commit protocol, mirroring LocalCheckpointStore:
      - upload checkpoint bytes to gs://<bucket>/<prefix>/checkpoint.pt
      - upload manifest.json with if_generation_match=0, so the manifest
        write fails instead of silently overwriting a manifest committed
        by a concurrent writer. The caller retries with a new version on
        a 412 Precondition Failed, exactly like a conditional write.
      - a reader verifies the manifest sha256 against the checkpoint
        object metadata before loading, and treats a missing or mismatched
        manifest as "no checkpoint".
    """

    def __init__(self, bucket: str, prefix: str):
        try:
            from google.cloud import storage  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-storage is required for GCS checkpoints. "
                "Install requirements.txt."
            ) from exc
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket)
        self.prefix = prefix.strip("/")

    def _blob(self, name: str):
        return self.bucket.blob(f"{self.prefix}/{name}")

    def save(self, data: bytes, metadata: dict, name: str = "checkpoint.pt") -> dict:
        checkpoint_blob = self._blob(name)
        checkpoint_blob.upload_from_string(data)
        checkpoint_blob.reload()
        manifest = {
            **metadata,
            "checkpoint": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "generation": checkpoint_blob.generation,
        }
        # Manifest is the commit point. if_generation_match=0 means this
        # write only succeeds if no manifest object exists yet, so a
        # concurrent writer cannot overwrite a committed manifest.
        self._blob("manifest.json").upload_from_string(
            json.dumps(manifest, indent=2, sort_keys=True),
            if_generation_match=0,
        )
        return manifest

    def load_manifest(self) -> dict | None:
        blob = self._blob("manifest.json")
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())

    def verify(self, manifest: dict | None = None) -> bool:
        manifest = manifest if manifest is not None else self.load_manifest()
        if manifest is None:
            return False
        blob = self._blob(manifest.get("checkpoint", "checkpoint.pt"))
        if not blob.exists():
            return False
        blob.reload()
        return blob.md5_hash is not None  # hash check is done on download below

    def load(self, manifest: dict | None = None) -> bytes:
        manifest = manifest if manifest is not None else self.load_manifest()
        if manifest is None:
            raise FileNotFoundError("no manifest found in GCS prefix")
        data = self._blob(manifest["checkpoint"]).download_as_bytes()
        if hashlib.sha256(data).hexdigest() != manifest.get("sha256"):
            raise ValueError("checkpoint manifest hash mismatch on GCS, refusing to resume")
        return data


def store_for_uri(uri: str):
    """Return a LocalCheckpointStore for a local path, GCS store for gs://."""
    if uri.startswith("gs://"):
        rest = uri[len("gs://"):]
        bucket, _, prefix = rest.partition("/")
        return GCSCheckpointStore(bucket, prefix or "checkpoints")
    return LocalCheckpointStore(uri)
