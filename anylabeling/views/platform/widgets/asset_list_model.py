"""AssetListModel — QAbstractListModel for virtual asset list rendering.

Backed by AssetRepository with lazy loading via canFetchMore/fetchMore.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore

from anylabeling.platform.application.asset_repository import AssetRepository
from anylabeling.platform.domain.asset import Asset

BATCH_SIZE = 100


class AssetListModel(QtCore.QAbstractListModel):
    """Virtual list model for assets — only visible rows are materialized.

    Uses ``canFetchMore`` / ``fetchMore`` for incremental loading in
    batches of 100. Backed by AssetRepository.

    Roles:
        - DisplayRole: filename (basename)
        - UserRole: asset id
        - ToolTipRole: full asset path
    """

    def __init__(
        self,
        asset_repository: AssetRepository,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = asset_repository
        self._asset_paths: list[str] = []
        self._asset_cache: dict[str, Asset] = {}
        self._cursor: int = 0
        self._all_loaded: bool = False
        self._refresh_paths()

    # ------------------------------------------------------------------
    # QAbstractListModel interface
    # ------------------------------------------------------------------

    def rowCount(
        self, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> int:
        return len(self._asset_paths)

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._asset_paths):
            return None

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return Path(self._asset_paths[row]).name
        if role == QtCore.Qt.ItemDataRole.UserRole:
            asset = self._get_asset(row)
            return asset.id if asset else None
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return self._asset_paths[row]
        return None

    def canFetchMore(
        self, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        return not self._all_loaded

    def fetchMore(
        self, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> None:
        if self._all_loaded:
            return

        new_paths = self._repo.scan_assets(
            offset=self._cursor, limit=BATCH_SIZE
        )
        if len(new_paths) < BATCH_SIZE:
            self._all_loaded = True

        if not new_paths:
            return

        count = len(new_paths)
        first = len(self._asset_paths)
        last = first + count - 1

        self.beginInsertRows(QtCore.QModelIndex(), first, last)
        self._asset_paths.extend(new_paths)
        self._cursor += count
        self.endInsertRows()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-scan repository and reset the model."""
        self.beginResetModel()
        self._asset_paths.clear()
        self._asset_cache.clear()
        self._cursor = 0
        self._all_loaded = False
        self._refresh_paths()
        self.endResetModel()

    def asset_path_at(self, row: int) -> str | None:
        """Return the absolute asset path at *row*, or None."""
        if 0 <= row < len(self._asset_paths):
            return self._asset_paths[row]
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_paths(self) -> None:
        """Load the initial batch from the repository."""
        new_paths = self._repo.scan_assets(offset=0, limit=BATCH_SIZE)
        if len(new_paths) < BATCH_SIZE:
            self._all_loaded = True
        self._asset_paths = list(new_paths)
        self._cursor = len(new_paths)

    def _get_asset(self, row: int) -> Asset | None:
        """Lazy-load Asset metadata, caching the result."""
        path = self._asset_paths[row]
        if path not in self._asset_cache:
            asset = self._repo.get_asset(path)
            if asset is not None:
                self._asset_cache[path] = asset
        return self._asset_cache.get(path)


__all__ = ["AssetListModel", "BATCH_SIZE"]
