"""Tests for the Capability ABC classes in interfaces.py."""

from __future__ import annotations

import inspect

import pytest

from anylabeling.platform.adapters.interfaces import (
    DatasetCapability,
    ExportCapability,
    InferenceCapability,
    RunParser,
    TrainCapability,
    ValCapability,
)
from anylabeling.platform.domain.model import ModelArtifact
from anylabeling.platform.domain.run import MetricPoint


# ---------------------------------------------------------------------------
# Helpers — concrete subclasses for testing
# ---------------------------------------------------------------------------


class _TrainImpl(TrainCapability):
    def build_train_kwargs(self, params, data_path, output_dir) -> dict:
        return {}

    def get_train_command(self, model_path, kwargs) -> list[str]:
        return []

    def train_param_schema(self) -> dict:
        return {}


class _ValImpl(ValCapability):
    def build_val_kwargs(self, model_path, data_path, **params) -> dict:
        return {}

    def get_val_command(self, model_path, kwargs) -> list[str]:
        return []


class _ExportImpl(ExportCapability):
    def get_supported_formats(self) -> list[str]:
        return ["onnx"]

    def build_export_kwargs(self, model_path, output_dir, format, **params) -> dict:
        return {}

    def get_export_command(self, model_path, kwargs) -> list[str]:
        return []


class _InferenceImpl(InferenceCapability):
    def get_infer_command(self, model_path, image_source, *, is_batch=False, **params) -> list[str]:
        return []

    def inference_param_schema(self) -> dict:
        return {}


class _DatasetImpl(DatasetCapability):
    def adapt(self, build, task_spec) -> dict:
        return {}

    def write_config(self, build, task_spec) -> "Path":
        from pathlib import Path

        return Path("/tmp/config.yaml")

    def get_data_path(self, build) -> str:
        return "/tmp/data.yaml"


class _RunParserImpl(RunParser):
    def parse_train_results(self, output_dir) -> list[MetricPoint]:
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
# TrainCapability
# ---------------------------------------------------------------------------


