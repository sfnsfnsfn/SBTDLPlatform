"""DatasetBuildService — orchestrate the complete dataset build pipeline.

Converts project assets + annotations into a training-ready dataset on disk.
Pure Python — no UI or framework imports.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anylabeling.platform.domain.records import DatasetBuildRecord

if TYPE_CHECKING:
    from anylabeling.platform.application.project_context import ProjectContext

import cv2
import numpy as np

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.dataset import (
    DatasetBuild,
    LeakageReport,
    ManifestIntegrityReport,
)
from anylabeling.platform.domain.task import TaskSpec
from anylabeling.platform.domain.tile import TilePlan, TileRecord
from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter
from anylabeling.platform.infrastructure.image_sources.base import (
    LargeImageSource,
)
from anylabeling.platform.infrastructure.manifest_store import ManifestStore
from anylabeling.platform.tiling.label_splitters import (
    ClassifySplitter,
    HBBSplitter,
    OBBSplitter,
    PolygonSplitter,
    PoseSplitter,
)
from anylabeling.platform.tiling.tile_materializer import TileMaterializer
from anylabeling.platform.tiling.tile_planner import TilePlanner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Splitter registry — maps task_family → splitter class
# ---------------------------------------------------------------------------

_SPLITTER_REGISTRY: dict[str, type] = {
    "detection_hbb": HBBSplitter,
    "detection_obb": OBBSplitter,
    "instance_segmentation": PolygonSplitter,
    "pose": PoseSplitter,
    "classification": ClassifySplitter,
}


class DatasetBuildService:
    """Orchestrates the complete dataset build pipeline.

    Steps performed by :meth:`build`:

    1. Assign split (train / val / test) to each asset using *split_seed*.
       Assets sharing the same ``group_id`` are always placed in the same split.

    2. If *tile_plan* is provided:
       a. Generate ``TileRecord`` instances for each asset via ``TilePlanner``.
       b. Assign the asset's split to each tile.
       c. Materialize tile images via ``TileMaterializer``.

    3. Split annotation objects per tile using the appropriate ``LabelSplitter``
       for the task family, and write YOLO-format ``.txt`` label files.

    4. Write output artefacts under ``dataset_builds/<build_id>/``:

       * ``build.json`` — ``DatasetBuild`` metadata
       * ``split_manifest.jsonl`` — one row per asset
       * ``tile_manifest.jsonl`` — one row per tile (only when tiling)
       * ``data.yaml`` — YOLO-format dataset descriptor
       * ``images/{train,val,test}/`` — tile images (or full images if not tiling)
       * ``labels/{train,val,test}/`` — YOLO-format ``.txt`` labels
       * ``_READY`` — marker file written after a successful build

    5. Return a ``DatasetBuild`` with build metadata.
    """

    def __init__(self, project_root: str | Path, context: ProjectContext | None = None) -> None:
        """Initialize with the project root directory.

        Parameters
        ----------
        project_root:
            Root of the V4 MVP project directory (contains ``dataset_builds/``).
        context:
            Optional ProjectContext for persisting build state to SQLite.
            When ``None`` (default), only filesystem artifacts are written
            (backward-compatible with existing callers).
        """
        self._project_root = Path(project_root)
        self._context = context

    @property
    def project_root(self) -> Path:
        """Root of the V4 MVP project directory (read-only)."""
        return self._project_root

    # ------------------------------------------------------------------
    # build — main entry point
    # ------------------------------------------------------------------

    def build(
        self,
        task_spec: TaskSpec,
        assets: list[Asset],
        annotations: dict[str, AnnotationDocument],
        tile_plan: TilePlan | None = None,
        image_sources: dict[str, LargeImageSource] | None = None,
        split_seed: int = 42,
        split_ratios: tuple[float, float, float] = (0.7, 0.2, 0.1),
        split_strategy: str = "random_by_asset",
    ) -> DatasetBuild:
        """Execute the complete dataset build pipeline.

        Parameters
        ----------
        task_spec:
            Immutable task specification (task family, labels, metric).
        assets:
            List of assets to include in the dataset.
        annotations:
            Mapping of ``asset_id`` → ``AnnotationDocument``.
        tile_plan:
            Optional tiling parameters.  When ``None``, no tiling is performed
            and full images are used directly (classification workflow).
        image_sources:
            Optional mapping ``asset_id`` → ``LargeImageSource``.  Required
            when *tile_plan* is provided (to materialize tiles).  For
            classification without tiling it may be omitted.
        split_seed:
            Seed for deterministic split assignment.
        split_ratios:
            ``(train_ratio, val_ratio, test_ratio)``.  Must sum to 1.0.
        split_strategy:
            ``"random_by_asset"`` or ``"group_by_group_id"``.

        Returns
        -------
        DatasetBuild
            Metadata for the completed build.

        Raises
        ------
        ValueError
            If *tile_plan* is provided but *image_sources* is missing, or if
            split ratios are invalid.
        """
        # --- validate inputs ---
        if tile_plan is not None and image_sources is None:
            raise ValueError(
                "image_sources is required when tile_plan is provided"
            )

        # Require image_sources for non-tiling, non-classification builds
        # that actually have assets. Classification may omit image_sources
        # by design (images organized by class directories). (C7 fix)
        if (
            tile_plan is None
            and image_sources is None
            and assets
            and task_spec.family != "classification"
        ):
            raise ValueError(
                "image_sources is required when building a dataset without "
                "tiling for non-classification tasks with assets. Provide at "
                "least one LargeImageSource per asset to copy images into "
                "the dataset output directory."
            )

        total = sum(split_ratios)
        if not (0.999 <= total <= 1.001):
            raise ValueError(
                f"split_ratios must sum to 1.0, got {split_ratios} (sum={total})"
            )
        for r in split_ratios:
            if r < 0:
                raise ValueError(f"split_ratios must be non-negative: {split_ratios}")

        image_sources = image_sources or {}

        # --- generate build id ---
        build_id = self._make_build_id(
            task_spec, assets, split_seed, split_strategy, split_ratios, tile_plan
        )

        build_dir = self._project_root / "dataset_builds" / build_id

        # --- create DB record before any build work (if context available) ---
        if self._context is not None:
            split_ratios_json = json.dumps(
                {
                    "train": split_ratios[0],
                    "val": split_ratios[1],
                    "test": split_ratios[2],
                }
            )
            tile_plan_json: str | None = None
            if tile_plan is not None:
                tile_plan_json = json.dumps(
                    {
                        "tile_width": tile_plan.tile_width,
                        "tile_height": tile_plan.tile_height,
                        "overlap_x": tile_plan.overlap_x,
                        "overlap_y": tile_plan.overlap_y,
                        "edge_mode": tile_plan.edge_mode,
                        "min_object_pixels": tile_plan.min_object_pixels,
                        "min_visibility_ratio": tile_plan.min_visibility_ratio,
                    }
                )
            self._context.dataset_builds.create(
                DatasetBuildRecord(
                    id=build_id,
                    task_family=task_spec.family,
                    output_path=str(build_dir),
                    split_strategy=split_strategy,
                    split_seed=split_seed,
                    split_ratios_json=split_ratios_json,
                    tile_plan_json=tile_plan_json,
                    preprocess_config_json=None,
                    manifest_hash="",
                    status="running",
                )
            )

        # mkdir AFTER DB record creation — avoids orphaned directories
        # if the DB insert fails
        build_dir.mkdir(parents=True, exist_ok=True)

        try:
            images_dir = build_dir / "images"
            labels_dir = build_dir / "labels"

            # --- step 1: assign splits ---
            asset_splits = self._assign_splits(assets, split_seed, split_ratios, split_strategy)

            # --- step 2: generate tiles & materialize ---
            all_tiles: list[TileRecord] = []
            tile_split_map: dict[str, str] = {}  # tile_id → split

            if tile_plan is not None:
                for asset in assets:
                    asset_tiles = TilePlanner.plan(asset, tile_plan)
                    split_label = asset_splits[asset.id]

                    # Assign split to each tile
                    tiles_with_split: list[TileRecord] = []
                    for t in asset_tiles:
                        t_with_split = TileRecord(
                            tile_id=t.tile_id,
                            asset_id=t.asset_id,
                            x0=t.x0,
                            y0=t.y0,
                            width=t.width,
                            height=t.height,
                            valid_width=t.valid_width,
                            valid_height=t.valid_height,
                            split=split_label,  # type: ignore[arg-type]
                        )
                        tiles_with_split.append(t_with_split)
                        tile_split_map[t.tile_id] = split_label
                        all_tiles.append(t_with_split)

                    # Materialize tiles for this asset
                    source = image_sources.get(asset.id)
                    if source is None:
                        raise ValueError(
                            f"No image source for asset {asset.id} (required for tiling)"
                        )

                    split_dir = images_dir / split_label
                    materializer = TileMaterializer(split_dir)
                    materializer.materialize_all(source, tiles_with_split)

                    # Write YOLO label files for each tile
                    splitter_cls = _SPLITTER_REGISTRY.get(task_spec.family)
                    if splitter_cls is not None:
                        ann_doc = annotations.get(asset.id)
                        splitter = splitter_cls()
                        label_out_dir = labels_dir / split_label
                        label_out_dir.mkdir(parents=True, exist_ok=True)
                        for t in tiles_with_split:
                            tile_objects = (
                                splitter.split(ann_doc, t, tile_plan)
                                if ann_doc is not None
                                else []
                            )
                            self._write_yolo_labels(
                                tile_objects,
                                t.width,
                                t.height,
                                label_out_dir / f"{t.tile_id}.txt",
                                task_spec,
                            )
            else:
                # No tiling — write YOLO labels for full images
                for asset in assets:
                    split_label = asset_splits[asset.id]
                    ann_doc = annotations.get(asset.id)
                    if ann_doc is None:
                        continue

                    splitter_cls = _SPLITTER_REGISTRY.get(task_spec.family)
                    label_out_dir = labels_dir / split_label
                    label_out_dir.mkdir(parents=True, exist_ok=True)

                    if splitter_cls is not None:
                        # For no-tiling, write YOLO labels directly from annotation objects
                        self._write_yolo_labels(
                            ann_doc.objects,
                            asset.width,
                            asset.height,
                            label_out_dir / f"{asset.id}.txt",
                            task_spec,
                        )

                    # Copy full images to split dirs if sources available
                    source = image_sources.get(asset.id)
                    if source is not None:
                        img_out_dir = images_dir / split_label
                        img_out_dir.mkdir(parents=True, exist_ok=True)
                        pixels = source.read_region(
                            rect_l0=(0, 0, asset.width, asset.height),
                            output_size=(asset.width, asset.height),
                        )
                        out_path = img_out_dir / f"{asset.id}.png"
                        self._save_image(pixels, out_path)

            # --- step 4: compute manifest hashes ---
            asset_manifest_hash = self._hash_asset_list(assets)
            annotation_manifest_hash = self._hash_annotations(annotations)

            # --- step 5: write manifests ---
            self._write_split_manifest(build_dir, assets, asset_splits, all_tiles)
            if tile_plan is not None:
                self._write_tile_manifest(build_dir, all_tiles)

            # --- step 6: write data.yaml ---
            self._write_data_yaml(build_dir, task_spec)

            # --- step 7: write build.json ---
            dataset_build = DatasetBuild(
                id=build_id,
                task_spec_id=task_spec.id,
                source_asset_manifest_hash=asset_manifest_hash,
                annotation_manifest_hash=annotation_manifest_hash,
                split_seed=split_seed,
                split_strategy=split_strategy,
                tile_plan=tile_plan,
                output_path=str(build_dir),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_build_json(build_dir, dataset_build)

            # --- step 8: mark completed in DB first, then write _READY ---
            if self._context is not None:
                self._context.dataset_builds.mark_completed(build_id)

            # write _READY sentinel ONLY after DB mark succeeds
            (build_dir / "_READY").write_text(
                f"build {build_id} completed\n", encoding="utf-8"
            )

            return dataset_build

        except Exception as exc:
            if self._context is not None:
                try:
                    self._context.dataset_builds.mark_failed(
                        build_id, error_message=str(exc)
                    )
                except Exception as db_exc:
                    logger.error(
                        "Failed to mark build %s as failed in DB: %s",
                        build_id,
                        db_exc,
                    )
            raise

    # ------------------------------------------------------------------
    # split assignment
    # ------------------------------------------------------------------

    def _assign_splits(
        self,
        assets: list[Asset],
        seed: int,
        ratios: tuple[float, float, float],
        strategy: str,
    ) -> dict[str, str]:
        """Assign split (train/val/test) to each asset. Returns ``{asset_id: split}``.

        Strategy ``"random_by_asset"`` — shuffle assets by seed, assign by ratio.
        Strategy ``"group_by_group_id"`` — group by ``asset.group_id``, assign
        whole groups to the same split.

        CRITICAL: Assets with the same ``group_id`` MUST go to the same split
        when using ``group_by_group_id`` strategy.
        """
        rng = random.Random(seed)

        if strategy == "group_by_group_id":
            # Group assets by group_id (or asset.id if no group)
            groups: dict[str, list[Asset]] = {}
            for a in assets:
                key = a.group_id or a.id
                groups.setdefault(key, []).append(a)

            group_ids = sorted(groups.keys())
            rng.shuffle(group_ids)

            n = len(group_ids)
            n_train = max(1, int(n * ratios[0]))
            n_val = max(1, int(n * ratios[1])) if ratios[1] > 0 else 0

            train_groups = set(group_ids[:n_train])
            val_groups = set(group_ids[n_train : n_train + n_val])

            result: dict[str, str] = {}
            for gid, group_assets in groups.items():
                if gid in train_groups:
                    split_label = "train"
                elif gid in val_groups:
                    split_label = "val"
                else:
                    split_label = "test"
                for a in group_assets:
                    result[a.id] = split_label
            return result

        # random_by_asset (default)
        shuffled = list(assets)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_train = max(1, int(n * ratios[0]))
        n_val = max(1, int(n * ratios[1])) if ratios[1] > 0 else 0

        result = {}
        for i, a in enumerate(shuffled):
            if i < n_train:
                result[a.id] = "train"
            elif i < n_train + n_val:
                result[a.id] = "val"
            else:
                result[a.id] = "test"
        return result

    # ------------------------------------------------------------------
    # YOLO label writing
    # ------------------------------------------------------------------

    @staticmethod
    def _write_yolo_labels(
        objects: list[AnnotationObject],
        img_width: int,
        img_height: int,
        output_path: Path,
        task_spec: TaskSpec,
    ) -> None:
        """Write YOLO-format ``.txt`` label file for a single image / tile.

        Format per task family:

        * ``detection_hbb``: ``class_id xc yc w h`` (normalised)
        * ``detection_obb``: ``class_id x1 y1 x2 y2 x3 y3 x4 y4`` (normalised)
        * ``instance_segmentation``: ``class_id x1 y1 x2 y2 ...`` (normalised)
        * ``pose``: ``class_id xc yc w h kx1 ky1 kv1 ...`` (normalised)
        * ``classification``: only ``class_id``, written if image-level labels exist
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for obj in objects:
            label_id = obj.label_id
            gt = obj.geometry_type

            if label_id < 0:
                continue

            if gt == "bbox_xyxy":
                x1, y1, x2, y2 = obj.geometry  # type: ignore[misc]
                xc = ((x1 + x2) / 2.0) / img_width
                yc = ((y1 + y2) / 2.0) / img_height
                w = (x2 - x1) / img_width
                h = (y2 - y1) / img_height
                lines.append(f"{label_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")

            elif gt == "obb_polygon":
                points = obj.geometry  # type: ignore[assignment]
                norm_pts = []
                for px, py in points:
                    norm_pts.append(f"{px / img_width:.6f}")
                    norm_pts.append(f"{py / img_height:.6f}")
                lines.append(f"{label_id} " + " ".join(norm_pts))

            elif gt == "polygon":
                points = obj.geometry  # type: ignore[assignment]
                norm_pts = []
                for px, py in points:
                    norm_pts.append(f"{px / img_width:.6f}")
                    norm_pts.append(f"{py / img_height:.6f}")
                lines.append(f"{label_id} " + " ".join(norm_pts))

            elif gt == "keypoints":
                keypoints = obj.geometry  # type: ignore[assignment]
                # Compute bbox from visible keypoints
                visible = [(x, y) for x, y, v in keypoints if v > 0]
                if not visible:
                    continue
                kx1 = min(x for x, _ in visible)
                ky1 = min(y for _, y in visible)
                kx2 = max(x for x, _ in visible)
                ky2 = max(y for _, y in visible)
                xc = ((kx1 + kx2) / 2.0) / img_width
                yc = ((ky1 + ky2) / 2.0) / img_height
                bw = (kx2 - kx1) / img_width
                bh = (ky2 - ky1) / img_height

                kp_parts = []
                for kx, ky, kv in keypoints:
                    kp_parts.append(f"{kx / img_width:.6f}")
                    kp_parts.append(f"{ky / img_height:.6f}")
                    kp_parts.append(str(int(kv)))
                lines.append(
                    f"{label_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f} "
                    + " ".join(kp_parts)
                )

        if lines:
            output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            # Write empty file so it exists for images with no objects
            output_path.write_text("", encoding="utf-8")

    # ------------------------------------------------------------------
    # data.yaml
    # ------------------------------------------------------------------

    @staticmethod
    def _write_data_yaml(
        build_dir: Path,
        task_spec: TaskSpec,
    ) -> None:
        """Write YOLO-format ``data.yaml`` to *build_dir*."""
        names: dict[int, str] = {}
        for lb in task_spec.labels:
            names[lb.id] = lb.name

        yaml_lines = [
            f"path: {build_dir.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "",
            "names:",
        ]
        for idx in sorted(names):
            yaml_lines.append(f"  {idx}: {names[idx]}")
        yaml_lines.append(f"nc: {len(names)}")

        AtomicWriter.write_text(build_dir / "data.yaml", "\n".join(yaml_lines) + "\n")

    # ------------------------------------------------------------------
    # manifest helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_split_manifest(
        build_dir: Path,
        assets: list[Asset],
        asset_splits: dict[str, str],
        tiles: list[TileRecord],
    ) -> None:
        """Write ``split_manifest.jsonl`` — one row per asset."""
        # Count tiles per asset
        tile_counts: dict[str, int] = {}
        for t in tiles:
            tile_counts[t.asset_id] = tile_counts.get(t.asset_id, 0) + 1

        path = build_dir / "split_manifest.jsonl"
        # Clear existing file if any
        if path.exists():
            path.unlink()

        for asset in assets:
            row = {
                "asset_id": asset.id,
                "split": asset_splits.get(asset.id, "none"),
                "tile_count": tile_counts.get(asset.id, 0),
                "group_id": asset.group_id,
                "width": asset.width,
                "height": asset.height,
                "path": asset.path,
            }
            ManifestStore.append_jsonl(path, row)

    @staticmethod
    def _write_tile_manifest(
        build_dir: Path,
        tiles: list[TileRecord],
    ) -> None:
        """Write ``tile_manifest.jsonl`` — one row per tile."""
        path = build_dir / "tile_manifest.jsonl"
        if path.exists():
            path.unlink()

        for tile in tiles:
            row = {
                "tile_id": tile.tile_id,
                "asset_id": tile.asset_id,
                "x0": tile.x0,
                "y0": tile.y0,
                "width": tile.width,
                "height": tile.height,
                "valid_width": tile.valid_width,
                "valid_height": tile.valid_height,
                "split": tile.split,
            }
            ManifestStore.append_jsonl(path, row)

    # ------------------------------------------------------------------
    # build.json
    # ------------------------------------------------------------------

    @staticmethod
    def _write_build_json(build_dir: Path, build: DatasetBuild) -> None:
        """Write ``build.json`` with dataset build metadata."""
        # Compute manifest file hashes for integrity verification
        split_manifest_path = build_dir / "split_manifest.jsonl"
        tile_manifest_path = build_dir / "tile_manifest.jsonl"
        split_manifest_hash = ManifestStore.compute_manifest_hash(split_manifest_path) if split_manifest_path.exists() else ""
        tile_manifest_hash = ManifestStore.compute_manifest_hash(tile_manifest_path) if tile_manifest_path.exists() else ""

        data: dict[str, Any] = {
            "id": build.id,
            "task_spec_id": build.task_spec_id,
            "source_asset_manifest_hash": build.source_asset_manifest_hash,
            "annotation_manifest_hash": build.annotation_manifest_hash,
            "split_manifest_hash": split_manifest_hash,
            "tile_manifest_hash": tile_manifest_hash,
            "split_seed": build.split_seed,
            "split_strategy": build.split_strategy,
            "tile_plan": None,
            "augmentation_plan_id": build.augmentation_plan_id,
            "adapter_id": build.adapter_id,
            "output_path": build.output_path,
            "created_at": build.created_at,
        }
        if build.tile_plan is not None:
            data["tile_plan"] = {
                "tile_width": build.tile_plan.tile_width,
                "tile_height": build.tile_plan.tile_height,
                "overlap_x": build.tile_plan.overlap_x,
                "overlap_y": build.tile_plan.overlap_y,
                "edge_mode": build.tile_plan.edge_mode,
                "min_object_pixels": build.tile_plan.min_object_pixels,
                "min_visibility_ratio": build.tile_plan.min_visibility_ratio,
            }
        AtomicWriter.write_json(build_dir / "build.json", data)

    # ------------------------------------------------------------------
    # hashing helpers (deterministic manifest hashes)
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_asset_list(assets: list[Asset]) -> str:
        """Compute a stable hash of the asset list."""
        h = hashlib.sha256()
        for a in sorted(assets, key=lambda x: x.id):
            h.update(
                f"{a.id}|{a.path}|{a.width}|{a.height}".encode("utf-8")
            )
        return h.hexdigest()

    @staticmethod
    def _hash_annotations(annotations: dict[str, AnnotationDocument]) -> str:
        """Compute a stable hash of the annotation documents."""
        h = hashlib.sha256()
        for asset_id in sorted(annotations):
            doc = annotations[asset_id]
            h.update(f"{asset_id}|{doc.image_width}|{doc.image_height}".encode("utf-8"))
            for obj in sorted(doc.objects, key=lambda o: o.id):
                h.update(
                    f"{obj.id}|{obj.label_id}|{obj.geometry_type}".encode("utf-8")
                )
        return h.hexdigest()

    # ------------------------------------------------------------------
    # build id generation
    # ------------------------------------------------------------------

    @staticmethod
    def _make_build_id(
        task_spec: TaskSpec,
        assets: list[Asset],
        split_seed: int,
        split_strategy: str,
        split_ratios: tuple[float, float, float],
        tile_plan: TilePlan | None,
    ) -> str:
        """Generate a deterministic build id."""
        h = hashlib.sha256()
        h.update(task_spec.id.encode("utf-8"))
        for a in sorted(assets, key=lambda x: x.id):
            h.update(a.id.encode("utf-8"))
        h.update(str(split_seed).encode("utf-8"))
        h.update(split_strategy.encode("utf-8"))
        h.update(f"{split_ratios[0]:.3f}_{split_ratios[1]:.3f}_{split_ratios[2]:.3f}".encode("utf-8"))
        if tile_plan is not None:
            h.update(
                f"tp:{tile_plan.tile_width}x{tile_plan.tile_height}"
                f"_o{tile_plan.overlap_x}_{tile_plan.overlap_y}"
                f"_{tile_plan.edge_mode}".encode("utf-8")
            )
        return f"build_{h.hexdigest()[:12]}"

    # ------------------------------------------------------------------
    # image save helper
    # ------------------------------------------------------------------

    @staticmethod
    def _save_image(pixels: np.ndarray, out_path: Path) -> None:
        """Save a numpy image array to disk as PNG."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if pixels.ndim == 3 and pixels.shape[2] >= 3:
            save_array = pixels[:, :, :3][:, :, ::-1]  # RGB -> BGR
        elif pixels.ndim == 3 and pixels.shape[2] == 1:
            save_array = pixels[:, :, 0]
        else:
            save_array = pixels
        cv2.imwrite(str(out_path), save_array)


    # ------------------------------------------------------------------
    # Manifest integrity verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_build_integrity(build_dir: Path) -> ManifestIntegrityReport:
        """Verify all manifests in a build directory are intact.

        Reads ``build.json`` to obtain expected manifest hashes, then
        re-hashes each manifest file on disk and compares.  Returns a
        ``ManifestIntegrityReport`` summarising any mismatches.
        """
        build_json = build_dir / "build.json"
        if not build_json.exists():
            return ManifestIntegrityReport(
                build_id=build_dir.name,
                passed=False,
                error=f"build.json not found in {build_dir}",
            )

        try:
            data = json.loads(build_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return ManifestIntegrityReport(
                build_id=build_dir.name,
                passed=False,
                error=f"build.json is not valid JSON: {exc}",
            )

        build_id = data.get("id", build_dir.name)
        checked: list[str] = []
        corrupted: list[str] = []
        missing: list[str] = []

        # Check split manifest
        split_path = build_dir / "split_manifest.jsonl"
        checked.append("split_manifest.jsonl")
        expected_split = data.get("split_manifest_hash", "")
        if expected_split:
            if not ManifestStore.verify_manifest_hash(split_path, expected_split):
                if split_path.exists():
                    corrupted.append("split_manifest.jsonl")
                else:
                    missing.append("split_manifest.jsonl")

        # Check tile manifest (if tiles were used)
        tile_path = build_dir / "tile_manifest.jsonl"
        if tile_path.exists() or data.get("tile_manifest_hash"):
            checked.append("tile_manifest.jsonl")
            expected_tile = data.get("tile_manifest_hash", "")
            if expected_tile:
                if not ManifestStore.verify_manifest_hash(tile_path, expected_tile):
                    if tile_path.exists():
                        corrupted.append("tile_manifest.jsonl")
                    else:
                        missing.append("tile_manifest.jsonl")

        passed = len(corrupted) == 0 and len(missing) == 0 and not bool(
            ManifestIntegrityReport(
                build_id=build_id,
                passed=False,
            ).error
        )

        return ManifestIntegrityReport(
            build_id=build_id,
            passed=passed,
            checked_files=checked,
            corrupted_files=corrupted,
            missing_files=missing,
        )

    # ------------------------------------------------------------------
    # Data leakage detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_leakage(
        build_dir: Path,
        task_spec=None,  # type: ignore[no-untyped-def]
    ) -> LeakageReport:
        """Analyse a completed build for data leakage and class imbalance.

        Reads ``split_manifest.jsonl`` to identify:
        1. Cross-split group leakage — groups appearing in more than
           one split (train/val/test).
        2. Per-class distribution imbalance — classes whose
           representation in any split falls below a warning threshold.

        Parameters
        ----------
        build_dir:
            Path to the dataset build directory containing manifests.
        task_spec:
            Optional TaskSpec for label-name resolution in warnings.

        Returns
        -------
        LeakageReport
            Summary with leakage flags and imbalance warnings.
        """
        build_json = build_dir / "build.json"
        build_id = build_dir.name
        split_strategy = "unknown"

        if build_json.exists():
            try:
                data = json.loads(build_json.read_text(encoding="utf-8"))
                build_id = data.get("id", build_id)
                split_strategy = data.get("split_strategy", split_strategy)
            except json.JSONDecodeError:
                pass

        # Read split manifest
        split_manifest = build_dir / "split_manifest.jsonl"
        if not split_manifest.exists():
            return LeakageReport(
                build_id=build_id,
                split_strategy=split_strategy,
                passed=False,
            )

        rows = ManifestStore.read_jsonl(split_manifest)
        if not rows:
            return LeakageReport(
                build_id=build_id,
                split_strategy=split_strategy,
                passed=True,
            )

        # 1. Cross-split group leakage
        group_splits: dict[str, set[str]] = {}
        for row in rows:
            gid = row.get("group_id")
            if gid is None:
                continue
            split_label = row.get("split", "none")
            if split_label == "none":
                continue
            group_splits.setdefault(gid, set()).add(split_label)

        cross_split_groups = sorted(
            gid for gid, splits in group_splits.items() if len(splits) > 1
        )
        has_cross_split = len(cross_split_groups) > 0

        # 2. Per-class distribution (from tile manifest if available)
        tile_manifest = build_dir / "tile_manifest.jsonl"
        if tile_manifest.exists():
            # Count YOLO label files for distribution
            labels_dir = build_dir / "labels"
            per_class: dict[str, dict[str, int]] = {}
            if labels_dir.is_dir():
                for split_name in ("train", "val", "test"):
                    split_dir = labels_dir / split_name
                    if not split_dir.is_dir():
                        continue
                    for label_file in split_dir.glob("*.txt"):
                        try:
                            content = label_file.read_text(encoding="utf-8").strip()
                            if not content:
                                continue
                            for line in content.splitlines():
                                parts = line.split()
                                if parts:
                                    class_id = parts[0]
                                    per_class.setdefault(class_id, {"train": 0, "val": 0, "test": 0})
                                    per_class[class_id][split_name] = per_class[class_id].get(split_name, 0) + 1
                        except (OSError, json.JSONDecodeError, ValueError) as exc:
                            logger.warning(
                                "Failed to read label file %s: %s",
                                label_file, exc,
                            )
        else:
            # No tiling — count from split manifest and annotations
            per_class = {}

        # Detect class imbalance: any class with < max(1, 1% of split) samples
        class_imbalance_warnings: list[str] = []
        for class_id, split_counts in per_class.items():
            total_for_class = sum(split_counts.values())
            label_name = (
                task_spec.labels[int(class_id)].name
                if task_spec and int(class_id) < len(task_spec.labels)
                else class_id
            ) if task_spec else class_id
            for split_name, count in split_counts.items():
                split_total = sum(
                    c.get(split_name, 0) for c in per_class.values()
                )
                threshold = max(1, int(split_total * 0.01))
                if count < threshold:
                    pct = (count / max(1, split_total)) * 100
                    class_imbalance_warnings.append(
                        f"Class '{label_name}' has {count} sample(s) "
                        f"in {split_name} ({pct:.1f}% vs >=1% expected)"
                    )

        passed = not has_cross_split

        return LeakageReport(
            build_id=build_id,
            split_strategy=split_strategy,
            passed=passed,
            has_cross_split_groups=has_cross_split,
            cross_split_groups=cross_split_groups,
            per_class_distribution={
                class_id: dict(counts)
                for class_id, counts in per_class.items()
            },
            class_imbalance_warnings=class_imbalance_warnings,
        )


__all__ = ["DatasetBuildService"]
