"""AlgorithmProvider ABC — the top-level facade for a vision algorithm.

Each algorithm (Ultralytics YOLO, DETR, SAM, …) is represented by a
concrete :class:`AlgorithmProvider` subclass that composes 0-6 capability
adapters.  The provider declares *what* the algorithm can do and exposes
the adapters for each supported capability.

Capability properties default to ``None`` — a subclass only overrides the
properties for capabilities it actually provides.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anylabeling.platform.adapters.interfaces import (
        DatasetCapability,
        ExportCapability,
        InferenceCapability,
        RunParser,
        TrainCapability,
        ValCapability,
    )
    from anylabeling.platform.adapters.registry import AlgorithmCapabilities


class AlgorithmProvider(ABC):
    """Top-level provider for a vision algorithm.

    Subclasses must implement :attr:`id` and :attr:`capabilities`.
    They may optionally override any of the capability adapter properties
    (``train_adapter``, ``val_adapter``, ``export_adapter``,
    ``inference_adapter``, ``dataset_adapter``, ``run_parser``).
    """

    # ------------------------------------------------------------------
    # Required abstract properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for this algorithm adapter.

        Must match the ``adapter_id`` in :attr:`capabilities`.
        Example: ``"ultralytics_yolo_detect"``.
        """
        ...

    @property
    @abstractmethod
    def capabilities(self) -> AlgorithmCapabilities:
        """Immutable declaration of what this algorithm can do.

        Returns:
            :class:`~anylabeling.platform.adapters.registry.AlgorithmCapabilities`.
        """
        ...

    # ------------------------------------------------------------------
    # Capability adapters — default to None
    # ------------------------------------------------------------------

    @property
    def train_adapter(self) -> TrainCapability | None:
        """Return the :class:`TrainCapability` adapter, or ``None``."""
        return None

    @property
    def val_adapter(self) -> ValCapability | None:
        """Return the :class:`ValCapability` adapter, or ``None``."""
        return None

    @property
    def export_adapter(self) -> ExportCapability | None:
        """Return the :class:`ExportCapability` adapter, or ``None``."""
        return None

    @property
    def inference_adapter(self) -> InferenceCapability | None:
        """Return the :class:`InferenceCapability` adapter, or ``None``."""
        return None

    @property
    def dataset_adapter(self) -> DatasetCapability | None:
        """Return the :class:`DatasetCapability` adapter, or ``None``."""
        return None

    @property
    def run_parser(self) -> RunParser | None:
        """Return the :class:`RunParser` adapter, or ``None``."""
        return None

    # ------------------------------------------------------------------
    # Convenience queries
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        """Human-readable display name (delegates to capabilities)."""
        return self.capabilities.display_name

    @property
    def task_families(self) -> frozenset[str]:
        """Supported task families (delegates to capabilities)."""
        return self.capabilities.task_families

    @property
    def supports_training(self) -> bool:
        """Whether this algorithm supports training."""
        return self.train_adapter is not None

    @property
    def supports_validation(self) -> bool:
        """Whether this algorithm supports validation."""
        return self.val_adapter is not None

    @property
    def supports_export(self) -> bool:
        """Whether this algorithm supports model export."""
        return self.export_adapter is not None

    @property
    def supports_inference(self) -> bool:
        """Whether this algorithm supports inference."""
        return self.inference_adapter is not None

    @property
    def supports_dataset_build(self) -> bool:
        """Whether this algorithm supports dataset building."""
        return self.dataset_adapter is not None


__all__ = [
    "AlgorithmProvider",
]
