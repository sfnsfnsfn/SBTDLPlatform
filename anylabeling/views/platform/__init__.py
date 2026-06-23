"""Platform Workbench UI — V4 MVP M1.5.

Provides the WorkbenchWindow shell that wraps the existing X-AnyLabeling
LabelingWidget as a "Label Workspace" page within a multi-step pipeline UI.
"""

from anylabeling.views.platform.workbench_window import WorkbenchWindow
from anylabeling.views.platform.navigation_bar import (
    NavigationBar,
    PipelineStep,
    DATA,
    LABEL,
    TRAIN,
    EVALUATE,
    INFER,
    EXPORT,
)
from anylabeling.views.platform.project_home import ProjectHomeWidget
from anylabeling.views.platform.new_project_dialog import NewProjectDialog
from anylabeling.views.platform.job_console import JobConsole
from anylabeling.views.platform.train_workspace import TrainWorkspace
from anylabeling.views.platform.data_workspace import DataWorkspace
from anylabeling.views.platform.export_workspace import ExportWorkspace
from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
from anylabeling.views.platform.infer_workspace import InferWorkspace
from anylabeling.views.platform.label_workspace import LabelWorkspace
from anylabeling.views.platform.i18n import tr, set_locale

__all__ = [
    "WorkbenchWindow",
    "NavigationBar",
    "PipelineStep",
    "DATA", "LABEL", "TRAIN", "EVALUATE", "INFER", "EXPORT",
    "ProjectHomeWidget",
    "NewProjectDialog",
    "JobConsole",
    "TrainWorkspace",
    "DataWorkspace",
    "ExportWorkspace",
    "EvaluateWorkspace",
    "InferWorkspace",
    "LabelWorkspace",
    "tr",
    "set_locale",
]
