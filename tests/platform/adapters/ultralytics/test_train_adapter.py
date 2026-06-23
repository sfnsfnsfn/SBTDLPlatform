"""Tests for UltralyticsTrainAdapter and TrainRequest.

Coverage:
    1. build_train_kwargs contains all required keys
    2. build_train_kwargs respects request values (epochs, data, project)
    3. TrainRequest default values are sensible
    4. Edge cases
"""

from __future__ import annotations

import pytest

from anylabeling.platform.adapters.ultralytics.train_adapter import (
    TrainRequest,
    UltralyticsTrainAdapter,
)
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.task import (
    LabelClass,
    TaskSpec,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_task_spec() -> TaskSpec:
    """A minimal detection task spec for testing."""
    return TaskSpec(
        id="task_det_001",
        family="detection_hbb",
        labels=(
            LabelClass(id=0, name="cat"),
            LabelClass(id=1, name="dog"),
        ),
        annotation_schema="yolo_bbox",
        primary_metric="mAP50-95",
    )


@pytest.fixture
def sample_dataset_build() -> DatasetBuild:
    """A minimal dataset build for testing."""
    return DatasetBuild(
        id="build_abc123",
        task_spec_id="task_det_001",
        source_asset_manifest_hash="abc",
        annotation_manifest_hash="def",
        split_seed=42,
        split_strategy="random_by_asset",
        output_path="/tmp/dataset_builds/build_abc123",
    )


@pytest.fixture
def sample_request(
    sample_task_spec: TaskSpec,
    sample_dataset_build: DatasetBuild,
) -> TrainRequest:
    """A TrainRequest with sensible defaults."""
    return TrainRequest(
        task_spec=sample_task_spec,
        dataset_build=sample_dataset_build,
        base_model="yolo11n.pt",
        epochs=100,
    )


@pytest.fixture
def adapter() -> UltralyticsTrainAdapter:
    """Fresh UltralyticsTrainAdapter instance."""
    return UltralyticsTrainAdapter()


# ============================================================================
# 1. build_train_kwargs — key presence
# ============================================================================


class TestBuildTrainKwargsRequiredKeys:
    """Verify that build_train_kwargs returns all expected top-level keys."""

    REQUIRED_KEYS = [
        "data",
        "epochs",
        "batch",
        "imgsz",
        "workers",
        "device",
        "seed",
        # Optimizer
        "lr0",
        "lrf",
        "momentum",
        "weight_decay",
        "warmup_epochs",
        "optimizer",
        "cos_lr",
        "amp",
        # Augmentation
        "hsv_h",
        "hsv_s",
        "hsv_v",
        "degrees",
        "translate",
        "scale",
        "shear",
        "perspective",
        "fliplr",
        "mosaic",
        "mixup",
        "copy_paste",
        "close_mosaic",
        # Loss
        "box",
        "cls",
        "dfl",
        "pose",
        "kobj",
        # Save
        "project",
        "name",
        "exist_ok",
        "save_period",
        "plots",
        "val",
        "save",
    ]

    def test_all_required_keys_present(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        """Every required key must be in the returned kwargs dict."""
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/data/data.yaml", output_dir="/runs/test"
        )
        for key in self.REQUIRED_KEYS:
            assert key in kwargs, f"Missing key: {key}"


# ============================================================================
# 2. build_train_kwargs — value propagation
# ============================================================================


class TestBuildTrainKwargsValues:
    """Verify that request values are correctly propagated to kwargs."""

    def test_data_path_matches_input(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        kwargs = adapter.build_train_kwargs(
            sample_request,
            data_yaml="/path/to/data.yaml",
            output_dir="/output/dir",
        )
        assert kwargs["data"] == "/path/to/data.yaml"

    def test_project_set_to_output_dir(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        kwargs = adapter.build_train_kwargs(
            sample_request,
            data_yaml="/data.yaml",
            output_dir="/output/dir",
        )
        assert kwargs["project"] == "/output/dir"

    def test_epochs_match_request(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.epochs = 200
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["epochs"] == 200

    def test_batch_match_request(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.batch = 64
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["batch"] == 64

    def test_device_match_request(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.device = "cpu"
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["device"] == "cpu"

    def test_name_is_always_train(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["name"] == "train"

    def test_exist_ok_is_true(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["exist_ok"] is True

    def test_optimizer_params_propagated(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.optimizer = "SGD"
        sample_request.lr0 = 0.001
        sample_request.momentum = 0.9
        sample_request.cos_lr = True
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["optimizer"] == "SGD"
        assert kwargs["lr0"] == 0.001
        assert kwargs["momentum"] == 0.9
        assert kwargs["cos_lr"] is True

    def test_augmentation_params_propagated(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.mosaic = 0.5
        sample_request.mixup = 0.2
        sample_request.hsv_h = 0.02
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["mosaic"] == 0.5
        assert kwargs["mixup"] == 0.2
        assert kwargs["hsv_h"] == 0.02

    def test_loss_params_propagated(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.box = 7.0
        sample_request.cls = 0.3
        sample_request.dfl = 1.0
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["box"] == 7.0
        assert kwargs["cls"] == 0.3
        assert kwargs["dfl"] == 1.0

    def test_save_params_propagated(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.save_period = 10
        sample_request.plots = False
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["save_period"] == 10
        assert kwargs["plots"] is False


# ============================================================================
# 3. TrainRequest defaults
# ============================================================================


class TestTrainRequestDefaults:
    """Verify that TrainRequest default values are sensible."""

    def test_epochs_default_is_200(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.epochs == 200

    def test_batch_default_is_32(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.batch == 32

    def test_imgsz_default_is_640(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.imgsz == 640

    def test_lr0_default_is_0_01(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.lr0 == 0.01

    def test_seed_default_is_42(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.seed == 42

    def test_mosaic_default_is_1_0(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.mosaic == 1.0

    def test_val_and_save_default_true(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.val is True
        assert req.save is True

    def test_plots_default_true(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.plots is True

    def test_workers_default_is_8(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.workers == 8

    def test_device_default_is_0(
        self,
        sample_task_spec: TaskSpec,
        sample_dataset_build: DatasetBuild,
    ):
        req = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
        )
        assert req.device == "0"


# ============================================================================
# 4. Edge cases
# ============================================================================


class TestEdgeCases:
    def test_zero_epochs(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.epochs = 0
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        assert kwargs["epochs"] == 0

    def test_empty_base_model(
        self,
        adapter: UltralyticsTrainAdapter,
        sample_request: TrainRequest,
    ):
        sample_request.base_model = ""
        kwargs = adapter.build_train_kwargs(
            sample_request, data_yaml="/d.yaml", output_dir="/o"
        )
        # build_train_kwargs does not include model path — it's separate
        assert "model" not in kwargs


__all__: list[str] = []
