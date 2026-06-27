"""
Storage abstraction for local and cloud dataset storage.

LocalStorage  — reads/writes the local data/ directory (current default)
GCSStorage    — reads/writes a GCS bucket (Phase 2, Cloud Run)

Functions in downloader.py and schema.py accept a Storage instance so
the storage backend can be swapped without touching business logic.
Pandas and pyarrow accept both local paths and GCS URIs (gs://...) natively,
so the uri() method is all that's needed for Parquet I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    def read_text(self, key: str) -> str: ...
    def write_text(self, key: str, content: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def find(self, filename: str) -> list[str]: ...
    def uri(self, key: str) -> str: ...


class LocalStorage:
    """Reads and writes the local filesystem under a root directory."""

    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)

    def read_text(self, key: str) -> str:
        return (self.root / key).read_text()

    def write_text(self, key: str, content: str) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def find(self, filename: str) -> list[str]:
        """Return all keys (relative to root) whose filename matches."""
        if not self.root.exists():
            return []
        return sorted(
            str(p.relative_to(self.root))
            for p in self.root.rglob(filename)
        )

    def uri(self, key: str) -> str:
        """Absolute path string — accepted by pandas/pyarrow for Parquet I/O."""
        return str((self.root / key).resolve())


class GCSStorage:
    """
    Phase 2 — reads/writes a GCS bucket.
    Requires: google-cloud-storage, gcsfs (for pandas Parquet I/O via fsspec).

    Install: pip install google-cloud-storage gcsfs
    """

    def __init__(self, bucket: str, prefix: str = "") -> None:
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")

    def _blob_name(self, key: str) -> str:
        return f"{self.prefix}/{key}".lstrip("/") if self.prefix else key

    def read_text(self, key: str) -> str:
        from google.cloud import storage as gcs
        client = gcs.Client()
        blob = client.bucket(self.bucket).blob(self._blob_name(key))
        return blob.download_as_text()

    def write_text(self, key: str, content: str) -> None:
        from google.cloud import storage as gcs
        client = gcs.Client()
        blob = client.bucket(self.bucket).blob(self._blob_name(key))
        blob.upload_from_string(content, content_type="application/json")

    def exists(self, key: str) -> bool:
        from google.cloud import storage as gcs
        client = gcs.Client()
        return client.bucket(self.bucket).blob(self._blob_name(key)).exists()

    def find(self, filename: str) -> list[str]:
        from google.cloud import storage as gcs
        client = gcs.Client()
        blobs = client.list_blobs(self.bucket, prefix=self.prefix or None)
        prefix_strip = (self.prefix + "/") if self.prefix else ""
        return sorted(
            b.name[len(prefix_strip):]
            for b in blobs
            if b.name.endswith(f"/{filename}") or b.name == filename
        )

    def uri(self, key: str) -> str:
        """GCS URI — accepted by pandas/pyarrow via gcsfs."""
        return f"gs://{self.bucket}/{self._blob_name(key)}"


# Module-level default — avoids constructing a new instance on every call
_default_storage = LocalStorage()


def default_storage() -> LocalStorage:
    return _default_storage
