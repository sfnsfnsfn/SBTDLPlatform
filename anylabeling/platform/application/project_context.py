"""ProjectContext — unified dependency assembly hub for a platform project.

Owns the SQLite database connection, all repository instances, and the
existing JobService/WorkflowState services.
"""

from __future__ import annotations

import logging
from pathlib import Path

from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.application.workflow_state import DomainState, WorkflowState
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.annotations import SQLiteAnnotationRepository
from anylabeling.platform.infrastructure.sqlite_repositories.assets import SQLiteAssetRepository
from anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds import SQLiteDatasetBuildRepository
from anylabeling.platform.infrastructure.sqlite_repositories.evaluations import SQLiteEvaluationRepository
from anylabeling.platform.infrastructure.sqlite_repositories.jobs import SQLiteJobRepository
from anylabeling.platform.infrastructure.sqlite_repositories.models import SQLiteModelRepository
from anylabeling.platform.infrastructure.sqlite_repositories.runs import SQLiteRunRepository
from anylabeling.platform.infrastructure.sqlite_repositories.workflow_query import SQLiteWorkflowQuery

_logger = logging.getLogger(__name__)


class ProjectContext:
    """Unified dependency assembly for an open platform project."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root).resolve()
        self._db: ProjectDb | None = None
        self._assets: SQLiteAssetRepository | None = None
        self._annotations: SQLiteAnnotationRepository | None = None
        self._dataset_builds: SQLiteDatasetBuildRepository | None = None
        self._runs: SQLiteRunRepository | None = None
        self._jobs_repo: SQLiteJobRepository | None = None
        self._models: SQLiteModelRepository | None = None
        self._evaluations: SQLiteEvaluationRepository | None = None
        self._workflow_query: SQLiteWorkflowQuery | None = None
        self._job_service: JobService | None = None
        self._workflow_state: WorkflowState | None = None

    def open(self) -> None:
        db_path = self._project_root / "project.sqlite"
        self._db = ProjectDb(db_path)
        self._db.open()
        self._assets = SQLiteAssetRepository(self._db)
        self._annotations = SQLiteAnnotationRepository(self._db)
        self._dataset_builds = SQLiteDatasetBuildRepository(self._db)
        self._runs = SQLiteRunRepository(self._db)
        self._jobs_repo = SQLiteJobRepository(self._db)
        self._models = SQLiteModelRepository(self._db)
        self._evaluations = SQLiteEvaluationRepository(self._db)
        self._workflow_query = SQLiteWorkflowQuery(self._db)
        jobs_root = self._project_root / "jobs"
        self._job_service = JobService(jobs_root)
        self._workflow_state = WorkflowState(self._project_root)
        _logger.info("ProjectContext opened for %s", self._project_root)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        for attr in ("_assets", "_annotations", "_dataset_builds", "_runs",
                     "_jobs_repo", "_models", "_evaluations", "_workflow_query",
                     "_job_service", "_workflow_state"):
            setattr(self, attr, None)
        _logger.info("ProjectContext closed")

    @property
    def project_root(self) -> Path: return self._project_root
    @property
    def db(self) -> ProjectDb:
        if self._db is None: raise RuntimeError("Not open")
        return self._db
    @property
    def assets(self):
        if self._assets is None: raise RuntimeError("Not open")
        return self._assets
    @property
    def annotations(self):
        if self._annotations is None: raise RuntimeError("Not open")
        return self._annotations
    @property
    def dataset_builds(self):
        if self._dataset_builds is None: raise RuntimeError("Not open")
        return self._dataset_builds
    @property
    def runs(self):
        if self._runs is None: raise RuntimeError("Not open")
        return self._runs
    @property
    def jobs(self):
        if self._jobs_repo is None: raise RuntimeError("Not open")
        return self._jobs_repo
    @property
    def models(self):
        if self._models is None: raise RuntimeError("Not open")
        return self._models
    @property
    def evaluations(self):
        if self._evaluations is None: raise RuntimeError("Not open")
        return self._evaluations
    @property
    def workflow_query(self):
        if self._workflow_query is None: raise RuntimeError("Not open")
        return self._workflow_query
    @property
    def job_service(self) -> JobService:
        if self._job_service is None: raise RuntimeError("Not open")
        return self._job_service
    @property
    def workflow_state(self):
        if self._workflow_state is None: raise RuntimeError("Not open")
        return self._workflow_state
    @property
    def is_open(self) -> bool: return self._db is not None

    def refresh_navigation_state(self):
        if self._workflow_state is None: return {}
        return self._workflow_state.refresh()

    def db_path(self) -> Path:
        return self._project_root / "project.sqlite"


__all__ = ["ProjectContext"]
