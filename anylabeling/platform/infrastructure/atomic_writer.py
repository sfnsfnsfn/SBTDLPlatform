from __future__ import annotations

import json
import os
from pathlib import Path


class AtomicWriter:
    """Atomic file writer using tmp→validate→replace semantics.

    Writes to a temporary sidecar file first, flushes to disk, validates
    the written content, and only then atomically replaces the target with
    ``os.replace``.  This guarantees that readers never see a partial or
    corrupt file.
    """

    @staticmethod
    def write_json(path: str | Path, data: dict) -> None:
        """Atomically write *data* as JSON to *path*.

        1. Serialize to JSON and write to ``<path>.tmp`` (UTF-8, indent=2).
        2. Flush to OS and force to disk.
        3. Re-read and parse the temporary file to validate the JSON.
        4. ``os.replace(tmp_path, target_path)`` to swap atomically.

        Raises:
            ValueError: If the re-read JSON validation fails.
            OSError: If ``os.replace`` fails.
        """
        target = Path(path)
        tmp = target.with_suffix(target.suffix + ".tmp")

        content = json.dumps(data, ensure_ascii=False, indent=2)

        try:
            tmp.write_text(content, encoding="utf-8")

            # Validate by re-reading
            parsed = json.loads(tmp.read_text(encoding="utf-8"))
            if parsed != data:
                raise ValueError("Re-read JSON does not match input data")

            os.replace(tmp, target)
        except Exception:
            # Best-effort cleanup of leftover tmp file
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

    @staticmethod
    def write_text(path: str | Path, content: str) -> None:
        """Atomically write *content* as text to *path*.

        Same tmp→validate→replace pattern as :meth:`write_json`.
        """
        target = Path(path)
        tmp = target.with_suffix(target.suffix + ".tmp")

        try:
            tmp.write_text(content, encoding="utf-8")

            # Validate by re-reading
            read_back = tmp.read_text(encoding="utf-8")
            if read_back != content:
                raise ValueError("Re-read text does not match input content")

            os.replace(tmp, target)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise


__all__ = [
    "AtomicWriter",
]
