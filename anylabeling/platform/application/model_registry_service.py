"""ModelRegistryService — manages registered models for a project.

Each project has a ``models/registry.json`` that records which exported models
are available for use in the labeling workspace.

Architecture constraints:
    - No PyQt6 imports.
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from anylabeling.platform.domain.model import ModelArtifact


class ModelRegistryService:
    """Manages the project-level model registry.

    The registry is stored at ``<project_root>/models/registry.json`` as a JSON
    array of model entries.

    Usage::

        registry = ModelRegistryService(project_root="/data/project")
        registry.register(artifact)
        models = registry.list_models()
        registry.unregister("model_abc123")
    """

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def registry_path(self) -> Path:
        """Path to the registry.json file."""
        return self._project_root / "models" / "registry.json"

    # ------------------------------------------------------------------
    # register
    # ------------------------------------------------------------------

    def register(self, artifact: ModelArtifact) -> None:
        """Register an exported model in the project's model registry.

        If a model with the same ``model_id`` already exists, its entry is
        updated rather than duplicated.

        Args:
            artifact: The :class:`ModelArtifact` to register.
        """
        registry = self._read_registry()

        entry = {
            "model_id": artifact.id,
            "run_id": artifact.run_id,
            "format": artifact.format,
            "path": artifact.path,
            "labels": artifact.labels,
            "preprocess": artifact.preprocess,
            "postprocess": artifact.postprocess,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        # Replace existing entry with same model_id if present
        existing_idx: int | None = None
        for i, item in enumerate(registry):
            if item.get("model_id") == artifact.id:
                existing_idx = i
                break

        if existing_idx is not None:
            registry[existing_idx] = entry
        else:
            registry.append(entry)

        self._write_registry(registry)

    # ------------------------------------------------------------------
    # list_models
    # ------------------------------------------------------------------

    def list_models(self) -> list[dict]:
        """List all registered models for this project.

        Returns:
            A list of dicts, each with keys ``model_id``, ``run_id``,
            ``format``, ``path``, ``labels``, ``registered_at``.
        """
        return self._read_registry()

    # ------------------------------------------------------------------
    # unregister
    # ------------------------------------------------------------------

    def unregister(self, model_id: str) -> None:
        """Remove a model from the registry.

        Args:
            model_id: The model identifier to remove.

        Raises nothing if the model_id is not found.
        """
        registry = self._read_registry()
        registry = [m for m in registry if m.get("model_id") != model_id]
        self._write_registry(registry)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _read_registry(self) -> list[dict]:
        """Read the registry file, returning an empty list if missing/corrupt."""
        path = self.registry_path
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_registry(self, registry: list[dict]) -> None:
        """Write the registry to disk atomically."""
        path = self.registry_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


__all__ = [
    "ModelRegistryService",
]
