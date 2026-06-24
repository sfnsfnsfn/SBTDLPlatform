"""SQLite-backed repository implementations for the platform domain.

Each repository accepts a :class:`~anylabeling.platform.infrastructure.project_db.ProjectDb`
instance in its constructor and manages its own table schema via ``CREATE TABLE IF NOT EXISTS``.
Write operations use the ``INSERT … ON CONFLICT`` (upsert) pattern for idempotent persistence.
"""

from anylabeling.platform.infrastructure.sqlite_repositories.annotations import (
    SQLiteAnnotationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.assets import (
    SQLiteAssetRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds import (
    SQLiteDatasetBuildRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.evaluations import (
    SQLiteEvaluationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.jobs import (
    SQLiteJobRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.models import (
    SQLiteModelRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.runs import (
    SQLiteRunRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.workflow_query import (
    SQLiteWorkflowQuery,
)

__all__ = [
    "SQLiteAnnotationRepository",
    "SQLiteAssetRepository",
    "SQLiteDatasetBuildRepository",
    "SQLiteEvaluationRepository",
    "SQLiteJobRepository",
    "SQLiteModelRepository",
    "SQLiteRunRepository",
    "SQLiteWorkflowQuery",
]
