"""Shell package — new 5-domain application shell widgets.

Replaces the old 8-step horizontal NavigationBar + QTreeWidget + Inspector +
JobConsole layout with a modern 5-domain vertical navigation design.
"""

from anylabeling.views.platform.shell.app_bar import AppBar
from anylabeling.views.platform.shell.error_banner import ErrorBanner
from anylabeling.views.platform.shell.primary_navigation import (
    Domain,
    NavState,
    PrimaryNavigation,
)
from anylabeling.views.platform.shell.page_header import PageHeader
from anylabeling.views.platform.shell.status_bar import StatusBar
from anylabeling.views.platform.shell.sub_nav import SubNav, SubStep
from anylabeling.views.platform.shell.task_center_drawer import (
    TaskCenterDrawer,
)

__all__ = [
    "AppBar",
    "Domain",
    "ErrorBanner",
    "NavState",
    "PageHeader",
    "PrimaryNavigation",
    "StatusBar",
    "SubNav",
    "SubStep",
    "TaskCenterDrawer",
]
