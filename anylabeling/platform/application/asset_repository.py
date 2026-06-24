"""AssetRepository — unified asset scanning service.

Provides read-only access to project assets without coupling to
WorkbenchWindow or any UI layer.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path

from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.import_config import get_supported_extensions
from anylabeling.platform.infrastructure.image_reader import ImageReader

logger = logging.getLogger(__name__)

_IMAGE_EXTS: set[str] = set(get_supported_extensions())

STATUS_UNANNOTATED = "unannotated"
STATUS_PARTIAL = "partial"
STATUS_COMPLETE = "complete"


class AssetRepository:
    """Read-only scanner for the ``assets/`` directory of a V4 MVP project.

    All methods handle a missing ``assets/`` directory gracefully by
    returning empty collections.

    Caches scan results internally. Call ``invalidate_cache()`` after
    import or other operations that modify the assets directory.
    """

    def __init__(
        self,
        project_root: str | Path,
        annotations_dir: str | Path | None = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._assets_dir = self._project_root / "assets"
        self._annotations_dir = (
            Path(annotations_dir)
            if annotations_dir
            else self._project_root / "annotations"
        )
        self._asset_paths_cache: tuple[str, ...] | None = None
        self._asset_cache: dict[str, Asset] = {}
        self._annotation_status_cache: dict[str, str] | None = None

    @property
    def project_root(self) -> Path:
        """The project root directory."""
        return self._project_root

    # ------------------------------------------------------------------
    # public query API
    # ------------------------------------------------------------------

    def scan_assets(
        self,
        offset: int = 0,
        limit: int | None = None,
        group_filter: str | None = None,
        status_filter: str | None = None,
    ) -> list[str]:
        """Return sorted absolute paths of supported image files.

        Scans ``assets/`` recursively — images inside sub-directories
        are included. Their immediate parent directory is used as the
        group identifier.

        Args:
            offset: Number of paths to skip (for pagination).
            limit: Maximum number of paths to return.
            group_filter: Only return assets in this group.
            status_filter: Only return assets with this status.
        """
        paths = self._get_all_paths()

        if group_filter is not None:
            paths = [
                p
                for p in paths
                if self._get_asset_group(Path(p)) == group_filter
            ]
        if status_filter is not None and status_filter != "all":
            statuses = self.get_annotation_statuses()
            paths = [
                p
                for p in paths
                if statuses.get(Path(p).stem, STATUS_UNANNOTATED)
                == status_filter
            ]

        if offset > 0:
            paths = paths[offset:]
        if limit is not None:
            paths = paths[:limit]

        return paths

    def count_assets(self) -> int:
        """Return the number of supported image files in ``assets/``."""
        return len(self._get_all_paths())

    def count_by_extension(self) -> dict[str, int]:
        """Return a dict mapping lower-case extension → file count."""
        counter: Counter[str] = Counter()
        for p in self._get_all_paths():
            counter[Path(p).suffix.lower()] += 1
        return dict(counter)

    def find_large_images(self, min_dim: int = 2000) -> list[str]:
        """Return paths of images whose larger dimension exceeds *min_dim*.

        Uses QImageReader for metadata-only reads — handles all formats
        including large TIFFs that OpenCV cannot decode.
        """
        if not self._assets_dir.exists():
            return []

        large: list[str] = []
        for p in self._get_all_paths():
            meta = ImageReader.metadata(p)
            if meta.width > 0 and max(meta.width, meta.height) > min_dim:
                large.append(p)
        return sorted(large)

    def list_subdirs(self) -> list[str]:
        """Return names of immediate sub-directories inside ``assets/``."""
        if not self._assets_dir.exists():
            return []
        return sorted(
            d.name for d in self._assets_dir.iterdir() if d.is_dir()
        )

    # ------------------------------------------------------------------
    # Extended query API (Phase 3a)
    # ------------------------------------------------------------------

    def get_asset(self, asset_path: str) -> Asset | None:
        """Return full Asset metadata. Results are cached.

        Returns None if the asset does not exist or cannot be read.
        """
        abs_path = str(
            Path(asset_path)
            if Path(asset_path).is_absolute()
            else self._assets_dir / asset_path
        )
        if abs_path in self._asset_cache:
            return self._asset_cache[abs_path]

        path = Path(abs_path)
        if not path.is_file():
            return None

        try:
            meta = ImageReader.metadata(abs_path)
            if meta.width == 0:
                return None
            w, h, ch = meta.width, meta.height, meta.channels
        except (ImportError, OSError):
            logger.warning("Failed to read image: %s", abs_path)
            return None

        rel = str(path.relative_to(self._project_root)).replace("\\", "/")
        asset_id = f"asset_{hashlib.sha256(rel.encode()).hexdigest()[:12]}"
        asset = Asset(
            id=asset_id,
            path=rel,
            width=w,
            height=h,
            channels=ch,
        )
        self._asset_cache[abs_path] = asset
        return asset

    def get_asset_ids_by_status(self, status: str) -> set[str]:
        """Return asset stems matching the given annotation status."""
        statuses = self.get_annotation_statuses()
        return {stem for stem, s in statuses.items() if s == status}

    def get_asset_ids_by_group(self, group_id: str) -> set[str]:
        """Return asset stems in a specific group."""
        return {
            Path(p).stem
            for p in self._get_all_paths()
            if self._get_asset_group(Path(p)) == group_id
        }

    def get_groups(self) -> list[str]:
        """Return sorted list of unique group IDs across all assets."""
        groups: set[str] = set()
        for p in self._get_all_paths():
            gid = self._get_asset_group(Path(p))
            if gid:
                groups.add(gid)
        return sorted(groups)

    def get_stats(self) -> dict:
        """Return comprehensive asset statistics."""
        paths = self._get_all_paths()
        statuses = self.get_annotation_statuses()
        by_ext = self.count_by_extension()
        groups = self.get_groups()

        return {
            "total": len(paths),
            "annotated": sum(
                1 for s in statuses.values() if s == STATUS_COMPLETE
            ),
            "unannotated": sum(
                1 for s in statuses.values() if s == STATUS_UNANNOTATED
            ),
            "partial": sum(
                1 for s in statuses.values() if s == STATUS_PARTIAL
            ),
            "by_extension": by_ext,
            "groups": groups,
            "group_count": len(groups),
            "large_count": len(self.find_large_images()),
        }

    def invalidate_cache(self) -> None:
        """Clear all internal caches. Call after import or asset changes."""
        self._asset_paths_cache = None
        self._asset_cache.clear()
        self._annotation_status_cache = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all_paths(self) -> list[str]:
        """Return sorted absolute paths, using cache if available."""
        if self._asset_paths_cache is not None:
            return list(self._asset_paths_cache)

        if not self._assets_dir.exists():
            self._asset_paths_cache = ()
            return []

        self._asset_paths_cache = tuple(
            sorted(
                str(p)
                for p in self._assets_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
            )
        )
        return list(self._asset_paths_cache)

    @staticmethod
    def _get_asset_group(path: Path) -> str | None:
        """Extract group_id from asset path: parent dir of the file."""
        parent = path.parent
        if parent.name == "assets":
            return None
        return parent.name

    def get_annotation_statuses(self) -> dict[str, str]:
        """Return {asset_stem: status} for all assets."""
        if self._annotation_status_cache is not None:
            return self._annotation_status_cache

        statuses: dict[str, str] = {}
        annotated_stems: set[str] = set()

        if self._annotations_dir.exists():
            for ann_file in self._annotations_dir.iterdir():
                if ann_file.suffix == ".json" and not ann_file.name.endswith(
                    ".tmp"
                ):
                    annotated_stems.add(ann_file.stem)

        for p in self._get_all_paths():
            stem = Path(p).stem
            if stem in annotated_stems:
                try:
                    ann_path = self._annotations_dir / f"{stem}.json"
                    data = json.loads(
                        ann_path.read_text(encoding="utf-8")
                    )
                    objects = data.get("shapes", [])
                    statuses[stem] = (
                        STATUS_COMPLETE
                        if objects
                        else STATUS_UNANNOTATED
                    )
                except (json.JSONDecodeError, OSError):
                    statuses[stem] = STATUS_PARTIAL
            else:
                statuses[stem] = STATUS_UNANNOTATED

        self._annotation_status_cache = statuses
        return statuses


__all__ = [
    "AssetRepository",
    "STATUS_UNANNOTATED",
    "STATUS_PARTIAL",
    "STATUS_COMPLETE",
]
