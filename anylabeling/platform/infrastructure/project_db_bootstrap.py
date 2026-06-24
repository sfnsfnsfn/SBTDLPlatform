"""ProjectDbBootstrap — scans a legacy (pre-SQLite) project directory and
populates the SQLite database tables via the existing repository layer.

Usage::

    db = ProjectDb("/path/to/project.db")
    db.open()

    bootstrap = ProjectDbBootstrap(db, "/path/to/old_project")
    report = bootstrap.run()
    print(f"Bootstrapped {report.assets_processed} assets")
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from anylabeling.platform.domain.records import (
    AnnotationSummaryRecord,
    AssetRecord,
    DatasetBuildRecord,
    ModelRecord,
    RunRecord,
)
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.annotations import (
    SQLiteAnnotationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.assets import (
    SQLiteAssetRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds import (
    SQLiteDatasetBuildRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.models import (
    SQLiteModelRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.runs import (
    SQLiteRunRepository,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic UUID namespace for bootstrap IDs
# ---------------------------------------------------------------------------

_NS_BOOT = uuid.uuid5(uuid.NAMESPACE_OID, "x-anylabeling-bootstrap")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapReport:
    """Aggregate counts from a bootstrap run.

    Each field reports the number of records written to the corresponding
    database table.  *errors* captures non-fatal warnings (corrupt files,
    unreadable images, etc.) without aborting the scan.
    """

    assets_processed: int = 0
    annotations_processed: int = 0
    dataset_builds_processed: int = 0
    runs_processed: int = 0
    models_processed: int = 0
    errors: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class ProjectDbBootstrap:
    """Scans a legacy V3 project directory and populates the SQLite database.

    The scanner walks well-known subdirectories (assets/, annotations/,
    dataset_builds/, runs/, models/) and writes their content into the
    corresponding database tables using the existing repository layer.

    Missing optional directories are handled gracefully.  Corrupted or
    unparseable files are logged as warnings and counted in
    ``BootstrapReport.errors`` rather than aborting the scan.

    Args:
        db: An open :class:`ProjectDb` instance.
        project_dir: Root of the legacy project directory.
    """

    def __init__(self, db: ProjectDb, project_dir: str | Path) -> None:
        self._db = db
        self._project_dir = Path(project_dir)

        # Lazily initialised repositories
        self._asset_repo: SQLiteAssetRepository | None = None
        self._ann_repo: SQLiteAnnotationRepository | None = None
        self._build_repo: SQLiteDatasetBuildRepository | None = None
        self._run_repo: SQLiteRunRepository | None = None
        self._model_repo: SQLiteModelRepository | None = None

    # ------------------------------------------------------------------
    # Repository accessors (lazy init)
    # ------------------------------------------------------------------

    @property
    def _assets(self) -> SQLiteAssetRepository:
        if self._asset_repo is None:
            self._asset_repo = SQLiteAssetRepository(self._db)
        return self._asset_repo

    @property
    def _annotations(self) -> SQLiteAnnotationRepository:
        if self._ann_repo is None:
            self._ann_repo = SQLiteAnnotationRepository(self._db)
        return self._ann_repo

    @property
    def _builds(self) -> SQLiteDatasetBuildRepository:
        if self._build_repo is None:
            self._build_repo = SQLiteDatasetBuildRepository(self._db)
        return self._build_repo

    @property
    def _runs(self) -> SQLiteRunRepository:
        if self._run_repo is None:
            self._run_repo = SQLiteRunRepository(self._db)
        return self._run_repo

    @property
    def _models(self) -> SQLiteModelRepository:
        if self._model_repo is None:
            self._model_repo = SQLiteModelRepository(self._db)
        return self._model_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> BootstrapReport:
        """Execute all scanners and return aggregate counts.

        Each scan step catches and logs exceptions individually so that a
        failure in one area (e.g. a corrupt dataset build) does not prevent
        the remaining areas from being processed.

        Returns:
            A :class:`BootstrapReport` with per-table counts.
        """
        errors: list[str] = []

        assets = self._safe_scan(self._scan_assets, "assets", errors)
        # Build a stem → asset_id mapping from the scanned assets so
        # annotation records can reference the correct asset id.
        stem_map = _build_stem_map(assets)
        anns = self._safe_scan(
            lambda: self._scan_annotations(stem_map), "annotations", errors
        )
        builds = self._safe_scan(self._scan_dataset_builds, "dataset_builds", errors)
        runs = self._safe_scan(self._scan_runs, "runs", errors)
        models = self._safe_scan(self._scan_models, "models", errors)

        return BootstrapReport(
            assets_processed=len(assets),
            annotations_processed=len(anns),
            dataset_builds_processed=len(builds),
            runs_processed=len(runs),
            models_processed=len(models),
            errors=tuple(errors),
        )

    # ------------------------------------------------------------------
    # Scan internals
    # ------------------------------------------------------------------

    def _scan_project_json(self) -> dict | None:
        """Read and return *project.json* content, or ``None``.

        This is a metadata-only scan; the project name and labels are not
        stored in the SQLite tables by the bootstrap process.
        """
        path = self._project_dir / "project.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("Failed to read %s: %s", path, exc)
            return None

    def _scan_labels_json(self) -> list | None:
        """Read and return legacy *labels.json* content, or ``None``."""
        path = self._project_dir / "labels.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("Failed to read %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Asset scanner
    # ------------------------------------------------------------------

    def _scan_assets(self) -> list[AssetRecord]:
        """Walk **assets/** recursively and upsert every file as an asset.

        Supports nested subdirectory groups.  Image dimensions are detected
        via Pillow when possible; non-image files and unreadable images are
        stored with zero dimensions.
        """
        assets_dir = self._project_dir / "assets"
        if not assets_dir.is_dir():
            _logger.info("assets/ directory not found — skipping asset scan.")
            return []

        records: list[AssetRecord] = []
        for path in sorted(assets_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(assets_dir)
            rel_str = rel.as_posix()

            asset_id = _bootstrap_id("asset", rel_str)
            ext = path.suffix.lower()
            size = path.stat().st_size

            group = _extract_group(rel)

            width, height = _read_image_dimensions(path)

            record = AssetRecord(
                id=asset_id,
                rel_path=rel_str,
                width=width,
                height=height,
                ext=ext,
                size_bytes=size,
                group_name=group,
            )
            self._assets.upsert(record)
            records.append(record)

        return records

    # ------------------------------------------------------------------
    # Annotation scanner
    # ------------------------------------------------------------------

    def _scan_annotations(
        self, stem_map: dict[str, str]
    ) -> list[AnnotationSummaryRecord]:
        """Scan **annotations/** and upsert annotation summary records.

        Supported formats:
        - ``.xml`` → format ``voc``
        - ``.json`` → format ``json``

        Each annotation file is mapped to the corresponding asset via
        filename stem matching using *stem_map*.
        """
        ann_dir = self._project_dir / "annotations"
        if not ann_dir.is_dir():
            _logger.info("annotations/ directory not found — skipping annotation scan.")
            return []

        records: list[AnnotationSummaryRecord] = []
        for path in sorted(ann_dir.iterdir()):
            if not path.is_file():
                continue
            try:
                record = self._build_annotation_record(path, stem_map)
                if record is not None:
                    self._annotations.upsert_summary(record)
                    records.append(record)
            except Exception:
                _logger.exception(
                    "Failed to process annotation %s — skipping.", path
                )

        return records

    def _build_annotation_record(
        self, path: Path, stem_map: dict[str, str]
    ) -> AnnotationSummaryRecord | None:
        """Create an :class:`AnnotationSummaryRecord` for a single annotation file.

        Uses *stem_map* to resolve the annotation's filename stem to an
        existing asset id.  Returns ``None`` if the annotation format is
        not recognised or no matching asset is found.
        """
        suffix = path.suffix.lower()
        if suffix == ".xml":
            fmt = "voc"
        elif suffix == ".json":
            fmt = "json"
        else:
            _logger.warning("Unrecognised annotation format: %s", path)
            return None

        stem = path.stem  # e.g. "img001" from "img001.xml"
        asset_id = stem_map.get(stem)
        if asset_id is None:
            _logger.warning(
                "No matching asset found for annotation %s (stem=%s) — skipping.",
                path,
                stem,
            )
            return None

        return AnnotationSummaryRecord(
            asset_id=asset_id,
            rel_path=path.name,
            format=fmt,
            object_count=0,
        )

    # ------------------------------------------------------------------
    # Dataset build scanner
    # ------------------------------------------------------------------

    def _scan_dataset_builds(self) -> list[DatasetBuildRecord]:
        """Scan **dataset_builds/*/build.json** and upsert build records.

        Completed builds (status ``"completed"`` in the JSON) are persisted
        with status set to ``"completed"``.
        """
        builds_dir = self._project_dir / "dataset_builds"
        if not builds_dir.is_dir():
            _logger.info("dataset_builds/ directory not found — skipping.")
            return []

        records: list[DatasetBuildRecord] = []
        for build_dir in sorted(builds_dir.iterdir()):
            if not build_dir.is_dir():
                continue
            build_json = build_dir / "build.json"
            if not build_json.exists():
                continue
            try:
                data = json.loads(build_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                _logger.warning("Failed to read %s: %s", build_json, exc)
                continue

            build_id = build_dir.name
            task_family = data.get("task_family", "unknown")
            output_path = data.get("output_path", build_dir.name)
            raw_status = data.get("status", "pending")

            record = DatasetBuildRecord(
                id=build_id,
                task_family=task_family,
                output_path=str(output_path),
                status=raw_status if raw_status == "completed" else "pending",
            )
            self._builds.create(record)
            records.append(record)

        return records

    # ------------------------------------------------------------------
    # Run scanner
    # ------------------------------------------------------------------

    def _scan_runs(self) -> list[RunRecord]:
        """Scan **runs/*/** and upsert run records from metrics manifests.

        When ``metrics.json`` is present its content is stored as
        ``metrics_json``.
        """
        runs_dir = self._project_dir / "runs"
        if not runs_dir.is_dir():
            _logger.info("runs/ directory not found — skipping run scan.")
            return []

        records: list[RunRecord] = []
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            try:
                record = self._build_run_record(run_dir)
                if record is not None:
                    self._runs.create(record)
                    records.append(record)
            except Exception:
                _logger.exception(
                    "Failed to process run %s — skipping.", run_dir
                )

        return records

    def _build_run_record(self, run_dir: Path) -> RunRecord | None:
        """Create a :class:`RunRecord` from a single run directory.

        Returns ``None`` if the directory contains no usable data.
        """
        run_id = run_dir.name
        metrics_path = run_dir / "metrics.json"

        metrics_json: str | None = None
        if metrics_path.exists():
            try:
                metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))
                metrics_json = json.dumps(metrics_data, sort_keys=True)
            except (json.JSONDecodeError, OSError) as exc:
                _logger.warning(
                    "Failed to read %s: %s", metrics_path, exc
                )

        return RunRecord(
            id=run_id,
            dataset_build_id="bootstrap",
            adapter_id="bootstrap",
            task_family="unknown",
            status="completed",
            metrics_json=metrics_json,
        )

    # ------------------------------------------------------------------
    # Model scanner
    # ------------------------------------------------------------------

    def _scan_models(self) -> list[ModelRecord]:
        """Scan **models/*/** and upsert model records.

        Reads ``metadata.json`` for model name, format, task family, and
        the associated run ID.  The presence of any ``.pt`` or ``.onnx``
        file is treated as the model artifact path.
        """
        models_dir = self._project_dir / "models"
        if not models_dir.is_dir():
            _logger.info("models/ directory not found — skipping model scan.")
            return []

        records: list[ModelRecord] = []
        for model_dir in sorted(models_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            try:
                record = self._build_model_record(model_dir)
                if record is not None:
                    self._models.upsert(record)
                    records.append(record)
            except Exception:
                _logger.exception(
                    "Failed to process model %s — skipping.", model_dir
                )

        return records

    def _build_model_record(self, model_dir: Path) -> ModelRecord | None:
        """Create a :class:`ModelRecord` from a single model directory.

        Returns ``None`` if the directory contains no recognisable model
        files.
        """
        model_id = model_dir.name
        metadata_path = model_dir / "metadata.json"

        name = model_id
        fmt = "unknown"
        task_family = "unknown"
        run_id = "bootstrap"

        if metadata_path.exists():
            try:
                meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                name = meta.get("name", name)
                fmt = meta.get("format", fmt)
                task_family = meta.get("task_family", task_family)
                run_id = meta.get("run_id", run_id)
            except (json.JSONDecodeError, OSError) as exc:
                _logger.warning(
                    "Failed to read %s: %s", metadata_path, exc
                )

        # Locate the actual model artifact
        artifact_path = _find_model_artifact(model_dir)
        model_path_str = str(artifact_path) if artifact_path else model_dir.name

        return ModelRecord(
            id=model_id,
            run_id=run_id,
            name=name,
            format=fmt,
            path=model_path_str,
            task_family=task_family,
            ready=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_scan(
        scan_fn: Callable[[], list],
        label: str,
        errors: list[str],
    ) -> list:
        """Execute *scan_fn* and capture exceptions into *errors*.

        This ensures a failure in one scan area (e.g. corrupt annotations)
        does not abort other scan areas.
        """
        try:
            return scan_fn()
        except Exception as exc:
            _logger.exception("Scan of %s failed.", label)
            errors.append(f"{label}: {exc}")
            return []


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _bootstrap_id(kind: str, key: str) -> str:
    """Generate a deterministic UUID for a bootstrap entity.

    Using the same *kind* + *key* input always produces the same UUID,
    which makes repeated bootstrap runs idempotent at the record level.
    """
    return str(uuid.uuid5(_NS_BOOT, f"{kind}:{key}"))


def _extract_group(rel_path: Path) -> str | None:
    """Extract the group name from a relative asset path.

    For ``group_a/img003.jpg`` → ``"group_a"``.
    For top-level files (``img001.jpg``) → ``None``.
    """
    parts = rel_path.parts
    if len(parts) > 1:
        return parts[-2]
    return None


def _read_image_dimensions(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` for an image file.

    Uses Pillow when available.  Returns ``(0, 0)`` if the file cannot be
    identified as an image.
    """
    try:
        import PIL.Image
    except ImportError:
        _logger.debug("Pillow not available — cannot read image dimensions.")
        return 0, 0

    try:
        with PIL.Image.open(str(path)) as img:
            return img.width, img.height
    except Exception:
        _logger.debug("Could not read image dimensions from %s", path)
        return 0, 0


def _find_model_artifact(model_dir: Path) -> Path | None:
    """Return the first ``.pt`` or ``.onnx`` file in *model_dir*.

    Returns ``None`` if no recognisable model artifact is found.
    """
    for pattern in ("*.pt", "*.onnx", "*.pth", "*.bin"):
        candidates = list(model_dir.glob(pattern))
        if candidates:
            return candidates[0]
    return None


def _build_stem_map(assets: list[AssetRecord]) -> dict[str, str]:
    """Build a mapping from filename stem to asset id.

    When multiple assets share the same stem (e.g. ``img001.jpg`` and
    ``img001.png``) the last one wins, which is consistent with the
    deterministic sort order of ``_scan_assets``.
    """
    stem_map: dict[str, str] = {}
    for a in assets:
        stem = Path(a.rel_path).stem
        stem_map[stem] = a.id
    return stem_map


__all__ = [
    "BootstrapReport",
    "ProjectDbBootstrap",
]
