"""AssetFilterBar — multi-facet filter bar and proxy model for asset lists."""

from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.application.asset_repository import AssetRepository
from anylabeling.views.platform.i18n import tr


class AssetFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Multi-facet filter for AssetListModel.

    Filters by annotation status, group, and text search simultaneously.
    Supports sorting by name, date, size, status.
    """

    SORT_ROLES = {
        "name": QtCore.Qt.ItemDataRole.DisplayRole,
        "date": QtCore.Qt.ItemDataRole.DisplayRole,  # future
        "size": QtCore.Qt.ItemDataRole.DisplayRole,  # future
        "status": QtCore.Qt.ItemDataRole.DisplayRole,  # future
    }

    def __init__(
        self, parent: QtCore.QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._status_filter: str = "all"
        self._group_filter: str = "all"
        self._search_text: str = ""
        self._repository: AssetRepository | None = None
        self._status_ids: set | None = None
        self._group_ids: set | None = None

    def set_repository(self, repo: AssetRepository) -> None:
        self._repository = repo

    def set_status_filter(self, status: str) -> None:
        self._status_filter = status
        if self._repository is not None and status != "all":
            self._status_ids = self._repository.get_asset_ids_by_status(status)
        else:
            self._status_ids = None
        self.invalidateFilter()

    def set_group_filter(self, group: str) -> None:
        self._group_filter = group
        if self._repository is not None and group != "all":
            self._group_ids = self._repository.get_asset_ids_by_group(group)
        else:
            self._group_ids = None
        self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        self._search_text = text
        self.invalidateFilter()

    def status_filter(self) -> str:
        return self._status_filter

    def group_filter(self) -> str:
        return self._group_filter

    def search_text(self) -> str:
        return self._search_text

    def set_sort_option(self, option: str) -> None:
        """Apply sorting by *option* (name/date/size/status)."""
        role = self.SORT_ROLES.get(option)
        if role is not None:
            self.setSortRole(role)
            self.sort(0, QtCore.Qt.SortOrder.AscendingOrder)

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QtCore.QModelIndex = QtCore.QModelIndex(),
    ) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        index = model.index(source_row, 0, source_parent)
        path = model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)

        if self._search_text and path:
            if self._search_text.lower() not in str(path).lower():
                return False

        if self._status_ids is not None and path:
            stem = Path(str(path)).stem
            if stem not in self._status_ids:
                return False

        if self._group_ids is not None and path:
            stem = Path(str(path)).stem
            if stem not in self._group_ids:
                return False

        return True


class AssetFilterBar(QtWidgets.QWidget):
    """Horizontal filter bar for the asset list.

    Contains search input, status dropdown, group dropdown, sort dropdown.
    """

    filter_changed = QtCore.pyqtSignal()

    SORT_OPTIONS = ["name", "date", "size", "status"]

    def __init__(
        self,
        asset_repository: AssetRepository,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = asset_repository
        self._build_ui()
        self._populate_dropdowns()

    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText(
            tr("搜索…", "Search…")
        )
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(
            self.filter_changed.emit
        )
        layout.addWidget(self._search_input)

        self._status_combo = QtWidgets.QComboBox()
        self._status_combo.addItem(
            tr("状态: 全部", "Status: All"), "all"
        )
        self._status_combo.addItem(
            tr("已标注", "Annotated"), "complete"
        )
        self._status_combo.addItem(
            tr("未标注", "Unannotated"), "unannotated"
        )
        self._status_combo.addItem(
            tr("部分标注", "Partial"), "partial"
        )
        self._status_combo.currentIndexChanged.connect(
            self.filter_changed.emit
        )
        layout.addWidget(self._status_combo)

        self._group_combo = QtWidgets.QComboBox()
        self._group_combo.addItem(
            tr("分组: 全部", "Group: All"), "all"
        )
        self._group_combo.currentIndexChanged.connect(
            self.filter_changed.emit
        )
        layout.addWidget(self._group_combo)

        self._sort_combo = QtWidgets.QComboBox()
        for opt in self.SORT_OPTIONS:
            self._sort_combo.addItem(
                tr(opt.capitalize(), opt.capitalize()), opt
            )
        self._sort_combo.currentIndexChanged.connect(
            self.filter_changed.emit
        )
        layout.addWidget(self._sort_combo)

        layout.addStretch()
        self.setLayout(layout)

    def _populate_dropdowns(self) -> None:
        """Populate group dropdown from repository."""
        groups = self._repo.get_groups()
        for g in groups:
            self._group_combo.addItem(g, g)

    @property
    def search_text(self) -> str:
        return self._search_input.text()

    @property
    def status_filter(self) -> str:
        return self._status_combo.currentData()

    @property
    def group_filter(self) -> str:
        return self._group_combo.currentData()

    @property
    def sort_option(self) -> str:
        return self._sort_combo.currentData()

    def refresh_groups(self) -> None:
        """Refresh group dropdown from the repository."""
        current = self._group_combo.currentData()
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem(
            tr("分组: 全部", "Group: All"), "all"
        )
        for g in self._repo.get_groups():
            self._group_combo.addItem(g, g)
        idx = self._group_combo.findData(current)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self._group_combo.blockSignals(False)


__all__ = ["AssetFilterBar", "AssetFilterProxyModel"]
