"""Tests for the AlgorithmProvider ABC."""

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
from anylabeling.platform.adapters.registry import (
    AlgorithmCapabilities,
)


# ---------------------------------------------------------------------------
# Concrete provider implementations for testing
# ---------------------------------------------------------------------------


class _FullProvider(AlgorithmProvider):
    """A provider that implements all capabilities."""

    @property
    def id(self) -> str:
        return "full_provider"

    @property
    def capabilities(self) -> AlgorithmCapabilities:
        return AlgorithmCapabilities(
            adapter_id="full_provider",
            display_name="Full Provider",
            task_families=frozenset({"detection_hbb"}),
            supports_training=True,
            supports_validation=True,
            supports_export_onnx=True,
            supports_sliced_inference=False,
        )

    @property
    def train_adapter(self):
        return _FakeTrain()

    @property
    def val_adapter(self):
        return _FakeVal()

    @property
    def export_adapter(self):
        return _FakeExport()

    @property
    def inference_adapter(self):
        return _FakeInference()

    @property
    def dataset_adapter(self):
        return _FakeDataset()

    @property
    def run_parser(self):
        return _FakeRunParser()


class _MinimalProvider(AlgorithmProvider):
    """A provider that only supports inference (e.g., SAM)."""

    @property
    def id(self) -> str:
        return "minimal_provider"

    @property
    def capabilities(self) -> AlgorithmCapabilities:
        return AlgorithmCapabilities(
            adapter_id="minimal_provider",
            display_name="Minimal Provider",
            task_families=frozenset({"instance_segmentation"}),
            supports_training=False,
            supports_validation=False,
            supports_export_onnx=False,
            supports_sliced_inference=False,
        )

    @property
    def inference_adapter(self):
        return _FakeInference()


class _EmptyProvider(AlgorithmProvider):
    """A provider with no capabilities at all (bare minimum override)."""

    @property
    def id(self) -> str:
        return "empty"

    @property
    def capabilities(self) -> AlgorithmCapabilities:
        return AlgorithmCapabilities(
            adapter_id="empty",
            display_name="Empty",
            task_families=frozenset(),
            supports_training=False,
            supports_validation=False,
            supports_export_onnx=False,
            supports_sliced_inference=False,
        )


# ---------------------------------------------------------------------------
# Fake adapter implementations
# ---------------------------------------------------------------------------


class _FakeTrain(TrainCapability):
    def build_train_kwargs(self, params, data_path, output_dir) -> dict:
        return {}

    def get_train_command(self, model_path, kwargs) -> list[str]:
        return []

    def train_param_schema(self) -> dict:
        return {}


class _FakeVal(ValCapability):
    def build_val_kwargs(self, model_path, data_path, **params) -> dict:
        return {}

    def get_val_command(self, model_path, kwargs) -> list[str]:
        return []


class _FakeExport(ExportCapability):
    def get_supported_formats(self) -> list[str]:
        return ["onnx"]

    def build_export_kwargs(self, model_path, output_dir, format, **params) -> dict:
        return {}

    def get_export_command(self, model_path, kwargs) -> list[str]:
        return []


class _FakeInference(InferenceCapability):
    def get_infer_command(self, model_path, image_source, *, is_batch=False, **params) -> list[str]:
        return []

    def inference_param_schema(self) -> dict:
        return {}


class _FakeDataset(DatasetCapability):
    def adapt(self, build, task_spec) -> dict:
        return {}

    def write_config(self, build, task_spec):
        from pathlib import Path

        return Path("/tmp/dummy.yaml")

    def get_data_path(self, build) -> str:
        return "/tmp/dummy.yaml"


class _FakeRunParser(RunParser):
    def parse_train_results(self, output_dir) -> list:
        return []

    def parse_val_results(self, output_dir) -> dict | None:
        return None

    def find_best_epoch(self, metrics) -> dict | None:
        return None

    def get_best_weight_path(self, output_dir) -> str | None:
        return None

    def get_last_weight_path(self, output_dir) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAlgorithmProviderAbstract:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            AlgorithmProvider()  # type: ignore[abstract]

    def test_id_is_abstract_property(self):
        prop = AlgorithmProvider.__dict__["id"]
        assert getattr(prop.fget, "__isabstractmethod__", False)

    def test_capabilities_is_abstract_property(self):
        prop = AlgorithmProvider.__dict__["capabilities"]
        assert getattr(prop.fget, "__isabstractmethod__", False)


class TestFullProvider:
    def test_instantiates(self):
        p = _FullProvider()
        assert p.id == "full_provider"

    def test_all_adapters_available(self):
        p = _FullProvider()
        assert p.train_adapter is not None
        assert p.val_adapter is not None
        assert p.export_adapter is not None
        assert p.inference_adapter is not None
        assert p.dataset_adapter is not None
        assert p.run_parser is not None

    def test_support_bools(self):
        p = _FullProvider()
        assert p.supports_training is True
        assert p.supports_validation is True
        assert p.supports_export is True
        assert p.supports_inference is True
        assert p.supports_dataset_build is True

    def test_display_name_delegates(self):
        p = _FullProvider()
        assert p.display_name == "Full Provider"

    def test_task_families_delegates(self):
        p = _FullProvider()
        assert p.task_families == frozenset({"detection_hbb"})

    def test_capabilities_returns_correct_type(self):
        p = _FullProvider()
        caps = p.capabilities
        assert isinstance(caps, AlgorithmCapabilities)


class TestMinimalProvider:
    def test_instantiates(self):
        p = _MinimalProvider()
        assert p.id == "minimal_provider"

    def test_only_inference_available(self):
        p = _MinimalProvider()
        assert p.train_adapter is None
        assert p.val_adapter is None
        assert p.export_adapter is None
        assert p.inference_adapter is not None
        assert p.dataset_adapter is None
        assert p.run_parser is None

    def test_support_bools(self):
        p = _MinimalProvider()
        assert p.supports_training is False
        assert p.supports_validation is False
        assert p.supports_export is False
        assert p.supports_inference is True
        assert p.supports_dataset_build is False


class TestEmptyProvider:
    def test_no_adapters(self):
        p = _EmptyProvider()
        assert p.train_adapter is None
        assert p.val_adapter is None
        assert p.export_adapter is None
        assert p.inference_adapter is None
        assert p.dataset_adapter is None
        assert p.run_parser is None

    def test_all_support_bools_false(self):
        p = _EmptyProvider()
        assert p.supports_training is False
        assert p.supports_validation is False
        assert p.supports_export is False
        assert p.supports_inference is False
        assert p.supports_dataset_build is False
