"""Tests for AlgorithmRegistry and AlgorithmCapabilities."""

from __future__ import annotations

import pytest

from anylabeling.platform.adapters.registry import (
    AlgorithmCapabilities,
    AlgorithmRegistry,
)
from anylabeling.platform.adapters.provider import AlgorithmProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cap(
    adapter_id: str,
    families: frozenset[str],
    *,
    supports_training: bool = True,
    supports_validation: bool = True,
    supports_export: bool = True,
    export_formats: frozenset[str] | None = None,
    supports_inference: bool = True,
    supports_dataset_build: bool = True,
) -> AlgorithmCapabilities:
    if export_formats is None:
        export_formats = frozenset({"onnx"})
    return AlgorithmCapabilities(
        adapter_id=adapter_id,
        display_name="Test",
        task_families=families,
        supports_training=supports_training,
        supports_validation=supports_validation,
        supports_export=supports_export,
        export_formats=export_formats,
        supports_inference=supports_inference,
        supports_dataset_build=supports_dataset_build,
        supports_sliced_inference=False,
    )


def _make_provider(
    adapter_id: str,
    families: frozenset[str],
    *,
    supports_training: bool = True,
    supports_validation: bool = True,
    supports_export: bool = True,
    export_formats: frozenset[str] | None = None,
    supports_inference: bool = True,
    supports_dataset_build: bool = True,
) -> AlgorithmProvider:
    if export_formats is None:
        export_formats = frozenset({"onnx"})

    caps = AlgorithmCapabilities(
        adapter_id=adapter_id,
        display_name=f"Provider {adapter_id}",
        task_families=families,
        supports_training=supports_training,
        supports_validation=supports_validation,
        supports_export=supports_export,
        export_formats=export_formats,
        supports_inference=supports_inference,
        supports_dataset_build=supports_dataset_build,
        supports_sliced_inference=False,
    )

    class _P(AlgorithmProvider):
        @property
        def id(self) -> str:
            return adapter_id

        @property
        def capabilities(self):
            return caps

    return _P()


@pytest.fixture(autouse=True)
def _clear_registry():
    """Ensure every test starts with a clean registry."""
    AlgorithmRegistry.clear()
    yield
    AlgorithmRegistry.clear()


# ---------------------------------------------------------------------------
# AlgorithmCapabilities — new fields
# ---------------------------------------------------------------------------


class TestCapabilitiesNewFields:
    def test_export_formats_field(self):
        caps = _make_cap("a", frozenset({"detection_hbb"}), export_formats=frozenset({"onnx", "tensorrt"}))
        assert caps.export_formats == frozenset({"onnx", "tensorrt"})

    def test_export_formats_default_empty(self):
        caps = AlgorithmCapabilities(
            adapter_id="a",
            display_name="Test",
            task_families=frozenset(),
            supports_training=False,
            supports_validation=False,
            supports_export=False,
            supports_inference=False,
            supports_dataset_build=False,
            supports_sliced_inference=False,
        )
        assert caps.export_formats == frozenset()

    def test_supports_export_field(self):
        caps = _make_cap("a", frozenset({"detection_hbb"}), supports_export=True)
        assert caps.supports_export is True

    def test_supports_inference_field(self):
        caps = _make_cap("a", frozenset({"detection_hbb"}), supports_inference=True)
        assert caps.supports_inference is True

    def test_supports_inference_default(self):
        caps = AlgorithmCapabilities(
            adapter_id="a",
            display_name="Test",
            task_families=frozenset(),
            supports_training=False,
            supports_validation=False,
            supports_export=False,
            supports_dataset_build=False,
            supports_sliced_inference=False,
        )
        assert caps.supports_inference is False

    def test_supports_dataset_build_field(self):
        caps = _make_cap("a", frozenset({"detection_hbb"}), supports_dataset_build=True)
        assert caps.supports_dataset_build is True

    def test_supports_dataset_build_default(self):
        caps = AlgorithmCapabilities(
            adapter_id="a",
            display_name="Test",
            task_families=frozenset(),
            supports_training=False,
            supports_validation=False,
            supports_export=False,
            supports_inference=False,
            supports_sliced_inference=False,
        )
        assert caps.supports_dataset_build is False

    def test_supports_export_onnx_deprecated_field_still_works(self):
        """Backward compat: supports_export_onnx field is retained."""
        caps = AlgorithmCapabilities(
            adapter_id="a",
            display_name="Test",
            task_families=frozenset({"detection_hbb"}),
            supports_training=True,
            supports_validation=True,
            supports_export=True,
            supports_inference=True,
            supports_dataset_build=True,
            supports_sliced_inference=False,
            supports_export_onnx=True,
        )
        assert caps.supports_export_onnx is True


# ---------------------------------------------------------------------------
# AlgorithmCapabilities — frozen
# ---------------------------------------------------------------------------


