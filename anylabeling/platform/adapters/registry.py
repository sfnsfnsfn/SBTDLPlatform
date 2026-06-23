"""Algorithm registry for registering and querying vision algorithm capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anylabeling.platform.adapters.provider import AlgorithmProvider


@dataclass(frozen=True)
class AlgorithmCapabilities:
    """Immutable declaration of what a vision algorithm can do."""

    adapter_id: str
    display_name: str
    task_families: frozenset[str]
    supports_training: bool
    supports_validation: bool

    # New granular fields
    supports_export: bool = False
    export_formats: frozenset[str] = field(default_factory=frozenset)
    supports_inference: bool = False
    supports_dataset_build: bool = False

    # Deprecated — kept for backward compatibility
    supports_export_onnx: bool = False
    supports_sliced_inference: bool = False


class AlgorithmRegistry:
    """Registry of available vision algorithms.

    Algorithms register their capabilities once at import time.
    The registry can then be queried by adapter_id or task family.
    """

    _algorithms: dict[str, AlgorithmCapabilities] = {}
    _providers: dict[str, AlgorithmProvider] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @classmethod
    def register(
        cls,
        item: AlgorithmCapabilities | AlgorithmProvider,
    ) -> None:
        """Register an algorithm.

        Accepts either an :class:`AlgorithmCapabilities` (legacy) or an
        :class:`AlgorithmProvider`.  When a provider is given, its
        capabilities are extracted and registered automatically.
        """
        from anylabeling.platform.adapters.provider import AlgorithmProvider

        if isinstance(item, AlgorithmProvider):
            provider: AlgorithmProvider = item
            caps: AlgorithmCapabilities = provider.capabilities
            cls._providers[caps.adapter_id] = provider
            cls._algorithms[caps.adapter_id] = caps
        else:
            cls._algorithms[item.adapter_id] = item

    # ------------------------------------------------------------------
    # Lookup — capabilities
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, adapter_id: str) -> AlgorithmCapabilities:
        """Get capabilities by adapter_id. Raises KeyError if not found."""
        return cls._algorithms[adapter_id]

    @classmethod
    def get_provider(cls, adapter_id: str) -> AlgorithmProvider:
        """Get the :class:`AlgorithmProvider` by adapter_id.

        Raises KeyError if no provider was registered for this id.
        """
        if adapter_id not in cls._providers:
            raise KeyError(adapter_id)
        return cls._providers[adapter_id]

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    @classmethod
    def list_all(cls) -> list[AlgorithmCapabilities]:
        """List all registered algorithm capabilities."""
        return list(cls._algorithms.values())

    @classmethod
    def list_providers(cls) -> list[AlgorithmProvider]:
        """List all registered algorithm providers."""
        return list(cls._providers.values())

    # ------------------------------------------------------------------
    # Query by task family
    # ------------------------------------------------------------------

    @classmethod
    def for_task(cls, task_family: str) -> list[AlgorithmCapabilities]:
        """List capabilities that support the given task family."""
        return [
            cap
            for cap in cls._algorithms.values()
            if task_family in cap.task_families
        ]

    @classmethod
    def for_task_providers(cls, task_family: str) -> list[AlgorithmProvider]:
        """List providers that support the given task family."""
        return [
            provider
            for provider in cls._providers.values()
            if task_family in provider.capabilities.task_families
        ]

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._algorithms.clear()
        cls._providers.clear()


__all__ = [
    "AlgorithmCapabilities",
    "AlgorithmRegistry",
]
