"""Image source abstractions — protocol + concrete implementations."""

from anylabeling.platform.infrastructure.image_sources.base import (
    ImageMetadata,
    LargeImageSource,
)
from anylabeling.platform.infrastructure.image_sources.memory_image_source import (
    MemoryImageSource,
)
from anylabeling.platform.infrastructure.image_sources.qt_image_source import (
    QtImageSource,
)
from anylabeling.platform.infrastructure.image_sources.tiff_image_source import (
    TiffImageSource,
)

__all__ = [
    "ImageMetadata",
    "LargeImageSource",
    "MemoryImageSource",
    "QtImageSource",
    "TiffImageSource",
]
