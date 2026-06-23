from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from anylabeling.platform.domain.task import LabelClass, TaskSpec
from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

V4_PROJECT_DIRS: tuple[str, ...] = (
    "assets",
    "annotations",
    "dataset_builds",
    "jobs",
    "runs",
    "evaluations",
    "models",
    "cache",
    "logs",
)

PROJECT_JSON_FILENAME = "project.json"
LABELS_JSON_FILENAME = "labels.json"


class ProjectFileStore:
    """File-system project storage for V4 MVP.

    Creates and validates the on-disk project directory structure defined
    by the V4 platform specification.  All writes use :class:`AtomicWriter`
    to prevent partial-file corruption.

    Labels are stored in ``labels.json`` as the single source of truth.
    ``project.json`` references it via ``"labels_file"`` rather than
    duplicating the label list.
    """

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    @staticmethod
    def create_project(
        root: str | Path,
        name: str,
        task_spec: TaskSpec | None = None,
        description: str = "",
    ) -> Path:
        """Create a V4 MVP project directory at *root/name*.

        Creates all required subdirectories and writes ``project.json`` and
        ``labels.json`` via :class:`AtomicWriter`.  Labels are written to
        ``labels.json`` only; ``project.json`` stores a reference to the
        labels file via ``task_spec.labels_file``.

        Args:
            root: Parent directory.
            name: Project name (becomes the directory name).
            task_spec: Optional task specification. If None, task_spec is null
                       (user chose "Configure Later").
            description: Optional project description.

        Returns:
            Path to the created project root directory.
        """
        project_root = Path(root) / name
        project_root.mkdir(parents=True, exist_ok=False)

        # Create subdirectories
        for dirname in V4_PROJECT_DIRS:
            (project_root / dirname).mkdir(parents=False, exist_ok=False)

        # Build labels.json (source of truth for labels)
        labels_data = []
        if task_spec is not None:
            labels_data = [
                {"id": lb.id, "name": lb.name} for lb in task_spec.labels
            ]
        AtomicWriter.write_json(project_root / LABELS_JSON_FILENAME, labels_data)

        # Build project.json metadata
        project_meta = {
            "name": name,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": "4.0.0",
            "import_state": {"has_assets": False},
            "task_spec": None,
        }

        if task_spec is not None:
            project_meta["task_spec"] = {
                "id": task_spec.id,
                "family": task_spec.family,
                "labels_file": LABELS_JSON_FILENAME,
                "version": task_spec.version,
            }
        else:
            project_meta["task_spec"] = None

        AtomicWriter.write_json(project_root / PROJECT_JSON_FILENAME, project_meta)

        return project_root

    # ------------------------------------------------------------------
    # open / validate
    # ------------------------------------------------------------------

    @staticmethod
    def open_project(root: str | Path) -> dict:
        """Read and return the ``project.json`` metadata from *root*.

        Returns:
            Parsed project metadata dictionary.
        Raises:
            FileNotFoundError: If ``project.json`` does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        p = Path(root) / PROJECT_JSON_FILENAME
        if not p.exists():
            raise FileNotFoundError(f"project.json not found at {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def open_labels(root: str | Path) -> list[dict]:
        """Read and return the ``labels.json`` label list from *root*.

        Returns:
            List of label dicts, e.g. ``[{"id": 0, "name": "defect"}, ...]``.
        Raises:
            FileNotFoundError: If ``labels.json`` does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        p = Path(root) / LABELS_JSON_FILENAME
        if not p.exists():
            raise FileNotFoundError(f"labels.json not found at {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def save_task_spec(root: str | Path, task_spec: TaskSpec) -> None:
        """Persist *task_spec* to the project at *root*.

        Updates both ``project.json`` (task_spec section) and
        ``labels.json`` (label list).  Writes are atomic.
        """
        project_root = Path(root)
        project_path = project_root / PROJECT_JSON_FILENAME
        labels_path = project_root / LABELS_JSON_FILENAME

        # Update labels.json
        labels_data = [
            {"id": lb.id, "name": lb.name} for lb in task_spec.labels
        ]
        AtomicWriter.write_json(labels_path, labels_data)

        # Update project.json task_spec section
        try:
            meta = json.loads(project_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {}
        meta["task_spec"] = {
            "id": task_spec.id,
            "family": task_spec.family,
            "labels_file": LABELS_JSON_FILENAME,
            "version": task_spec.version,
        }
        AtomicWriter.write_json(project_path, meta)

    @staticmethod
    def validate_project(root: str | Path) -> list[str]:
        """Check project directory integrity.

        Returns a list of human-readable issue strings.  An empty list
        means the project passes all checks.

        Checks performed:
        - All required subdirectories exist.
        - ``project.json`` exists and is valid JSON.
        - ``labels.json`` exists and is valid JSON (required).
        """
        p = Path(root)
        issues: list[str] = []

        if not p.exists():
            return [f"Project root does not exist: {p}"]

        # Check directories
        for dirname in V4_PROJECT_DIRS:
            d = p / dirname
            if not d.exists():
                issues.append(f"Missing directory: {dirname}")
            elif not d.is_dir():
                issues.append(f"Not a directory: {dirname}")

        # Check project.json
        proj_path = p / PROJECT_JSON_FILENAME
        if not proj_path.exists():
            issues.append(f"Missing {PROJECT_JSON_FILENAME}")
        else:
            try:
                json.loads(proj_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                issues.append(f"Invalid {PROJECT_JSON_FILENAME}: {exc}")

        # Check labels.json (required — source of truth for labels)
        labels_path = p / LABELS_JSON_FILENAME
        if not labels_path.exists():
            issues.append(f"Missing {LABELS_JSON_FILENAME}")
        else:
            try:
                json.loads(labels_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                issues.append(f"Invalid {LABELS_JSON_FILENAME}: {exc}")

        return issues


__all__ = [
    "LABELS_JSON_FILENAME",
    "PROJECT_JSON_FILENAME",
    "ProjectFileStore",
    "V4_PROJECT_DIRS",
]
