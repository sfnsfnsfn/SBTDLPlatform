"""ImportService — copies images into project assets/ with analysis and dedup.

Architecture constraints:
    - No PyQt6 imports.
    - All file I/O uses pathlib.Path.
    - SHA-256 via infrastructure/checksum.py.
    - Image analysis via cv2 (opencv-python-headless assumed available).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Callable

from anylabeling.platform.domain.annotation import (
    AnnotationDocument,
    AnnotationObject,
)
from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.import_config import (
    AnnotationImportStats,
    ImportCancelledError,
    ImportResult,
    PrecheckResult,
    get_supported_extensions,
)
from anylabeling.platform.infrastructure.checksum import compute_sha256
from anylabeling.platform.infrastructure.image_reader import ImageReader

logger = logging.getLogger(__name__)

# Supported image extensions (matches ImportConfig defaults)
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(get_supported_extensions())


class ImportService:
    """Application service for importing images into a platform project.

    Copies images to ``<project_root>/assets/``, performs SHA-256 deduplication,
    extracts image properties (width, height, channels), detects large images,
    and optionally groups assets by source folder name.

    Usage::

        svc = ImportService(project_root="/data/project")
        result = svc.import_images(["/tmp/img1.jpg", "/tmp/img2.png"])
        print(f"Imported {result.total}, {result.large_count} large, "
              f"{result.duplicate_count} duplicates")
    """

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def import_images(
        self,
        paths: list[str],
        deduplicate: bool = True,
        group_by_folder: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_token: threading.Event | None = None,
    ) -> ImportResult:
        """Import images from *paths* into the project's assets directory.

        Args:
            paths: List of absolute file paths to import.
            deduplicate: If True, skip files whose SHA-256 matches an already
                imported asset (within the same group when group_by_folder).
            group_by_folder: If True, assign ``group_id`` based on the
                immediate parent directory name of each source file.
            progress_callback: Optional callback(current, total, filename)
                called after each file is processed.
            cancel_token: Optional threading.Event; if set, raises
                ImportCancelledError before processing the next file.

        Returns:
            ImportResult with imported assets and statistics.

        Raises:
            ImportCancelledError: If *cancel_token* is set during processing.
        """
        assets: list[Asset] = []
        errors: list[str] = []
        seen_hashes: dict[str, set[str]] = {}  # group_id -> {sha256, ...}

        duplicate_count = 0
        large_count = 0
        processed_count = 0
        skipped_count = 0

        # Ensure assets/ directory exists
        assets_dir = self._project_root / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Starting import of %d files to %s", len(paths), assets_dir)

        for i, src_path_str in enumerate(paths):
            # Check cancellation before each file
            if cancel_token and cancel_token.is_set():
                raise ImportCancelledError(
                    f"Import cancelled after {i} of {len(paths)} files"
                )

            src = Path(src_path_str)

            # Validate existence
            if not src.is_file():
                errors.append(f"File not found: {src_path_str}")
                skipped_count += 1
                continue

            # Validate extension
            suffix = src.suffix.lower()
            if suffix not in _SUPPORTED_EXTENSIONS:
                errors.append(f"Unsupported format: {src_path_str}")
                skipped_count += 1
                continue

            # Determine group_id upfront (before copy, support group-aware dedup)
            gid: str | None = None
            if group_by_folder:
                gid = src.parent.name

            # Compute SHA-256 from source (avoid wasted copy on duplicate)
            sha = compute_sha256(src)

            # Group-aware deduplication
            if deduplicate:
                group_key = gid or "__nogroup__"
                group_hashes = seen_hashes.setdefault(group_key, set())
                if sha in group_hashes:
                    duplicate_count += 1
                    continue
                group_hashes.add(sha)

            # Determine destination filename (handle collisions)
            dest_name = src.name
            dest = assets_dir / dest_name
            suffix_part = src.suffix
            stem = src.stem
            counter = 1
            while dest.exists():
                dest_name = f"{stem}_{counter}{suffix_part}"
                dest = assets_dir / dest_name
                counter += 1

            # Copy file preserving metadata (handle disk-full/permission errors)
            try:
                shutil.copy2(src, dest)
            except (OSError, PermissionError) as exc:
                errors.append(f"Copy failed: {src_path_str} — {exc}")
                skipped_count += 1
                continue

            # Image property analysis (reject unreadable/corrupt images)
            try:
                meta = ImageReader.metadata(str(dest))
                width, height, channels = meta.width, meta.height, meta.channels
            except (ImportError, OSError):
                width, height = 0, 0
            if width <= 0 or height <= 0:
                dest.unlink()
                errors.append(f"Failed to read image: {src_path_str}")
                skipped_count += 1
                continue

            # Large image detection
            is_large = self._is_large(width, height)
            if is_large:
                large_count += 1

            # Build Asset
            rel = str(dest.relative_to(self._project_root)).replace("\\", "/")
            asset = Asset(
                id=f"asset_{hashlib.sha256(rel.encode()).hexdigest()[:12]}",
                path=rel,
                width=width,
                height=height,
                channels=channels,
                group_id=gid,
                sha256=sha,
            )
            assets.append(asset)
            processed_count += 1

            # Report progress after each successfully processed file
            if progress_callback:
                progress_callback(i + 1, len(paths), src.name)

        logger.info(
            "Import complete: %d processed, %d duplicates, %d errors",
            processed_count, duplicate_count, len(errors),
        )
        return ImportResult(
            assets=assets,
            total=processed_count,
            large_count=large_count,
            duplicate_count=duplicate_count,
            errors=errors,
        )

    def precheck(
        self,
        sources: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_token: threading.Event | None = None,
    ) -> PrecheckResult:
        """Scan sources without copying any files.

        For each source: if a file → validate individually; if a directory →
        walk recursively. Validation checks extension, image readability
        (cv2.imread), and size (large image detection).

        Args:
            sources: List of file or directory paths to scan.
            progress_callback: Optional callback(current, total) during scan.
            cancel_token: Optional threading.Event; if set, raises
                ImportCancelledError before processing the next file.

        Returns:
            PrecheckResult with categorized files and size estimates.

        Raises:
            ImportCancelledError: If *cancel_token* is set during processing.
        """
        valid: list[str] = []
        damaged: list[str] = []
        unsupported: list[str] = []
        oversized: list[tuple[str, int, int]] = []
        errors: list[str] = []
        estimated_size: int = 0

        # Flatten sources into file list
        all_files: list[str] = []
        for source in sources:
            src_path = Path(source)
            if not src_path.exists():
                errors.append(f"Source not found: {source}")
                continue
            if src_path.is_file():
                all_files.append(str(src_path))
            elif src_path.is_dir():
                for root, _dirs, files in os.walk(src_path):
                    for f in files:
                        all_files.append(os.path.join(root, f))
            else:
                errors.append(f"Unsupported source type: {source}")

        total = len(all_files)

        for i, file_path in enumerate(all_files):
            # Check cancellation before each file
            if cancel_token and cancel_token.is_set():
                raise ImportCancelledError(
                    f"Precheck cancelled after {i} of {total} files"
                )

            if progress_callback:
                progress_callback(i + 1, total)

            path = Path(file_path)
            suffix = path.suffix.lower()

            # Extension check
            if suffix not in _SUPPORTED_EXTENSIONS:
                unsupported.append(file_path)
                continue

            # File size for estimate
            try:
                estimated_size += path.stat().st_size
            except OSError:
                pass

            # Image readability check
            try:
                meta = ImageReader.metadata(str(path))
                w, h = meta.width, meta.height
            except OSError:
                w, h = 0, 0

            if w <= 0 or h <= 0:
                damaged.append(file_path)
                continue

            # Large image check
            if self._is_large(w, h):
                oversized.append((file_path, w, h))

            valid.append(file_path)

        return PrecheckResult(
            total_files=total,
            valid_files=valid,
            damaged_files=damaged,
            unsupported_files=unsupported,
            oversized_files=oversized,
            estimated_size_bytes=estimated_size,
            errors=errors,
        )

    def import_with_annotations(
        self,
        image_paths: list[str],
        annotation_format: str,
        annotation_source: str,
        label_mapping: dict[int, int] | None = None,
        deduplicate: bool = True,
        progress_callback: (
            Callable[[int, int, str], None] | None
        ) = None,
        cancel_token: threading.Event | None = None,
    ) -> tuple[ImportResult, AnnotationImportStats]:
        """Import images with companion annotation files.

        Workflow:
            1. Import images via :meth:`import_images`.
            2. Detect companion annotation files per image.
            3. Parse via the appropriate codec (yolo/coco/voc).
            4. Apply *label_mapping* to convert external cls_id → project label_id.
            5. Write ``AnnotationDocument`` to ``annotations/<stem>.json``.

        Args:
            image_paths: List of absolute image file paths.
            annotation_format: One of ``"yolo"``, ``"coco"``, ``"voc"``.
            annotation_source: For yolo/voc: directory containing annotation
                files. For coco: path to the COCO JSON file.
            label_mapping: Optional mapping of external label_id →
                project label_id. Labels not in the mapping are skipped
                with a warning.
            deduplicate: Passed through to :meth:`import_images`.
            progress_callback: Optional callback(current, total, filename).
            cancel_token: Optional threading.Event for cancellation.

        Returns:
            Tuple of (ImportResult, AnnotationImportStats).
        """
        # 1. Import images first
        import_result = self.import_images(
            image_paths,
            deduplicate=deduplicate,
            group_by_folder=True,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )

        annotation_source_path = Path(annotation_source)

        # 2. Parse annotations
        if annotation_format == "coco":
            ann_stats = self._import_coco_annotations(
                annotation_source_path,
                import_result,
                label_mapping,
            )
        elif annotation_format in ("yolo", "voc"):
            ann_stats = self._import_per_image_annotations(
                annotation_source_path,
                import_result,
                annotation_format,
                label_mapping,
                progress_callback,
                cancel_token,
            )
        elif annotation_format == "xanylabel":
            ann_stats = self._import_xanylabel_annotations(
                annotation_source_path,
                import_result,
                label_mapping,
                progress_callback,
                cancel_token,
            )
        else:
            logger.warning(
                "Unknown annotation format: %s", annotation_format
            )
            ann_stats = AnnotationImportStats(
                errors=[f"Unknown annotation format: {annotation_format}"],
            )

        return import_result, ann_stats

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path:
        """The project root directory."""
        return self._project_root

    # ------------------------------------------------------------------
    # Annotation import helpers
    # ------------------------------------------------------------------

    def _import_coco_annotations(
        self,
        source_path: Path,
        import_result: ImportResult,
        label_mapping: dict[int, int] | None,
    ) -> AnnotationImportStats:
        """Import annotations from a COCO JSON file.

        Returns:
            AnnotationImportStats with import statistics.
        """
        from anylabeling.platform.application.codecs.coco_codec import (
            COCOCodec,
        )

        codec = COCOCodec()
        docs = codec.load_annotations(str(source_path))

        errors: list[str] = []

        # Build asset stem → (asset_id, width, height) lookup
        asset_lookup: dict[str, tuple[str, int, int]] = {}
        for asset in import_result.assets:
            stem = Path(asset.path).stem
            asset_lookup[stem] = (asset.id, asset.width, asset.height)

        imported = 0
        matched = 0
        empty_count = 0
        label_counts: dict[str, int] = {}
        unmapped: set[str] = set()

        annot_dir = self._project_root / "annotations"
        annot_dir.mkdir(parents=True, exist_ok=True)

        for filename, doc in docs.items():
            stem = Path(filename).stem
            stem_key: str | None = None
            if stem in asset_lookup:
                stem_key = stem
            else:
                # Try fuzzy matching
                for lk_stem in asset_lookup:
                    if lk_stem in filename or filename in lk_stem:
                        stem_key = lk_stem
                        break

            if stem_key is None:
                errors.append(
                    f"No matching asset for annotation: {filename}"
                )
                continue

            matched += 1
            _, img_w, img_h = asset_lookup[stem_key]

            # Apply label mapping
            mapped_objects: list[AnnotationObject] = []
            for obj in doc.objects:
                ext_label_id = obj.label_id
                cat_name = obj.attributes.get("category_name")

                if label_mapping and ext_label_id in label_mapping:
                    new_label_id = label_mapping[ext_label_id]
                else:
                    new_label_id = ext_label_id
                    if label_mapping and cat_name:
                        unmapped.add(cat_name)

                label_name = cat_name or str(ext_label_id)
                label_counts[label_name] = (
                    label_counts.get(label_name, 0) + 1
                )

                mapped_objects.append(
                    AnnotationObject(
                        id=obj.id,
                        label_id=new_label_id,
                        geometry_type=obj.geometry_type,
                        geometry=obj.geometry,
                        attributes=dict(obj.attributes),
                        source_object_id=obj.id,
                    )
                )

            if not mapped_objects:
                empty_count += 1

            new_doc = AnnotationDocument(
                asset_id=stem_key,
                image_width=img_w,
                image_height=img_h,
                objects=mapped_objects,
            )

            self._write_annotation_document(annot_dir, stem_key, new_doc)
            imported += 1

        return AnnotationImportStats(
            total_annotation_files=len(docs),
            matched_count=matched,
            unmatched_count=len(docs) - matched,
            empty_count=empty_count,
            imported_count=imported,
            error_count=len(errors),
            label_counts=label_counts,
            unmapped_labels=frozenset(unmapped),
            errors=errors,
        )

    def _import_per_image_annotations(
        self,
        source_dir: Path,
        import_result: ImportResult,
        annotation_format: str,
        label_mapping: dict[int, int] | None,
        progress_callback: (
            Callable[[int, int, str], None] | None
        ) = None,
        cancel_token: threading.Event | None = None,
    ) -> AnnotationImportStats:
        """Import per-image annotation files (YOLO .txt or VOC .xml).

        For each imported asset, look for a matching annotation file
        in *source_dir* with the same stem and the format-specific extension.

        Returns:
            AnnotationImportStats with import statistics.
        """
        if annotation_format == "yolo":
            from anylabeling.platform.application.codecs.yolo_codec import (
                YOLOCodec,
            )

            codec = YOLOCodec()
            ann_ext = ".txt"
        elif annotation_format == "voc":
            from anylabeling.platform.application.codecs.voc_codec import (
                VOCCodec,
            )

            codec = VOCCodec()
            ann_ext = ".xml"
        else:
            return AnnotationImportStats(
                errors=[
                    f"Unsupported per-image annotation format: {annotation_format}"
                ],
            )

        # Build annotation file lookup: stem → path
        ann_lookup: dict[str, Path] = {}
        if source_dir.is_dir():
            for p in source_dir.iterdir():
                if p.is_file() and p.suffix.lower() == ann_ext:
                    ann_lookup[p.stem] = p

        total = len(import_result.assets)
        matched = 0
        imported = 0
        empty = 0
        label_counts: dict[str, int] = {}
        unmapped: set[str] = set()
        errors: list[str] = []

        annot_dir = self._project_root / "annotations"
        annot_dir.mkdir(parents=True, exist_ok=True)

        for i, asset in enumerate(import_result.assets):
            if cancel_token and cancel_token.is_set():
                break

            stem = Path(asset.path).stem
            ann_path = ann_lookup.get(stem)

            if ann_path is None:
                continue

            matched += 1

            try:
                if annotation_format == "yolo":
                    doc = codec.load_annotations(
                        str(ann_path), asset.width, asset.height
                    )
                else:
                    doc = codec.load_annotations(str(ann_path))

                # Track label stats
                for obj in doc.objects:
                    cat_name = obj.attributes.get(
                        "category_name", str(obj.label_id)
                    )
                    label_counts[cat_name] = (
                        label_counts.get(cat_name, 0) + 1
                    )

                # Apply label mapping
                mapped_objects: list[AnnotationObject] = []
                for obj in doc.objects:
                    ext_id = obj.label_id
                    if label_mapping and ext_id in label_mapping:
                        new_id = label_mapping[ext_id]
                    else:
                        new_id = ext_id
                        if label_mapping:
                            cat_name = obj.attributes.get("category_name")
                            if cat_name:
                                unmapped.add(cat_name)

                    mapped_objects.append(
                        AnnotationObject(
                            id=obj.id,
                            label_id=new_id,
                            geometry_type=obj.geometry_type,
                            geometry=obj.geometry,
                            attributes=dict(obj.attributes),
                            source_object_id=obj.id,
                        )
                    )

                if not mapped_objects:
                    empty += 1

                new_doc = AnnotationDocument(
                    asset_id=asset.id,
                    image_width=asset.width,
                    image_height=asset.height,
                    objects=mapped_objects,
                )

                self._write_annotation_document(annot_dir, stem, new_doc)
                imported += 1

            except Exception as exc:
                logger.warning(
                    "Failed to parse annotation %s: %s", ann_path, exc
                )
                errors.append(f"Parse failed: {ann_path} — {exc}")

            if progress_callback:
                progress_callback(i + 1, total, asset.path)

        return AnnotationImportStats(
            total_annotation_files=len(ann_lookup),
            matched_count=matched,
            unmatched_count=len(ann_lookup) - matched,
            empty_count=empty,
            imported_count=imported,
            error_count=len(errors),
            label_counts=label_counts,
            unmapped_labels=frozenset(unmapped),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_annotation_document(
        annot_dir: Path, stem: str, doc: AnnotationDocument,
    ) -> None:
        """Write an AnnotationDocument to annotations/<stem>.json."""
        import json

        shapes: list[dict] = []
        for obj in doc.objects:
            shape: dict = {
                "id": obj.id,
                "label_id": obj.label_id,
                "geometry_type": obj.geometry_type,
            }
            if obj.geometry_type == "bbox_xyxy":
                x1, y1, x2, y2 = obj.geometry
                shape["points"] = [[x1, y1], [x2, y2]]
                shape["shape_type"] = "rectangle"
            elif obj.geometry_type == "obb_polygon":
                shape["points"] = list(obj.geometry)
                shape["shape_type"] = "obb_polygon"
            else:
                shape["points"] = []
                shape["shape_type"] = obj.geometry_type

            if obj.attributes:
                shape["attributes"] = obj.attributes

            shapes.append(shape)

        output = {
            "version": "1.0",
            "shapes": shapes,
            "imageWidth": doc.image_width,
            "imageHeight": doc.image_height,
            "imageLabels": doc.image_labels,
        }

        annot_dir.mkdir(parents=True, exist_ok=True)
        ann_path = annot_dir / f"{stem}.json"
        ann_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _import_xanylabel_annotations(
        self,
        source_path: Path,
        import_result: ImportResult,
        label_mapping: dict[int, int] | None,
        progress_callback: Callable | None = None,
        cancel_token: threading.Event | None = None,
    ) -> AnnotationImportStats:
        """Import X-AnyLabeling native JSON annotation files.

        Copies .json files from *source_path* to the project annotations/
        directory, matching by filename stem.
        """
        ann_stats = AnnotationImportStats()
        annot_dir = self._project_root / "annotations"
        annot_dir.mkdir(parents=True, exist_ok=True)

        # Build stem → annotation file map from source
        source_files: dict[str, Path] = {}
        for f in source_path.iterdir():
            if f.suffix == ".json" and not f.name.endswith(".tmp"):
                source_files[f.stem] = f

        ann_stats.total_annotation_files = len(source_files)

        # Match to imported assets and copy
        for asset in import_result.assets:
            asset_stem = Path(asset.path).stem
            if asset_stem in source_files:
                try:
                    data = json.loads(
                        source_files[asset_stem].read_text(encoding="utf-8")
                    )
                    # Apply label_mapping if provided
                    if label_mapping:
                        for shape in data.get("shapes", []):
                            lbl = shape.get("label", "")
                            if lbl in label_mapping:
                                shape["label"] = label_mapping[lbl]

                    # Write to project annotations/
                    target = annot_dir / f"{asset_stem}.json"
                    target.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )

                    # Count labels
                    shapes = data.get("shapes", [])
                    if shapes:
                        for s in shapes:
                            lbl = s.get("label", "unknown")
                            ann_stats.label_counts[lbl] = (
                                ann_stats.label_counts.get(lbl, 0) + 1
                            )
                        ann_stats.imported_count += 1
                    else:
                        ann_stats.empty_count += 1
                    ann_stats.matched_count += 1
                except (json.JSONDecodeError, OSError) as exc:
                    ann_stats.errors.append(
                        f"Failed to import {source_files[asset_stem]}: {exc}"
                    )
                    ann_stats.error_count += 1
            elif cancel_token and cancel_token.is_set():
                raise ImportCancelledError(
                    f"Annotation import cancelled after "
                    f"{ann_stats.matched_count} files"
                )

        ann_stats.unmatched_count = (
            ann_stats.total_annotation_files
            - ann_stats.matched_count
            - ann_stats.error_count
        )

        return ann_stats

    @staticmethod
    @staticmethod
    def _is_large(width: int, height: int, threshold: int = 2000) -> bool:
        """Check if either dimension exceeds *threshold*."""
        return width > threshold or height > threshold


__all__ = [
    "ImportService",
    "ImportCancelledError",
    "PrecheckResult",
]
