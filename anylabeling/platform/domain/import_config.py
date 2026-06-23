"""Import domain contracts — pure dataclass DTOs with no UI or framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field

from anylabeling.platform.domain.asset import Asset

# Shared supported image extensions — single source of truth
# Used by ImportService, AssetRepository, and import UI
_SUPPORTED_EXTENSIONS_TUPLE: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
)


def get_supported_extensions() -> tuple[str, ...]:
    """Return the canonical supported image extensions tuple."""
    return _SUPPORTED_EXTENSIONS_TUPLE


@dataclass(frozen=True)
class ImportConfig:
    """Configuration for the import process.

    Attributes:
        deduplicate: If True, skip files with duplicate SHA-256 hashes.
        group_by_folder: If True, assign ``group_id`` from the source folder name.
        detect_large_images: If True, mark images exceeding ``large_threshold``.
        large_threshold: Pixel threshold for large image detection.
        supported_extensions: File extensions eligible for import.
    """

    deduplicate: bool = True
    group_by_folder: bool = True
    detect_large_images: bool = True
    large_threshold: int = 2000
    supported_extensions: tuple[str, ...] = _SUPPORTED_EXTENSIONS_TUPLE


@dataclass
class ImportResult:
    """Result of an import operation.

    Attributes:
        assets: Successfully imported Asset descriptors.
        total: Total number of files processed (including duplicates).
        large_count: Number of images exceeding the large threshold.
        duplicate_count: Number of duplicate files skipped.
        errors: Human-readable error messages for failed imports.
    """

    assets: list[Asset]
    total: int
    large_count: int
    duplicate_count: int
    errors: list[str] = field(default_factory=list)


class ImportCancelledError(Exception):
    """Raised when an import operation is cancelled by the user."""

    def __init__(self, message: str = "Import cancelled") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class PrecheckResult:
    """Result of scanning sources before importing — no files are copied.

    Attributes:
        total_files: Total number of files discovered across all sources.
        valid_files: Absolute paths of files that passed all checks.
        damaged_files: Paths of files that could not be read by cv2.
        unsupported_files: Paths with unsupported extensions.
        oversized_files: (path, width, height) tuples exceeding large_threshold.
        estimated_size_bytes: Sum of file sizes of valid files.
        errors: Human-readable error messages.
    """

    total_files: int
    valid_files: list[str] = field(default_factory=list)
    damaged_files: list[str] = field(default_factory=list)
    unsupported_files: list[str] = field(default_factory=list)
    oversized_files: list[tuple[str, int, int]] = field(default_factory=list)
    estimated_size_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.valid_files)

    @property
    def damaged_count(self) -> int:
        return len(self.damaged_files)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_files)

    @property
    def oversized_count(self) -> int:
        return len(self.oversized_files)


@dataclass(frozen=True)
class AnnotationImportStats:
    """Statistics for annotation companion import.

    Attributes:
        total_annotation_files: Number of annotation files found.
        matched_count: Number of annotation files matched to images.
        unmatched_count: Number of annotation files without matching images.
        empty_count: Number of annotation files with no objects.
        imported_count: Number of annotation documents successfully written.
        error_count: Number of annotation files that failed to parse.
        label_counts: Mapping of label_name → instance count across all files.
        unmapped_labels: Set of label names not found in project labels.
        errors: Human-readable error messages.
    """

    total_annotation_files: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    empty_count: int = 0
    imported_count: int = 0
    error_count: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)
    unmapped_labels: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


__all__ = [
    "AnnotationImportStats",
    "ImportCancelledError",
    "ImportConfig",
    "ImportResult",
    "PrecheckResult",
    "get_supported_extensions",
]