class TestCapabilitiesFrozen:
    def test_capabilities_are_frozen(self):
        cap = _make_cap("x", frozenset({"pose"}))
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            cap.supports_training = False  # type: ignore[misc]

    def test_task_families_is_frozenset(self):
        cap = _make_cap("x", frozenset({"pose"}))
        with pytest.raises(AttributeError):
            cap.task_families.add("detection_hbb")  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# AlgorithmRegistry — register provider
# ---------------------------------------------------------------------------


class TestRegisterProvider:
    def test_register_provider_stores_capabilities(self):
        p = _make_provider("detect", frozenset({"detection_hbb"}))
        AlgorithmRegistry.register(p)
        caps = AlgorithmRegistry.get("detect")
        assert caps.adapter_id == "detect"
        assert caps.task_families == frozenset({"detection_hbb"})

    def test_register_provider_stores_provider(self):
        p = _make_provider("detect", frozenset({"detection_hbb"}))
        AlgorithmRegistry.register(p)
        retrieved = AlgorithmRegistry.get_provider("detect")
        assert retrieved is p
        assert retrieved.id == "detect"

    def test_register_legacy_capabilities_still_works(self):
        """Backward compat: AlgorithmRegistry.register(capabilities) still works."""
        cap = _make_cap("legacy", frozenset({"classification"}))
        AlgorithmRegistry.register(cap)
        assert AlgorithmRegistry.get("legacy") is cap


class TestRegisterAndGet:
    def test_get_returns_capabilities(self):
        p = _make_provider("test_algo", frozenset({"classification"}))
        AlgorithmRegistry.register(p)
        caps = AlgorithmRegistry.get("test_algo")
        assert isinstance(caps, AlgorithmCapabilities)
        assert caps.adapter_id == "test_algo"

    def test_get_missing_raises_keyerror(self):
        with pytest.raises(KeyError):
            AlgorithmRegistry.get("nonexistent")

    def test_get_provider_missing_raises_keyerror(self):
        with pytest.raises(KeyError):
            AlgorithmRegistry.get_provider("nonexistent")


class TestListAll:
    def test_list_all_empty(self):
        assert AlgorithmRegistry.list_all() == []

    def test_list_all_after_register(self):
        AlgorithmRegistry.register(_make_provider("a", frozenset({"pose"})))
        AlgorithmRegistry.register(_make_provider("b", frozenset({"detection_hbb"})))
        assert len(AlgorithmRegistry.list_all()) == 2


class TestForTask:
    def test_for_task_filters_by_family(self):
        AlgorithmRegistry.register(_make_provider("a", frozenset({"classification"})))
        AlgorithmRegistry.register(_make_provider("b", frozenset({"detection_hbb"})))
        AlgorithmRegistry.register(
            _make_provider("c", frozenset({"classification", "detection_hbb"}))
        )

        results = AlgorithmRegistry.for_task("classification")
        ids = {c.adapter_id for c in results}
        assert ids == {"a", "c"}

    def test_for_task_detect_returns_detect_only(self):
        AlgorithmRegistry.register(_make_provider("cls", frozenset({"classification"})))
        AlgorithmRegistry.register(_make_provider("det", frozenset({"detection_hbb"})))

        results = AlgorithmRegistry.for_task("detection_hbb")
        ids = {c.adapter_id for c in results}
        assert ids == {"det"}

    def test_for_task_unknown_family_returns_empty(self):
        AlgorithmRegistry.register(_make_provider("a", frozenset({"classification"})))
        assert AlgorithmRegistry.for_task("unknown") == []

    def test_for_task_providers_returns_providers(self):
        p = _make_provider("det", frozenset({"detection_hbb"}))
        AlgorithmRegistry.register(p)

        providers = AlgorithmRegistry.for_task_providers("detection_hbb")
        assert len(providers) == 1
        assert providers[0] is p


class TestRegistryClear:
    def test_registry_clear(self):
        AlgorithmRegistry.register(_make_provider("a", frozenset({"pose"})))
        assert len(AlgorithmRegistry.list_all()) == 1
        AlgorithmRegistry.clear()
        assert AlgorithmRegistry.list_all() == []
        # Providers should also be cleared
        with pytest.raises(KeyError):
            AlgorithmRegistry.get_provider("a")


class TestUltralyticsRegistration:
    def test_list_all_returns_5_algorithms(self):
        # Trigger the side-effect import that registers 5 YOLO algorithms.
        # Use reload to ensure module-level code re-executes after
        # the autouse fixture cleared the registry.
        import importlib

        import anylabeling.platform.adapters.ultralytics.capabilities

        importlib.reload(anylabeling.platform.adapters.ultralytics.capabilities)

        all_caps = AlgorithmRegistry.list_all()
        assert len(all_caps) == 5

        expected_ids = {
            "ultralytics_yolo_classify",
            "ultralytics_yolo_detect",
            "ultralytics_yolo_obb",
            "ultralytics_yolo_segment",
            "ultralytics_yolo_pose",
        }
        actual_ids = {c.adapter_id for c in all_caps}
        assert actual_ids == expected_ids
