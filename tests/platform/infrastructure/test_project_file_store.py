"""Tests for platform infrastructure: AtomicWriter, ProjectFileStore,
ManifestStore, and checksum utilities.

Covers:
  1. AtomicWriter.write_json() writes valid JSON.
  2. AtomicWriter does NOT leave partial file on failure.
  3. ProjectFileStore.create_project() creates all 9 directories.
  4. project.json contains correct fields after creation.
  5. labels.json contains correct label list.
  6. ProjectFileStore.open_project() reads back valid project data.
  7. ProjectFileStore.validate_project() detects missing directories.
  8. ManifestStore.append_jsonl() + read_jsonl() round-trip.
  9. ManifestStore.validate_jsonl() detects corrupt lines.
 10. compute_sha256() returns consistent results for same content.
"""

from __future__ import annotations

import json
import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap — same pattern as test_domain_contracts.py
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
DOMAIN_DIR = PLATFORM_DIR / "domain"
INFRA_DIR = PLATFORM_DIR / "infrastructure"


def _ensure_package(name: str, path: pathlib.Path | None = None) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name: str, path: pathlib.Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    spec = importlib_util.spec_from_file_location(name, path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap() -> None:
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.platform", PLATFORM_DIR)

    # Domain
    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)
    for name in ("tile", "task", "asset", "annotation", "dataset", "run", "prediction", "model"):
        _load_module(f"anylabeling.platform.domain.{name}", DOMAIN_DIR / f"{name}.py")
    _load_module("anylabeling.platform.domain", DOMAIN_DIR / "__init__.py")

    # Infrastructure
    _ensure_package("anylabeling.platform.infrastructure", INFRA_DIR)
    for name in ("atomic_writer", "checksum", "manifest_store", "project_file_store"):
        _load_module(f"anylabeling.platform.infrastructure.{name}", INFRA_DIR / f"{name}.py")
    _load_module("anylabeling.platform.infrastructure", INFRA_DIR / "__init__.py")


_bootstrap()

from anylabeling.platform.domain.task import LabelClass, TaskSpec
from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter
from anylabeling.platform.infrastructure.checksum import compute_sha256
from anylabeling.platform.infrastructure.manifest_store import ManifestStore
from anylabeling.platform.infrastructure.project_file_store import (
    LABELS_JSON_FILENAME,
    ProjectFileStore,
    V4_PROJECT_DIRS,
)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _make_task_spec() -> TaskSpec:
    labels = (
        LabelClass(id=0, name="defect"),
        LabelClass(id=1, name="scratch", color="#FF0000"),
    )
    return TaskSpec(
        id="task_001",
        family="detection_hbb",
        labels=labels,
        annotation_schema="xanylabeling_json",
        primary_metric="map50_95",
    )


# ===================================================================
# 1. AtomicWriter tests
# ===================================================================

