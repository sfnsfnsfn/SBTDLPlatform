"""BatchLabelingService — orchestrate AI-assisted batch labeling.

Iterates over project assets, runs inference via InferenceService,
and writes results to the annotations directory.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


class BatchLabelingService:
    """Service for batch AI-assisted labeling of project assets.

    Discovers assets, identifies unannotated ones, and can drive
    inference via an InferenceService to populate annotations.
    """

    def __init__(self, project_path: str) -> None:
        self._project_path = Path(project_path)

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def project_path(self) -> str:
        return str(self._project_path)

    # ------------------------------------------------------------------
    # asset discovery
    # ------------------------------------------------------------------

    def _list_image_files(self) -> list[Path]:
        """List all image files in the assets directory."""
        assets_dir = self._project_path / "assets"
        if not assets_dir.is_dir():
            return []
        return sorted(
            p for p in assets_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
        )

    def get_unannotated_assets(self) -> list[str]:
        """Return paths of assets that have no annotation file."""
        annotations_dir = self._project_path / "annotations"
        unannotated: list[str] = []
        for img_path in self._list_image_files():
            ann_path = annotations_dir / f"{img_path.stem}.json"
            if not ann_path.exists():
                unannotated.append(str(img_path))
        return unannotated

    def get_annotated_assets(self) -> list[str]:
        """Return paths of assets that have annotation files."""
        annotations_dir = self._project_path / "annotations"
        annotated: list[str] = []
        for img_path in self._list_image_files():
            ann_path = annotations_dir / f"{img_path.stem}.json"
            if ann_path.exists():
                annotated.append(str(img_path))
        return annotated

    def get_progress(self) -> tuple[int, int]:
        """Return (total_assets, annotated_count)."""
        total = len(self._list_image_files())
        annotated = len(self.get_annotated_assets())
        return total, annotated


__all__ = ["BatchLabelingService"]
