"""Tests for UltralyticsProvider."""

from __future__ import annotations

import pytest

from anylabeling.platform.adapters.interfaces import (
    DatasetCapability,
    ExportCapability,
    InferenceCapability,
    RunParser,
    TrainCapability,
    ValCapability,
)
from anylabeling.platform.adapters.provider import AlgorithmProvider
from anylabeling.platform.adapters.registry import AlgorithmRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    AlgorithmRegistry.clear()
    yield
    AlgorithmRegistry.clear()


class TestUltralyticsProvider:
    def test_import_and_instantiate(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        assert p is not None
        assert isinstance(p, AlgorithmProvider)

    def test_has_correct_id(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        assert p.id == "ultralytics_yolo_detect"

    def test_all_capabilities_available(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        # Ultralytics supports all six capabilities
        assert isinstance(p.train_adapter, TrainCapability)
        assert isinstance(p.val_adapter, ValCapability)
        assert isinstance(p.export_adapter, ExportCapability)
        assert isinstance(p.inference_adapter, InferenceCapability)
        assert isinstance(p.dataset_adapter, DatasetCapability)
        assert isinstance(p.run_parser, RunParser)

    def test_support_bools_all_true(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        assert p.supports_training is True
        assert p.supports_validation is True
        assert p.supports_export is True
        assert p.supports_inference is True
        assert p.supports_dataset_build is True

    def test_capabilities_has_new_fields(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        caps = p.capabilities
        assert caps.supports_export is True
        assert "onnx" in caps.export_formats
        assert caps.supports_inference is True
        assert caps.supports_dataset_build is True

    def test_display_name(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        assert "Ultralytics" in p.display_name
        assert "YOLO" in p.display_name

    def test_task_families(self):
        from anylabeling.platform.adapters.ultralytics.provider import (
            UltralyticsProvider,
        )

        p = UltralyticsProvider()
        assert "detection_hbb" in p.task_families


class TestUltralyticsProviderRegistration:
    def test_provider_registered_via_init(self):
        """Importing ultralytics package should auto-register the provider."""
        import importlib

        import anylabeling.platform.adapters.ultralytics

        importlib.reload(anylabeling.platform.adapters.ultralytics)

        # The provider should be registered
        provider = AlgorithmRegistry.get_provider("ultralytics_yolo_detect")
        assert provider is not None
        assert provider.id == "ultralytics_yolo_detect"

    def test_capabilities_also_registered(self):
        import importlib

        import anylabeling.platform.adapters.ultralytics

        importlib.reload(anylabeling.platform.adapters.ultralytics)

        caps = AlgorithmRegistry.get("ultralytics_yolo_detect")
        assert caps is not None
        assert caps.adapter_id == "ultralytics_yolo_detect"


class TestUltralyticsInferenceAdapter:
    def test_import_and_instantiate(self):
        from anylabeling.platform.adapters.ultralytics.inference_adapter import (
            UltralyticsInferenceAdapter,
        )

        adapter = UltralyticsInferenceAdapter()
        assert isinstance(adapter, InferenceCapability)

    def test_get_infer_command_single_image(self):
        from anylabeling.platform.adapters.ultralytics.inference_adapter import (
            UltralyticsInferenceAdapter,
        )

        adapter = UltralyticsInferenceAdapter()
        cmd = adapter.get_infer_command(
            "model.pt",
            "/path/to/image.jpg",
            conf=0.5,
            iou=0.3,
        )
        assert isinstance(cmd, list)
        assert len(cmd) > 0
        # Should contain sys.executable as first element
        import sys

        assert cmd[0] == sys.executable

    def test_get_infer_command_batch(self):
        from anylabeling.platform.adapters.ultralytics.inference_adapter import (
            UltralyticsInferenceAdapter,
        )

        adapter = UltralyticsInferenceAdapter()
        cmd = adapter.get_infer_command(
            "model.pt",
            "/path/to/dir",
            is_batch=True,
        )
        assert isinstance(cmd, list)
        assert len(cmd) > 0

    def test_inference_param_schema(self):
        from anylabeling.platform.adapters.ultralytics.inference_adapter import (
            UltralyticsInferenceAdapter,
        )

        adapter = UltralyticsInferenceAdapter()
        schema = adapter.inference_param_schema()
        assert isinstance(schema, dict)
        # Should contain common inference params
        assert "conf" in schema or "confidence" in str(schema).lower()