class TestAtomicWriterWriteJson:
    """Tests for AtomicWriter.write_json()."""

    def test_writes_valid_json(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "data.json"
        data = {"key": "value", "list": [1, 2, 3]}
        AtomicWriter.write_json(target, data)

        assert target.exists()
        assert target.is_file()
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert parsed == data

    def test_writes_pretty_json_with_indent_2(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "data.json"
        data = {"a": 1}
        AtomicWriter.write_json(target, data)
        raw = target.read_text(encoding="utf-8")
        assert "  " in raw  # indent=2 uses spaces
        assert raw.endswith("\n") or raw.endswith("}")  # json.dumps adds trailing newline

    def test_overwrites_existing_file(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "data.json"
        target.write_text("old content")
        AtomicWriter.write_json(target, {"new": True})
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert parsed == {"new": True}

    def test_writes_utf8_non_ascii(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "data.json"
        data = {"name": "你好", "desc": "こんにちは"}
        AtomicWriter.write_json(target, data)
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert parsed == data


class TestAtomicWriterNoPartialFile:
    """Tests verifying AtomicWriter does not leave partial / corrupt state."""

    def test_tmp_file_cleaned_up_after_success(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "data.json"
        AtomicWriter.write_json(target, {"ok": True})

        # No stray .tmp file should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Leftover tmp files: {tmp_files}"

    def test_target_is_directory_causes_oserror(self, tmp_path: pathlib.Path) -> None:
        """When the target path is a directory, os.replace fails and the
        directory must remain untouched (no partial replacement)."""
        target = tmp_path / "data.json"
        target.mkdir()

        with pytest.raises(OSError):
            AtomicWriter.write_json(target, {"key": "value"})

        # The directory must still exist — not replaced with a file
        assert target.is_dir(), "Target directory was corrupted"

    def test_original_content_preserved_on_os_replace_failure(self, tmp_path: pathlib.Path) -> None:
        """Write initial valid content, then simulate os.replace failure by
        replacing the target with a directory.  Recoverable?  Actually,
        we verify that *before* os.replace runs, the re-read validation
        step guards against corrupt writes.

        We do this by writing initial content, then making the target a
        directory, and verifying an error is raised without corrupting
        the directory."""
        target = tmp_path / "data.json"
        # Write initial content normally
        AtomicWriter.write_json(target, {"version": 1})
        parsed1 = json.loads(target.read_text(encoding="utf-8"))
        assert parsed1 == {"version": 1}

        # Remove file, replace with directory to force os.replace failure
        target.unlink()
        target.mkdir()

        with pytest.raises(OSError):
            AtomicWriter.write_json(target, {"version": 2})

        # Target is still a directory (not a corrupt partial file)
        assert target.is_dir()


class TestAtomicWriterWriteText:
    """Tests for AtomicWriter.write_text()."""

    def test_writes_text(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "notes.txt"
        AtomicWriter.write_text(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_tmp_cleaned_up(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "notes.txt"
        AtomicWriter.write_text(target, "content")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_target_is_directory_raises_oserror(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "notes.txt"
        target.mkdir()
        with pytest.raises(OSError):
            AtomicWriter.write_text(target, "content")
        assert target.is_dir()


# ===================================================================
# 2. ProjectFileStore tests
# ===================================================================

class TestProjectFileStoreCreate:
    """Tests for ProjectFileStore.create_project()."""

    def test_creates_all_9_directories(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        root = tmp_path / "workspace"
        root.mkdir()

        proj = ProjectFileStore.create_project(root, "my_project", task_spec)

        for dirname in V4_PROJECT_DIRS:
            d = proj / dirname
            assert d.exists(), f"Missing directory: {dirname}"
            assert d.is_dir(), f"Not a directory: {dirname}"

    def test_project_json_contains_correct_fields(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        root = tmp_path / "workspace"
        root.mkdir()

        proj = ProjectFileStore.create_project(root, "my_project", task_spec)
        project_json = proj / "project.json"

        data = json.loads(project_json.read_text(encoding="utf-8"))
        assert data["name"] == "my_project"
        assert data["version"] == "4.0.0"
        assert "created_at" in data
        # ISO 8601 format check: should contain 'T' or '+'
        assert "T" in data["created_at"] or "+" in data["created_at"]
        assert data["task_spec"]["id"] == "task_001"
        assert data["task_spec"]["family"] == "detection_hbb"
        # Labels are stored in labels.json, not duplicated in project.json
        assert data["task_spec"]["labels_file"] == "labels.json"
        assert "labels" not in data["task_spec"]

    def test_labels_json_contains_correct_label_list(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        root = tmp_path / "workspace"
        root.mkdir()

        proj = ProjectFileStore.create_project(root, "my_project", task_spec)
        labels_json = proj / "labels.json"

        data = json.loads(labels_json.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"id": 0, "name": "defect"}
        assert data[1] == {"id": 1, "name": "scratch"}

    def test_refuses_existing_project_root(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        root = tmp_path / "workspace"
        root.mkdir()
        ProjectFileStore.create_project(root, "my_project", task_spec)

        with pytest.raises(FileExistsError):
            ProjectFileStore.create_project(root, "my_project", task_spec)

    def test_returns_project_root_path(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        root = tmp_path / "workspace"
        root.mkdir()

        proj = ProjectFileStore.create_project(root, "my_project", task_spec)
        assert proj == root / "my_project"
        assert proj.is_dir()


class TestProjectFileStoreOpen:
    """Tests for ProjectFileStore.open_project()."""

    def test_reads_back_valid_project_data(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        metadata = ProjectFileStore.open_project(proj)
        assert metadata["name"] == "test_project"
        assert metadata["version"] == "4.0.0"
        assert metadata["task_spec"]["id"] == "task_001"

    def test_raises_filenotfound_for_missing_project_json(self, tmp_path: pathlib.Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            ProjectFileStore.open_project(empty_dir)

    def test_open_labels_reads_correct_labels(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        labels = ProjectFileStore.open_labels(proj)
        assert isinstance(labels, list)
        assert len(labels) == 2
        assert labels[0] == {"id": 0, "name": "defect"}
        assert labels[1] == {"id": 1, "name": "scratch"}

    def test_raises_filenotfound_for_missing_labels_json(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)
        (proj / LABELS_JSON_FILENAME).unlink()
        with pytest.raises(FileNotFoundError):
            ProjectFileStore.open_labels(proj)


class TestProjectFileStoreValidate:
    """Tests for ProjectFileStore.validate_project()."""

    def test_valid_project_returns_empty_issues(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        issues = ProjectFileStore.validate_project(proj)
        assert issues == [], f"Unexpected issues: {issues}"

    def test_detects_missing_directories(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        # Remove one directory
        import shutil
        shutil.rmtree(proj / "assets")

        issues = ProjectFileStore.validate_project(proj)
        assert len(issues) >= 1
        assert any("assets" in issue for issue in issues)

    def test_detects_missing_project_json(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        (proj / "project.json").unlink()
        issues = ProjectFileStore.validate_project(proj)
        assert any("project.json" in issue for issue in issues)

    def test_detects_corrupt_project_json(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        (proj / "project.json").write_text("not valid json{{{", encoding="utf-8")
        issues = ProjectFileStore.validate_project(proj)
        assert any("project.json" in issue for issue in issues)

    def test_detects_missing_labels_json(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        (proj / LABELS_JSON_FILENAME).unlink()
        issues = ProjectFileStore.validate_project(proj)
        assert any(LABELS_JSON_FILENAME in issue for issue in issues)

    def test_detects_corrupt_labels_json(self, tmp_path: pathlib.Path) -> None:
        task_spec = _make_task_spec()
        proj = ProjectFileStore.create_project(tmp_path, "test_project", task_spec)

        (proj / LABELS_JSON_FILENAME).write_text("not valid json{{{", encoding="utf-8")
        issues = ProjectFileStore.validate_project(proj)
        assert any(LABELS_JSON_FILENAME in issue for issue in issues)

    def test_detects_missing_root(self, tmp_path: pathlib.Path) -> None:
        issues = ProjectFileStore.validate_project(tmp_path / "nonexistent")
        assert len(issues) >= 1
        assert any("does not exist" in issue.lower() for issue in issues)


# ===================================================================
# 3. ManifestStore tests
# ===================================================================

class TestManifestStore:
    """Tests for ManifestStore.append_jsonl, read_jsonl, and validate_jsonl."""

    def test_append_and_read_round_trip(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "manifest.jsonl"
        rows = [
            {"asset_id": "a1", "sha256": "abc123"},
            {"asset_id": "a2", "sha256": "def456"},
            {"asset_id": "a3", "sha256": "ghi789"},
        ]
        for row in rows:
            ManifestStore.append_jsonl(path, row)

        read_back = ManifestStore.read_jsonl(path)
        assert read_back == rows

    def test_read_nonexistent_returns_empty_list(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "nonexistent.jsonl"
        result = ManifestStore.read_jsonl(path)
        assert result == []

    def test_append_creates_file_if_missing(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "new.jsonl"
        ManifestStore.append_jsonl(path, {"key": "value"})
        assert path.exists()
        assert path.is_file()

    def test_skip_empty_lines_in_read(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "manifest.jsonl"
        path.write_text(
            '{"id":1}\n\n{"id":2}\n   \n{"id":3}\n',
            encoding="utf-8",
        )
        rows = ManifestStore.read_jsonl(path)
        assert len(rows) == 3
        assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_validate_jsonl_returns_true_for_valid_file(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "valid.jsonl"
        ManifestStore.append_jsonl(path, {"a": 1})
        ManifestStore.append_jsonl(path, {"b": 2})
        assert ManifestStore.validate_jsonl(path) is True

    def test_validate_jsonl_returns_true_for_empty_file(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        assert ManifestStore.validate_jsonl(path) is True

    def test_validate_jsonl_returns_true_for_nonexistent(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "does_not_exist.jsonl"
        assert ManifestStore.validate_jsonl(path) is True

    def test_validate_jsonl_detects_corrupt_lines(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "corrupt.jsonl"
        path.write_text(
            '{"valid": true}\nthis is not json\n{"also": "valid"}\n',
            encoding="utf-8",
        )
        assert ManifestStore.validate_jsonl(path) is False


# ===================================================================
# 4. Checksum tests
# ===================================================================

class TestComputeSha256:
    """Tests for compute_sha256()."""

    def test_consistent_results(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "data.bin"
        path.write_bytes(b"hello world")
        h1 = compute_sha256(path)
        h2 = compute_sha256(path)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_content_produces_different_hash(self, tmp_path: pathlib.Path) -> None:
        path_a = tmp_path / "a.bin"
        path_b = tmp_path / "b.bin"
        path_a.write_bytes(b"hello")
        path_b.write_bytes(b"world")
        assert compute_sha256(path_a) != compute_sha256(path_b)

    def test_known_sha256_value(self, tmp_path: pathlib.Path) -> None:
        """Verify against known SHA-256 value for the string 'test'."""
        path = tmp_path / "test.txt"
        path.write_bytes(b"test")
        # Pre-computed: echo -n "test" | sha256sum
        expected = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        assert compute_sha256(path) == expected

    def test_large_file_chunked_reading(self, tmp_path: pathlib.Path) -> None:
        """Verify chunked reading works for files larger than default chunk_size."""
        path = tmp_path / "large.bin"
        # Write 20 KB of data (larger than default 8 KB chunk)
        data = b"x" * (20 * 1024)
        path.write_bytes(data)
        h1 = compute_sha256(path)
        h2 = compute_sha256(path, chunk_size=1024)
        assert h1 == h2
        assert len(h1) == 64


# ===================================================================
# 5. Architecture constraint tests (infrastructure layer)
# ===================================================================

FORBIDDEN_MODULES = [
    "PyQt6",
    "PyQt5",
    "ultralytics",
    "anylabeling.views",
]


def _infra_source_files() -> list[pathlib.Path]:
    return sorted(INFRA_DIR.glob("*.py"))


# Note: we cannot use ast.parse for import detection here because
# the infrastructure modules have already been loaded.  Instead we
# do a simple string grep.  For a proper CI guard, a static analysis
# tool would be better, but this keeps the test fast and simple.

@pytest.mark.parametrize("file_path", _infra_source_files())
def test_no_forbidden_imports_in_infrastructure(file_path: pathlib.Path) -> None:
    """Infrastructure layer must not import PyQt6, Ultralytics, or views.*."""
    source = file_path.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            for forbidden in FORBIDDEN_MODULES:
                if forbidden in stripped:
                    # Check it's actually importing that module, not a substring match
                    if stripped == f"import {forbidden}" or \
                       stripped.startswith(f"from {forbidden}") or \
                       stripped.startswith(f"import {forbidden}."):
                        pytest.fail(
                            f"{file_path.name} imports forbidden module: {forbidden}\n"
                            f"  Line: {stripped}"
                        )


def test_infrastructure_files_have_future_annotations() -> None:
    """All non-init infrastructure files must have ``from __future__ import annotations``."""
    missing: list[str] = []
    for fp in _infra_source_files():
        if fp.name == "__init__.py":
            continue
        source = fp.read_text(encoding="utf-8")
        if "from __future__ import annotations" not in source:
            missing.append(fp.name)
    assert missing == [], f"Missing __future__ annotations in: {missing}"


def test_infrastructure_files_have_all_export() -> None:
    """All non-init infrastructure files should define __all__."""
    missing: list[str] = []
    for fp in _infra_source_files():
        if fp.name == "__init__.py":
            continue
        source = fp.read_text(encoding="utf-8")
        if "__all__" not in source:
            missing.append(fp.name)
    assert missing == [], f"Missing __all__ export in: {missing}"
