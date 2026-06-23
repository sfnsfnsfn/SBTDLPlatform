"""Ultralytics adapter for the vision platform."""

from __future__ import annotations

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.dataset_adapter import (
    UltralyticsDatasetAdapter,
)
from anylabeling.platform.adapters.ultralytics.export_adapter import (
    UltralyticsExportAdapter,
)
from anylabeling.platform.adapters.ultralytics.inference_adapter import (
    UltralyticsInferenceAdapter,
)
from anylabeling.platform.adapters.ultralytics.val_adapter import (
    UltralyticsValAdapter,
)

# Import capabilities to register the legacy algorithm records.
import anylabeling.platform.adapters.ultralytics.capabilities  # noqa: F401

# Register UltralyticsProvider
from anylabeling.platform.adapters.ultralytics.provider import (  # noqa: E402
    UltralyticsProvider,
)

AlgorithmRegistry.register(UltralyticsProvider())

__all__ = [
    "UltralyticsDatasetAdapter",
    "UltralyticsExportAdapter",
    "UltralyticsInferenceAdapter",
    "UltralyticsProvider",
    "UltralyticsValAdapter",
]
