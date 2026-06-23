from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ManifestStore:
    """JSONL-based manifest storage for append-only record keeping.

    Each line in a JSONL file is an independent, parseable JSON object.
    This is used for asset manifests, annotation manifests, and similar
    append-only logs within the platform.
    """

    @staticmethod
    def append_jsonl(path: str | Path, row: dict) -> None:
        """Append a single JSON line to *path*.

        Opens in append mode so the file is created if it does not exist.
        Each row is written as one line (no pretty-printing) followed by a
        newline.  Encoding is always UTF-8.
        """
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    @staticmethod
    def read_jsonl(path: str | Path) -> list[dict]:
        """Read all rows from a JSONL file.

        Skips empty lines gracefully so that trailing newlines or blank
        lines do not cause parse errors.

        Returns:
            List of dicts, one per non-empty line.
        """
        p = Path(path)
        if not p.exists():
            return []

        rows: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
        return rows

    @staticmethod
    def validate_jsonl(path: str | Path) -> bool:
        """Verify that every line in the JSONL file is valid JSON.

        Empty lines are ignored.  Returns ``True`` only if every
        non-empty line is independently parseable.
        """
        p = Path(path)
        if not p.exists():
            # Non-existent file is trivially valid (no lines to fail).
            return True

        for line in p.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError:
                return False
        return True


    # ------------------------------------------------------------------
    # Manifest integrity hashing
    # ------------------------------------------------------------------

    @staticmethod
    def compute_manifest_hash(path: Path) -> str:
        """Compute SHA-256 hash of a JSONL manifest file (raw bytes).

        The hash is deterministic — reading the exact same bytes on
        disk will always produce the same hex digest.  This covers
        newline conventions and line ordering in addition to JSON
        content.
        """
        p = Path(path)
        if not p.exists():
            return ""
        raw = p.read_bytes()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def verify_manifest_hash(path: Path, expected: str) -> bool:
        """Verify that *path* hashes to *expected*.

        Returns ``True`` if the file exists and its SHA-256 matches
        *expected*.  Returns ``False`` for a missing file or a
        hash mismatch.
        """
        p = Path(path)
        if not p.exists():
            return False
        return ManifestStore.compute_manifest_hash(p) == expected


__all__ = [
    "ManifestStore",
]
