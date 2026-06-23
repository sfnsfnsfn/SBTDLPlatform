from __future__ import annotations

import hashlib
from pathlib import Path


def compute_sha256(file_path: str | Path, chunk_size: int = 8192) -> str:
    """Compute the SHA-256 hex digest of *file_path*.

    Reads the file in *chunk_size* bytes at a time so that memory usage
    stays bounded regardless of file size.

    Returns:
        Lowercase hexadecimal SHA-256 digest string (64 characters).
    """
    path = Path(file_path)
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


__all__ = [
    "compute_sha256",
]
