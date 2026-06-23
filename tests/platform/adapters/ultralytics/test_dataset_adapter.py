"""Tests for UltralyticsDatasetAdapter (M3.2).

Coverage:
    1. adapt() returns correct keys
    2. nc matches len(task_spec.labels)
    3. names dict maps indices to label names
    4. write_data_yaml creates a valid YAML file
    5. Written YAML can be re-read and matches adapt() output
    6. get_data_path returns absolute path string
    7. test split included when images/test/ directory exists
"""

from __future__ import annotations

from pathlib import Path

import yaml

from anylabeling.platform.adapters.ultralytics.dataset_adapter import (
    UltralyticsDatasetAdapter,
)
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.task import LabelClass, TaskSpec


# ============================================================================
# Helpers
# ============================================================================


def _make_task_spec() -> TaskSpec:
    """Create a minimal detection task spec with two classes."""
    return TaskSpec(
        id="task_001",
        family="detection_hbb",
        labels=(
            LabelClass(id=0, name="defect"),
            LabelClass(id=1, name="scratch"),
        ),
        annotation_schema="xanylabeling_v4",
        primary_metric="mAP@0.5",
    )


def _make_task_spec_single_class() -> TaskSpec:
    """Create a minimal classification task spec with one class."""
    return TaskSpec(
        id="task_cls_001",
        family="classification",
        labels=(LabelClass(id=0, name="ok"),),
        annotation_schema="xanylabeling_v4",
        primary_metric="accuracy",
    )


def _make_build(output_path: str) -> DatasetBuild:
    """Create a minimal DatasetBuild pointing at output_path."""
    return DatasetBuild(
        id="build_001",
        task_spec_id="task_001",
        source_asset_manifest_hash="abc123",
        annotation_manifest_hash="def456",
        split_seed=42,
        split_strategy="random_by_asset",
        output_path=output_path,
    )


def _setup_build_dir(base: Path) -> Path:
    """Create the expected directory structure under a build output path."""
    build_dir = base / "build_001"
    for split in ("train", "val", "test"):
        (build_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (build_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
    return build_dir


# ============================================================================
# Fixture
# ============================================================================


class TestAdaptReturnsCorrectKeys:
    def test_adapt_returns_all_required_keys(self, tmp_path: Path):
        """adapt() returns dict with path, train, val, nc, names keys."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert "path" in data
        assert "train" in data
        assert "val" in data
        assert "test" in data  # test dir exists
        assert "nc" in data
        assert "names" in data

    def test_adapt_path_is_absolute(self, tmp_path: Path):
        """The path value should be an absolute path string."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert Path(data["path"]).is_absolute()

    def test_adapt_train_val_are_relative(self, tmp_path: Path):
        """train and val should be relative paths."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert data["train"] == "images/train"
        assert data["val"] == "images/val"


# ============================================================================
# nc and names tests
# ============================================================================


class TestAdaptNcMatchesTaskSpecLabels:
    def test_nc_matches_number_of_labels(self, tmp_path: Path):
        """nc equals len(task_spec.labels)."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert data["nc"] == 2

    def test_nc_with_single_class(self, tmp_path: Path):
        """nc should be 1 for single-class task spec."""
        task_spec = _make_task_spec_single_class()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert data["nc"] == 1


class TestAdaptNamesMatchTaskSpec:
    def test_names_dict_maps_indices_to_label_names(self, tmp_path: Path):
        """names dict maps indices to label names."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert data["names"][0] == "defect"
        assert data["names"][1] == "scratch"

    def test_names_dict_length_matches_nc(self, tmp_path: Path):
        """len(names) should equal nc."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert len(data["names"]) == data["nc"]


# ============================================================================
# write_data_yaml tests
# ============================================================================


class TestWriteDataYamlCreatesFile:
    def test_write_data_yaml_creates_file(self, tmp_path: Path):
        """write_data_yaml creates a valid YAML file at the correct location."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        result_path = adapter.write_data_yaml(build, task_spec)

        assert result_path.exists()
        assert result_path.is_file()
        assert result_path.name == "data.yaml"
        assert result_path.parent == build_dir

    def test_yaml_file_is_non_empty(self, tmp_path: Path):
        """Written YAML file should not be empty."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        result_path = adapter.write_data_yaml(build, task_spec)

        content = result_path.read_text(encoding="utf-8")
        assert len(content) > 0


class TestWrittenYamlContentParsesCorrectly:
    def test_written_yaml_can_be_re_read(self, tmp_path: Path):
        """Written YAML can be re-read and matches adapt() output."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()

        # Get expected data via adapt
        expected = adapter.adapt(build, task_spec)

        # Write and re-read
        yaml_path = adapter.write_data_yaml(build, task_spec)
        with open(yaml_path, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f)

        assert parsed["path"] == expected["path"]
        assert parsed["train"] == expected["train"]
        assert parsed["val"] == expected["val"]
        assert parsed["nc"] == expected["nc"]
        assert parsed["names"] == expected["names"]

    def test_written_yaml_contains_expected_keys(self, tmp_path: Path):
        """Re-read YAML should have all required keys."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        yaml_path = adapter.write_data_yaml(build, task_spec)

        with open(yaml_path, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f)

        assert "path" in parsed
        assert "train" in parsed
        assert "val" in parsed
        assert "test" in parsed
        assert "nc" in parsed
        assert "names" in parsed


# ============================================================================
# get_data_path tests
# ============================================================================


class TestGetDataPathReturnsAbsolutePath:
    def test_get_data_path_returns_string(self, tmp_path: Path):
        """get_data_path returns a string."""
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        result = adapter.get_data_path(build)

        assert isinstance(result, str)

    def test_get_data_path_is_absolute(self, tmp_path: Path):
        """get_data_path returns an absolute path string."""
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        result = adapter.get_data_path(build)

        assert Path(result).is_absolute()

    def test_get_data_path_ends_with_data_yaml(self, tmp_path: Path):
        """get_data_path should end with data.yaml."""
        build_dir = _setup_build_dir(tmp_path)
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        result = adapter.get_data_path(build)

        assert Path(result).name == "data.yaml"


# ============================================================================
# test split tests
# ============================================================================


class TestTestSplitIncludedWhenImagesTestExists:
    def test_test_key_present_when_test_dir_exists(self, tmp_path: Path):
        """data dict includes 'test' key when images/test/ directory exists."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)  # creates images/test/
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert "test" in data
        assert data["test"] == "images/test"

    def test_test_key_absent_when_test_dir_missing(self, tmp_path: Path):
        """data dict does NOT include 'test' when images/test/ does not exist."""
        task_spec = _make_task_spec()

        # Create build dir WITHOUT test subdirectory
        build_dir = tmp_path / "build_no_test"
        for split in ("train", "val"):
            (build_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (build_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert "test" not in data

    def test_test_key_present_when_all_splits_exist(self, tmp_path: Path):
        """All three splits (train/val/test) produce all keys."""
        task_spec = _make_task_spec()
        build_dir = _setup_build_dir(tmp_path)  # creates all three
        build = _make_build(str(build_dir))

        adapter = UltralyticsDatasetAdapter()
        data = adapter.adapt(build, task_spec)

        assert data["train"] == "images/train"
        assert data["val"] == "images/val"
        assert data["test"] == "images/test"
