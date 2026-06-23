from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    """Immutable descriptor for an image asset within a platform project.

    ``path`` is relative to the project root.  ``width`` and ``height`` are
    L0 image dimensions.  Optional fields carry metadata that may be populated
    by a preflight scan (hash, channels, bit depth) or user grouping logic.
    """

    id: str
    path: str  # relative path within project
    width: int
    height: int
    channels: int | None = None
    bit_depth: int | None = None
    group_id: str | None = None
    sha256: str | None = None


__all__ = [
    "Asset",
]