class TestTrainCapability:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            TrainCapability()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        impl = _TrainImpl()
        assert impl is not None

    def test_has_abstract_build_train_kwargs(self):
        assert hasattr(TrainCapability, "build_train_kwargs")
        method = TrainCapability.__dict__["build_train_kwargs"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_get_train_command(self):
        assert hasattr(TrainCapability, "get_train_command")
        method = TrainCapability.__dict__["get_train_command"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_train_param_schema(self):
        assert hasattr(TrainCapability, "train_param_schema")
        method = TrainCapability.__dict__["train_param_schema"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_build_train_kwargs_signature(self):
        sig = inspect.signature(TrainCapability.build_train_kwargs)
        param_names = list(sig.parameters.keys())
        assert "params" in param_names
        assert "data_path" in param_names
        assert "output_dir" in param_names


# ---------------------------------------------------------------------------
# ValCapability
# ---------------------------------------------------------------------------


class TestValCapability:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ValCapability()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        impl = _ValImpl()
        assert impl is not None

    def test_has_abstract_build_val_kwargs(self):
        assert hasattr(ValCapability, "build_val_kwargs")
        method = ValCapability.__dict__["build_val_kwargs"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_get_val_command(self):
        assert hasattr(ValCapability, "get_val_command")
        method = ValCapability.__dict__["get_val_command"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_build_val_kwargs_accepts_variadic_kwargs(self):
        sig = inspect.signature(ValCapability.build_val_kwargs)
        param_names = list(sig.parameters.keys())
        assert "model_path" in param_names
        assert "data_path" in param_names
        # Should have **params
        assert any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )


# ---------------------------------------------------------------------------
# ExportCapability
# ---------------------------------------------------------------------------


class TestExportCapability:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ExportCapability()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        impl = _ExportImpl()
        assert impl is not None

    def test_has_abstract_get_supported_formats(self):
        assert hasattr(ExportCapability, "get_supported_formats")
        method = ExportCapability.__dict__["get_supported_formats"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_build_export_kwargs(self):
        assert hasattr(ExportCapability, "build_export_kwargs")
        method = ExportCapability.__dict__["build_export_kwargs"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_get_export_command(self):
        assert hasattr(ExportCapability, "get_export_command")
        method = ExportCapability.__dict__["get_export_command"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_save_export_artifacts_is_concrete_not_abstract(self):
        method = ExportCapability.__dict__["save_export_artifacts"]
        assert not getattr(method, "__isabstractmethod__", False)

    def test_save_export_artifacts_signature(self):
        sig = inspect.signature(ExportCapability.save_export_artifacts)
        param_names = list(sig.parameters.keys())
        assert "export_path" in param_names
        assert "model_path" in param_names
        assert "output_dir" in param_names
        assert "model_id" in param_names
        assert "labels" in param_names
        assert "run_id" in param_names

    def test_save_export_artifacts_default_impl_returns_model_artifact(self, tmp_path):
        impl = _ExportImpl()
        # Create a dummy export file
        export_file = tmp_path / "model.onnx"
        export_file.write_text("dummy")
        model_file = tmp_path / "model.pt"
        model_file.write_text("dummy")

        artifact = impl.save_export_artifacts(
            export_path=str(export_file),
            model_path=str(model_file),
            output_dir=str(tmp_path),
            model_id="test_model",
            labels=["cat", "dog"],
            run_id="run_001",
        )
        assert isinstance(artifact, ModelArtifact)
        assert artifact.id == "test_model"
        assert artifact.run_id == "run_001"
        assert artifact.format == "onnx"
        assert artifact.labels == ["cat", "dog"]


# ---------------------------------------------------------------------------
# InferenceCapability
# ---------------------------------------------------------------------------


class TestInferenceCapability:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            InferenceCapability()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        impl = _InferenceImpl()
        assert impl is not None

    def test_has_abstract_get_infer_command(self):
        assert hasattr(InferenceCapability, "get_infer_command")
        method = InferenceCapability.__dict__["get_infer_command"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_inference_param_schema(self):
        assert hasattr(InferenceCapability, "inference_param_schema")
        method = InferenceCapability.__dict__["inference_param_schema"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_get_infer_command_signature(self):
        sig = inspect.signature(InferenceCapability.get_infer_command)
        param_names = list(sig.parameters.keys())
        assert "model_path" in param_names
        assert "image_source" in param_names
        # Keyword-only is_batch
        params = list(sig.parameters.values())
        is_batch = sig.parameters.get("is_batch")
        assert is_batch is not None
        assert is_batch.kind == inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# DatasetCapability
# ---------------------------------------------------------------------------


class TestDatasetCapability:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            DatasetCapability()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        impl = _DatasetImpl()
        assert impl is not None

    def test_has_abstract_adapt(self):
        assert hasattr(DatasetCapability, "adapt")
        method = DatasetCapability.__dict__["adapt"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_write_config(self):
        assert hasattr(DatasetCapability, "write_config")
        method = DatasetCapability.__dict__["write_config"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_get_data_path(self):
        assert hasattr(DatasetCapability, "get_data_path")
        method = DatasetCapability.__dict__["get_data_path"]
        assert getattr(method, "__isabstractmethod__", False)


# ---------------------------------------------------------------------------
# RunParser
# ---------------------------------------------------------------------------


class TestRunParser:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            RunParser()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        impl = _RunParserImpl()
        assert impl is not None

    def test_has_abstract_parse_train_results(self):
        assert hasattr(RunParser, "parse_train_results")
        method = RunParser.__dict__["parse_train_results"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_parse_val_results(self):
        assert hasattr(RunParser, "parse_val_results")
        method = RunParser.__dict__["parse_val_results"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_find_best_epoch(self):
        assert hasattr(RunParser, "find_best_epoch")
        method = RunParser.__dict__["find_best_epoch"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_get_best_weight_path(self):
        assert hasattr(RunParser, "get_best_weight_path")
        method = RunParser.__dict__["get_best_weight_path"]
        assert getattr(method, "__isabstractmethod__", False)

    def test_has_abstract_get_last_weight_path(self):
        assert hasattr(RunParser, "get_last_weight_path")
        method = RunParser.__dict__["get_last_weight_path"]
        assert getattr(method, "__isabstractmethod__", False)
