"""Platform infrastructure — I/O, storage and utilities with no UI or framework imports.

NOTE: ImageMetadata and LargeImageSource from the image_sources subpackage
are intentionally NOT re-exported here yet.  The image_sources subpackage
pulls in numpy, PIL, and optionally PyQt6 — importing infrastructure must
remain lightweight.  When image_sources is fully implemented, add:

    from anylabeling.platform.infrastructure.image_sources import (
        ImageMetadata,
        LargeImageSource,
    )
"""

from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter
from anylabeling.platform.infrastructure.checksum import compute_sha256
from anylabeling.platform.infrastructure.manifest_store import ManifestStore
from anylabeling.platform.infrastructure.process_job_runner import ProcessJobRunner
from anylabeling.platform.infrastructure.project_file_store import ProjectFileStore

__all__ = [
    "AtomicWriter",
    "ManifestStore",
    "ProcessJobRunner",
    "ProjectFileStore",
    "compute_sha256",
]
