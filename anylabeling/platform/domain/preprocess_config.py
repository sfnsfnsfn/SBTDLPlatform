"""PreprocessConfig — immutable configuration for the preprocess pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PreprocessConfig:
    """Immutable configuration for tile slicing, dataset splitting, and augmentation.

    This is the contract that PreprocessWorkspace builds and emits.
    """

    tile_width: int = 1024
    tile_height: int = 1024
    overlap_x: int = 256  # in pixels
    overlap_y: int = 256  # in pixels
    edge_mode: str = "crop"  # "strict" | "crop" | "pad"
    split_strategy: str = "random_by_asset"  # "random_by_asset" | "random_by_tile" | "manual"
    train_ratio: float = 0.7
    val_ratio: float = 0.2
    test_ratio: float = 0.1
    random_seed: int = 42
    augmentations: frozenset[str] = frozenset()

    @staticmethod
    def estimate_tiles(config: PreprocessConfig, image_width: int, image_height: int) -> int:
        """Estimate the number of tiles for a single image given the config.

        Uses the stride = tile_size - overlap. For edge_mode != "strict",
        at least one tile is always produced per dimension.
        """
        if config.tile_width <= 0 or config.tile_height <= 0:
            return 0
        if image_width <= 0 or image_height <= 0:
            return 0

        stride_x = max(1, config.tile_width - config.overlap_x)
        stride_y = max(1, config.tile_height - config.overlap_y)

        if config.edge_mode == "strict":
            # Only tiles that fully fit
            tiles_x = max(0, (image_width - config.overlap_x) // stride_x) if image_width >= config.tile_width else 0
            tiles_y = max(0, (image_height - config.overlap_y) // stride_y) if image_height >= config.tile_height else 0
        else:
            # crop/pad: always at least 1 tile
            effective_w = max(1, image_width - config.overlap_x)
            effective_h = max(1, image_height - config.overlap_y)
            tiles_x = max(1, math.ceil(effective_w / stride_x))
            tiles_y = max(1, math.ceil(effective_h / stride_y))

        return tiles_x * tiles_y


def validate_split_ratios(train: float, val: float, test: float) -> list[str]:
    """Validate train/val/test split ratios. Returns list of issues (empty = valid)."""
    issues: list[str] = []

    total = train + val + test
    if abs(total - 1.0) > 0.001:
        issues.append(f"Ratios sum to {total:.3f}, expected 1.0")

    if train <= 0:
        issues.append("Train ratio must be > 0")
    if val < 0:
        issues.append("Val ratio must be >= 0")
    if test < 0:
        issues.append("Test ratio must be >= 0")

    return issues


__all__ = [
    "PreprocessConfig",
    "validate_split_ratios",
]
