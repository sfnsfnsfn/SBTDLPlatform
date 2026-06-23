"""SplitManifest — immutable record of dataset split assignments."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SplitManifest:
    """Immutable record capturing how assets/tiles are assigned to splits.

    ``asset_assignments`` maps asset_id to one of "train", "val", or "test".
    """

    strategy: str  # "random_by_asset" | "random_by_tile" | "manual"
    train_ratio: float
    val_ratio: float
    test_ratio: float
    random_seed: int
    asset_assignments: dict[str, str]  # asset_id -> "train"|"val"|"test"

    @staticmethod
    def compute_split_counts(
        manifest: SplitManifest, total_items: int,
    ) -> tuple[int, int, int]:
        """Compute (train_count, val_count, test_count) for *total_items*.

        Handles rounding so that the counts always sum to *total_items*.
        """
        if total_items <= 0:
            return (0, 0, 0)

        train = int(round(manifest.train_ratio * total_items))
        val = int(round(manifest.val_ratio * total_items))
        test = total_items - train - val

        # Ensure no negative values
        if test < 0:
            # Adjust val down
            val = max(0, total_items - train)
            test = total_items - train - val

        if val < 0:
            val = 0
            train = total_items - test

        return (train, val, test)


__all__ = ["SplitManifest"]
