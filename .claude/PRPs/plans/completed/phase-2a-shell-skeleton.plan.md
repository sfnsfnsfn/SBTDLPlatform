# Plan: Phase 2a — 新应用外壳骨架

## Summary
将当前 8 步顶部水平 Pipeline 导航替换为 5 域左侧导航（项目/数据准备/训练/评估与验证/导出），创建统一的应用栏、页面标题区和状态栏组件，建立新的 UI Shell 骨架。淘汰旧的 NavigationBar 水平按钮和 JobConsole 底部面板，为 Phase 2b 的 WorkflowState/ProjectSession/任务中心/统一错误组件提供容器。

## User Story
As a 算法工程师, I want 看到清晰的 5 域导航和统一的页面标题区, So that 我每次操作只需关注一个主目标，不被 8 步流水线分散注意力。

## Problem → Solution
当前 8 步顶部水平导航（PROJECT→IMPORT→CONFIG→LABEL→PREPROCESS→TRAIN→EVALUATE→EXPORT）将"数据准备"拆为 4 步，挤占导航空间 → 按 PRD 规范收敛为 5 域左侧导航。页面标题区每个页面自行设计 → 统一 `PageHeader` 组件。

## Metadata
- **Complexity**: Large (10–14 files, ~1200 lines)
- **Source PRD**: `docs/superpowers/plans/X-AnyLabeling_离线深度学习平台_产品化UI整改落地方案.md`
- **PRD Phase**: 阶段 2 — 新应用外壳与友好交互 (子阶段 2a)
- **Depends On**: Phase 1 (complete)
- **Estimated Files**: 6 new, 6 modified

---

## UX Design

### Before
```
┌─ NavigationBar (horizontal, 8 steps) ────────────────────────────────────┐
│ PROJECT → IMPORT → CONFIG → LABEL → PREPROCESS → TRAIN → EVALUATE → EXPORT│
├─ QSplitter ───────────────────────────────────────────────────────────────┤
│ [Tree 220px] │ [QStackedWidget — page content] │ [Inspector 220px]        │
├─ JobConsole (bottom footer, 80-200px) ────────────────────────────────────┤
│ Job list: training run-xxx 62% ...                                        │
└───────────────────────────────────────────────────────────────────────────┘
```

### After
```
┌─ AppBar (48px) ───────────────────────────────────────────────────────────┐
│ Logo | 当前项目▼ | 项目健康 | Ctrl+K | 任务中心 ●2 | 设置 | 帮助         │
├─ PrimaryNav (176px) ┬─ PageHeader (56px) ─────────────────────────────────┤
│ ● 项目              │ 页面标题 — 来源上下文 — 状态    [唯一主按钮]         │
│ ○ 数据准备          ├─ Page Content ──────────────────────────────────────┤
│ ○ 训练              │                                                    │
│ ○ 评估与验证        │     (QStackedWidget — 旧页面保持不变)               │
│ ○ 导出              │                                                    │
│                     │                                                    │
│ [折叠导航]          │                                                    │
├─────────────────────┴──────────────────────────────────────────────────────┤
│ StatusBar (24px): 已保存 | 当前设备 | 后台任务 | 本地离线状态               │
└───────────────────────────────────────────────────────────────────────────┘
```

### 数据准备子导航（仅在数据准备域内显示）
```
┌─ SubNav (inline, below PageHeader) ───────────────────────────────────────┐
│ 导入数据 → 任务与标签 → 标注 → 数据集构建                                  │
│ 资产 17,888 | 已标注 12,310 | 待复核 420 | 当前任务：实例分割 v3           │
└───────────────────────────────────────────────────────────────────────────┘
```

### 任务中心（右侧 Drawer，叠加，不常驻）
```
┌──────────┬──────────────────────┬─ TaskCenterDrawer (420px) ──┐
│ Primary  │ Page Content         │ [全部] [运行中] [失败]      │
│ Nav      │                      │ 训练 run-xxx    62%         │
│ 176px    │                      │ 数据集构建     正在写入...  │
│          │                      │ 导出 model-xxx  失败        │
│          │                      │ [查看详情] [停止/重试]     │
└──────────┴──────────────────────┴─────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After |
|---|---|---|
| 全局导航 | 8 步水平 Pipeline 按钮 | 5 域左侧 PrimaryNav + 图标 |
| 项目状态 | 无全局项目指示器 | AppBar 项目下拉 + 健康指示 |
| 页面标题 | 各页面自行设计 | 统一 PageHeader（标题/来源/状态/主按钮） |
| 任务进度 | JobConsole 底部嵌入面板 | TaskCenterDrawer 右侧叠加 |
| 状态栏 | QStatusBar 单行文本 | 自定义 StatusBar（保存状态/设备/后台任务/离线） |
| 数据准备子步骤 | 4 个独立顶部按钮 | SubNav 内联步骤条 + 统计条 |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `views/platform/workbench_window.py` | 1–500 | 当前 Shell — 理解所有连接点和迁移范围 |
| P0 | `views/platform/navigation_bar.py` | 1–205 | 现有 NavigationBar — 需替换但保留 PipelineStep |
| P0 | `views/platform/style.py` | 1–80 | 设计 token 和字体系统 |
| P1 | `views/platform/project_home.py` | all | 项目主页 — 与 AppBar 交互 |
| P1 | `views/platform/label_workspace.py` | first 100L | 标注页面三栏布局 — PrimaryNav 折叠交互 |
| P2 | `platform/workers/protocol.py` | 1–50 | JobState 枚举 — TaskCenterDrawer 数据源 |

---

## Patterns to Mirror

### Shell layout pattern (existing WorkbenchWindow)
// SOURCE: views/platform/workbench_window.py:66-122
```python
# 布局: NavigationBar → QSplitter(tree|stack|inspector) → JobConsole
main_vlayout = QtWidgets.QVBoxLayout()
main_vlayout.addWidget(self._navigation)
h_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
main_vlayout.addWidget(h_splitter, stretch=1)
main_vlayout.addWidget(self._job_console)
```

### Page creation + lazy-loading + replacement
// SOURCE: views/platform/workbench_window.py:245-293
```python
self._page_loaded: dict[int, bool] = {}
self._page_widgets: dict[int, QtWidgets.QWidget] = {}

def _replace_page(self, step, widget):
    idx = step.value
    old = self._pages.widget(idx)
    if old is not None and old is not widget:
        self._pages.removeWidget(old)
        old.deleteLater()
    self._pages.insertWidget(idx, widget)
```

### Signal-based navigation
// SOURCE: views/platform/workbench_window.py:421-425
```python
def _navigate_to(self, step: PipelineStep) -> None:
    self._load_page(step)
    self._pages.setCurrentIndex(step.value)
    self._navigation.set_current_step(step)
```

### Theme-aware QSS generation
// SOURCE: views/platform/style.py:74-80
```python
def get_primary_button_style(*, min_width=0, min_height=0) -> str:
    t = get_theme()
    return f"""QPushButton {{ background-color: {t["primary"]}; ... }}"""
```

### i18n function
// SOURCE: views/platform/i18n.py
```python
def tr(zh: str, en: str) -> str:
    # Returns zh or en based on current locale
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `views/platform/shell/app_bar.py` | **CREATE** | 应用栏：Logo + 项目选择 + 健康 + 搜索 + 任务中心 + 设置 + 帮助 |
| `views/platform/shell/primary_navigation.py` | **CREATE** | 5 域左侧导航 + 状态指示器 + 折叠 |
| `views/platform/shell/page_header.py` | **CREATE** | 统一页面标题区：标题/来源面包屑/状态/主按钮 |
| `views/platform/shell/status_bar.py` | **CREATE** | 状态栏：保存状态/设备/后台任务数/离线状态 |
| `views/platform/shell/__init__.py` | **CREATE** | Shell 包导出 |
| `views/platform/shell/sub_nav.py` | **CREATE** | 数据准备域内 4 步子导航 + 统计条 |
| `views/platform/workbench_window.py` | **UPDATE** | 替换整个 Shell：移除 NavigationBar/QTreeWidget/Inspector/JobConsole；接入新 Shell 组件 |
| `views/platform/navigation_bar.py` | **UPDATE** | 保留 PipelineStep/step_label，标记 NavigationBar 为 deprecated |
| `views/platform/style.py` | **UPDATE** | 新增 Shell 布局常量（APPBAR_H=48, NAV_W=176, HEADER_H=56, STATUSBAR_H=24, MIN_NAV_W=56） |
| `views/platform/label_workspace.py` | **UPDATE** | 标注页面时发射 signal 触发 PrimaryNav 折叠 |

## NOT Building (2a scope)

- WorkflowState 服务（Phase 2b）
- ProjectSession（Phase 2b）
- TaskCenterDrawer 完整实现（Phase 2b: 仅创建占位按钮和抽屉容器）
- 统一错误组件 ErrorBanner（Phase 2b）
- 命令面板 Ctrl+K（Phase 5）
- 数据导入预检重构（Phase 3）
- 标注自动保存（Phase 3）
- QTreeWidget/Inspector 移除后的功能补偿（Phase 3 用虚拟列表替换）
- PrimaryNav 动态状态计算（Phase 2b WorkflowState 驱动）
- 5 域页面切换的详细实现（Phase 2b 配合 ProjectSession）

---

## Step-by-Step Tasks

### Task 0: Add Shell layout constants to style.py
- **PRECHECK_AGENTS**: (none — 纯常量声明，无架构/安全/测试风险)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 新增 Shell 布局常量
- **IMPLEMENT**:
  ```python
  # Shell layout constants (px)
  APPBAR_HEIGHT = 48
  PRIMARY_NAV_WIDTH = 176
  PRIMARY_NAV_MIN_WIDTH = 56
  PAGE_HEADER_HEIGHT = 56
  PAGE_HEADER_MIN_HEIGHT = 48
  PAGE_HEADER_MAX_HEIGHT = 64
  STATUS_BAR_HEIGHT = 24
  TASK_DRAWER_WIDTH = 420
  TASK_DRAWER_MIN_WIDTH = 360
  TASK_DRAWER_MAX_WIDTH = 520
  MIN_WINDOW_WIDTH = 1280
  MIN_WINDOW_HEIGHT = 720
  RECOMMENDED_WIDTH = 1920
  RECOMMENDED_HEIGHT = 1080
  # Responsive breakpoints
  BREAKPOINT_NAV_FOLD = 1440  # Auto-suggest fold below this width
  ```
- **MIRROR**: `style.py` 现有 FONT_* 常量
- **GOTCHA**: 常量仅用于 CSS 和布局计算，不影响运行时可调逻辑
- **VALIDATE**: `python -c "from anylabeling.views.platform.style import APPBAR_HEIGHT; print(APPBAR_HEIGHT)"`

### Task 1: Create PrimaryNavigation widget
- **PRECHECK_AGENTS**: architect (新 Widget API 设计 + 5 域路由契约) + tdd-guide (新功能，测试先于实现)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 创建 `views/platform/shell/primary_navigation.py`
- **IMPLEMENT**:
  ```python
  class Domain(IntEnum):
      PROJECT = 0
      DATA_PREP = 1
      TRAIN = 2
      EVAL_VALIDATE = 3
      EXPORT = 4

  DOMAIN_LABELS_ZH = {
      Domain.PROJECT: "项目",
      Domain.DATA_PREP: "数据准备",
      Domain.TRAIN: "训练",
      Domain.EVAL_VALIDATE: "评估与验证",
      Domain.EXPORT: "导出",
  }

  class NavState(Enum):
      NOT_STARTED = "not_started"
      READY = "ready"
      IN_PROGRESS = "in_progress"
      COMPLETED = "completed"
      NEEDS_ATTENTION = "needs_attention"
      EXPIRED = "expired"

  class PrimaryNavigation(QtWidgets.QWidget):
      domain_changed = QtCore.pyqtSignal(int)   # Domain value
      fold_requested = QtCore.pyqtSignal(bool)   # True = fold

      def __init__(self, parent=None): ...
      def set_current_domain(self, domain: Domain): ...
      def set_domain_state(self, domain: Domain, state: NavState): ...
      def set_folded(self, folded: bool): ...
  ```
  - 5 个导航项，每项显示：图标 + 标签 + 状态指示器
  - 状态指示器使用 `NavState` enum: `NOT_STARTED`, `READY`, `IN_PROGRESS`, `COMPLETED`, `NEEDS_ATTENTION`, `EXPIRED`
  - 每个状态对应不同图标/颜色（不只用颜色 — 同时存在图标和文本）
  - 底部「折叠导航」按钮
  - 小于 1440px 宽时自动建议折叠
- **MIRROR**: 现有 `NavigationBar` 信号模式 (`page_changed` → `domain_changed`)
- **IMPORTS**: `from enum import IntEnum, Enum`; `from PyQt6 import QtCore, QtWidgets, QtGui`
- **GOTCHA**: 不使用 QSS 背景色直接硬编码；通过 `get_theme()` 获取 token。图标使用 SVG 或 Unicode 字符（后续可替换为真实图标文件）。NavState 颜色不能作为唯一状态表达。
- **VALIDATE**: 独立脚本创建 PrimaryNav 并验证 5 个 domain 按钮存在

### Task 2: Create AppBar widget
- **PRECHECK_AGENTS**: architect (新 Widget API + 项目健康状态集成) + tdd-guide (新功能，测试先于实现)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 创建 `views/platform/shell/app_bar.py`
- **IMPLEMENT**:
  ```python
  class AppBar(QtWidgets.QWidget):
      project_selected = QtCore.pyqtSignal(str)      # project path
      task_center_toggled = QtCore.pyqtSignal()
      settings_requested = QtCore.pyqtSignal()
      help_requested = QtCore.pyqtSignal()

      def __init__(self, parent=None): ...
      def set_project(self, name: str, health: str): ...
      def set_task_count(self, active: int): ...
      def clear_project(self): ...
  ```
  - 固定高度 48px
  - 左侧：Logo (24×24) + 应用名 "视觉算法平台"
  - 中间：当前项目下拉（项目名 + 健康状态图标）
  - 右侧：任务中心按钮（带数字气泡 `●2`）+ 设置 + 帮助
  - 无项目时隐藏项目中段，仅显示 Logo + 设置 + 帮助
  - 任务中心按钮：N>0 时高亮显示数字气泡
- **MIRROR**: 项目健康状态参考 `ProjectFileStore.validate_project()` 返回的 issues 列表
- **IMPORTS**: `from PyQt6 import QtCore, QtWidgets, QtGui`
- **GOTCHA**: 整个 Bar 固定 48px，不给子元素设置可变高度。Logo 使用现有 `new_icon("icon")`。
- **VALIDATE**: 独立脚本创建 AppBar + set_project → 验证项目名显示正确

### Task 3: Create PageHeader widget
- **PRECHECK_AGENTS**: architect (新 Widget API + 标题区统一标准) + tdd-guide (新功能，测试先于实现)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 创建 `views/platform/shell/page_header.py`
- **IMPLEMENT**:
  ```python
  class PageHeader(QtWidgets.QWidget):
      primary_action_triggered = QtCore.pyqtSignal()

      def __init__(self, parent=None): ...
      def set_title(self, title: str): ...
      def set_subtitle(self, subtitle: str): ...
      def set_breadcrumb(self, items: list[tuple[str, str]]): ...
          # items: [(label, target_domain_or_step), ...]
          # e.g. [("实例分割 v3", "task"), ("build-003", "build"), ("run-008", "run")]
      def set_status(self, status: str, actionable: bool = False): ...
      def set_primary_action(self, label: str, enabled: bool = True): ...
      def clear_primary_action(self): ...
      def set_state_summary(self, text: str): ...
          # "资产 17,888 | 已标注 12,310 | 当前任务：实例分割 v3"
  ```
  - 固定高度 56px (48-64px 可变范围)
  - 左：标题（大号 18px） + 副标题（小号 12px）
  - 中下：面包屑（可点击来源链）
  - 中：状态指示
  - 右：唯一主按钮
  - 仅在有项目时显示内容
- **MIRROR**: PRD 第 6.1 节页面标题区标准
- **IMPORTS**: `from PyQt6 import QtCore, QtWidgets, QtGui`
- **GOTCHA**: 面包屑项可点击（使用 QPushButton flat + link 样式），点击后 emit signal 到 WorkbenchWindow 导航。主按钮描述用户结果而非动作（"开始训练" 而非 "执行"）。
- **VALIDATE**: 独立脚本创建 PageHeader → set_title + set_breadcrumb → 验证布局

### Task 4: Create StatusBar widget
- **PRECHECK_AGENTS**: architect (新 Widget API + 多段状态设计) + tdd-guide (新功能，测试先于实现)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 创建 `views/platform/shell/status_bar.py`
- **IMPLEMENT**:
  ```python
  class StatusBar(QtWidgets.QWidget):
      save_retry_requested = QtCore.pyqtSignal()

      def __init__(self, parent=None): ...
      def set_save_status(self, status: str): ...
          # "已保存" / "正在保存…" / "保存失败—重试"
      def set_device(self, device: str): ...        # "CPU" / "CUDA: RTX 4090"
      def set_background_tasks(self, count: int, summary: str = ""): ...
      def set_offline_status(self, offline: bool): ...
  ```
  - 固定高度 24px
  - 从左到右：保存状态 | 设备 | 后台任务 | 离线状态
  - 保存失败时红色高亮 + 可点击重试（emit save_retry_requested）
- **MIRROR**: 现有 `QStatusBar.showMessage()` 使用 → 替换为自定义多段显示
- **IMPORTS**: `from PyQt6 import QtCore, QtWidgets`
- **GOTCHA**: 不承载复杂操作。每段为 QLabel + QPushButton(flat) 组合。不溢出的前提下最多 4 段。
- **VALIDATE**: 独立脚本创建 StatusBar → set 各状态值 → 验证可见

### Task 5: Create SubNav widget (data prep sub-steps)
- **PRECHECK_AGENTS**: architect (新 Widget API + 子步骤路由设计) + tdd-guide (新功能，测试先于实现)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 创建 `views/platform/shell/sub_nav.py`
- **IMPLEMENT**:
  ```python
  class SubStep(IntEnum):
      IMPORT = 0
      TASK = 1
      LABEL = 2
      DATASET_BUILD = 3

  SUBSTEP_LABELS_ZH = {
      SubStep.IMPORT: "导入数据",
      SubStep.TASK: "任务与标签",
      SubStep.LABEL: "标注",
      SubStep.DATASET_BUILD: "数据集构建",
  }

  class SubNav(QtWidgets.QWidget):
      step_changed = QtCore.pyqtSignal(int)   # SubStep value

      def __init__(self, parent=None): ...
      def set_current_step(self, step: SubStep): ...
      def set_step_state(self, step: SubStep, state: NavState): ...
      def set_summary(self, text: str): ...
          # "资产 17,888 | 已标注 12,310 | 待复核 420 | 当前任务：实例分割 v3"
  ```
  - 仅在"数据准备"域内显示
  - 4 步水平步骤：导入数据 → 任务与标签 → 标注 → 数据集构建
  - 每步间用 `→` 分隔
  - 每步显示状态指示器（复用 PrimaryNav 的 NavState）
  - 底部一行统计摘要
  - 用户可点击跳转已满足条件的步骤
- **MIRROR**: 现有 `NavigationBar` 步骤按钮 + 箭头模式
- **IMPORTS**: `from PyQt6 import QtCore, QtWidgets`; `from .primary_navigation import NavState`
- **GOTCHA**: SubNav 不是独立的 QWidget 页面，而是嵌入在 DATA_PREP 域的内容区顶部。通过 WorkbenchWindow 的布局控制显隐。
- **VALIDATE**: 独立脚本创建 SubNav → 设置 4 步状态 → 验证显示

### Task 6: Create shell __init__.py
- **PRECHECK_AGENTS**: (none — 包导出注册，无架构/安全/测试风险)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer (验证无循环导入)
- **ACTION**: 创建 `views/platform/shell/__init__.py` 包导出
- **IMPLEMENT**:
  ```python
  from anylabeling.views.platform.shell.app_bar import AppBar
  from anylabeling.views.platform.shell.primary_navigation import (
      Domain, NavState, PrimaryNavigation,
  )
  from anylabeling.views.platform.shell.page_header import PageHeader
  from anylabeling.views.platform.shell.status_bar import StatusBar
  from anylabeling.views.platform.shell.sub_nav import SubNav, SubStep

  __all__ = [
      "AppBar", "Domain", "NavState", "PageHeader",
      "PrimaryNavigation", "StatusBar", "SubNav", "SubStep",
  ]
  ```
- **GOTCHA**: 验证无循环导入（shell 包不应导入 workbench_window）
- **VALIDATE**: `python -c "from anylabeling.views.platform.shell import AppBar, PrimaryNavigation, NavState"`

### Task 7: Refactor WorkbenchWindow to use new Shell
- **PRECHECK_AGENTS**: architect (Shell 布局重构 + 信号连线契约) + tdd-guide (大规模重构，回归测试先行) + security-reviewer (项目路径传递 + QWidget 生命周期)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer + security-reviewer
- **ACTION**: 重构 `workbench_window.py` — 替换整个 Shell 布局
- **IMPLEMENT**:
  1. 移除 `NavigationBar`, `QTreeWidget` 项目树, `QTextEdit` inspector, `JobConsole` 从布局
  2. 新增布局结构:
     ```python
     # 主垂直布局
     main_vlayout.addWidget(self._app_bar)                    # 48px 固定
     h_layout = QHBoxLayout()
     h_layout.addWidget(self._primary_nav)                    # 176px → 56px
     right_vlayout = QVBoxLayout()
     right_vlayout.addWidget(self._page_header)               # 56px
     right_vlayout.addWidget(self._sub_nav)                   # 条件显示
     right_vlayout.addWidget(self._pages, stretch=1)          # 原 QStackedWidget
     right_vlayout.addWidget(self._status_bar)                # 24px 固定
     h_layout.addLayout(right_vlayout, stretch=1)
     main_vlayout.addLayout(h_layout, stretch=1)
     ```
  3. 连线所有 Shell 信号:
     - `primary_nav.domain_changed → _on_domain_changed`
     - `app_bar.task_center_toggled → _on_task_center_toggled`
     - `sub_nav.step_changed → _on_sub_step_changed`
  4. 保留 `set_project()` 方法中的核心逻辑 — 只修改 Shell 显示调用
  5. 修改 `_navigate_to()` 改为 domain + sub_step 双级导航
  6. 标注页面时连接 `label_workspace.nav_fold_requested` → `primary_nav.set_folded()`
  7. 窗口标题统一为 "项目名 — X-AnyLabeling"
  8. `QTreeWidget` 从布局移除但保留代码（Phase 3 清理）
  9. `Inspector` 从布局移除但保留代码（Phase 3 迁移到标注属性区）
- **MIRROR**: 现有 `workbench_window.py:47-135` 布局
- **IMPORTS**: 更新为 `from anylabeling.views.platform.shell import ...`
- **GOTCHA**:
  - 窗口最小尺寸增加到 1280×720（PRD 规范）
  - PipelineStep 枚举继续用于 _pages QStackedWidget 索引（保持兼容）
  - 所有 _create_*_workspace 方法和 _replace_page 方法保持不变
  - SubNav 仅在 DATA_PREP 域内可见
  - JobConsole 从布局移除，其功能由 Phase 2b TaskCenterDrawer 接管
- **VALIDATE**: `python -c "from anylabeling.views.platform.workbench_window import WorkbenchWindow"` + 现有测试通过

### Task 8: Mark NavigationBar as deprecated
- **PRECHECK_AGENTS**: security-reviewer (导入兼容性 + PipelineStep 保留影响)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 更新 `navigation_bar.py` 文档和注解
- **IMPLEMENT**:
  1. 更新模块 docstring 为 `"""Navigation bar — DEPRECATED. Use views/platform/shell/ instead."""`
  2. Import `warnings` 模块
  3. `PipelineStep` 和 `step_label` 保持不变（继续被 workbench_window 使用）
  4. `NavigationBar` 类保留（旧测试可能引用），添加 deprecation docstring
- **MIRROR**: 现有注释风格
- **IMPORTS**: `import warnings`
- **GOTCHA**: PipelineStep 仍被 workbench_window.py _pages QStackedWidget 使用，不可移除。旧常量别名 (DATA, LABEL, TRAIN 等) 保留但添加 deprecation 注释。
- **VALIDATE**: `python -c "from anylabeling.views.platform.navigation_bar import PipelineStep, step_label"` — 不 warning

### Task 9: Add LabelWorkspace nav fold signal
- **PRECHECK_AGENTS**: architect (信号契约 + showEvent/hideEvent 生命周期设计)
- **IMPLEMENTATION_AGENT**: 主会话
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer
- **ACTION**: 在 LabelWorkspace 添加 `nav_fold_requested` signal
- **IMPLEMENT**:
  ```python
  # 在 LabelWorkspace 类中添加
  nav_fold_requested = QtCore.pyqtSignal(bool)  # True = fold navigation

  def showEvent(self, event):
      super().showEvent(event)
      self.nav_fold_requested.emit(True)

  def hideEvent(self, event):
      super().hideEvent(event)
      self.nav_fold_requested.emit(False)
  ```
  - WorkbenchWindow 连接此 signal 到 `primary_nav.set_folded()`
- **MIRROR**: 现有 signal 模式 `evaluate_requested = pyqtSignal(...)`
- **IMPORTS**: `from PyQt6 import QtCore`
- **GOTCHA**: 仅标注页面需要三栏布局 → 折叠导航释放空间。其他页面不接此 signal。
- **VALIDATE**: 切换到标注页面 → PrimaryNav 折叠为 56px；离开 → 恢复 176px

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected |
|---|---|---|
| PrimaryNav has 5 domains | create widget | 5 buttons labeled correctly |
| PrimaryNav domain_changed | click "数据准备" | emits Domain.DATA_PREP |
| PrimaryNav fold/unfold | set_folded(True) | width=56px, labels hidden |
| AppBar shows project | set_project("TestProj", "healthy") | project name visible |
| AppBar task count bubble | set_task_count(3) | "●3" visible |
| PageHeader title + breadcrumb | set_title("训练") + set_breadcrumb(...) | both visible |
| PageHeader primary action | set_primary_action("开始训练") | button visible with correct label |
| StatusBar save status | set_save_status("保存失败—重试") | red text + is clickable |
| SubNav 4 steps visible | create widget | 4 step labels visible with arrows |
| SubNav step click emits | click step 2 | emits SubStep.LABEL |

### Edge Cases Checklist
- [ ] 无项目时 AppBar 隐藏项目中段
- [ ] 无项目时 PageHeader 显示引导信息
- [ ] 窗口缩到 1280×720 → PrimaryNav 自动折叠
- [ ] DPI 125%/150%/200% → 所有 Shell 组件高度不变
- [ ] 切换项目 → 清除所有状态指示器
- [ ] 数据准备域外 → SubNav 隐藏

---

## Validation Commands

```bash
# Shell 组件导入验证
python -c "from anylabeling.views.platform.shell import AppBar, PrimaryNavigation, PageHeader, StatusBar, SubNav"

# NavigationBar 兼容性
python -c "from anylabeling.views.platform.navigation_bar import PipelineStep, step_label"

# 全量回归
python -m pytest tests/ -x -m "not slow" -k "not test_format_metric"
```

---

## Agent Orchestration

> 遵循 `.claude/PRPs/agent-orchestration-rules.md` 强制编排规则。

### Core Rules (21 条铁律)

1. 主会话负责整体调度和最终决策，不得独自完成全部分析+实现+审查。
2. 每个 Task 开始前必须调用该 Task 的 PRECHECK_AGENTS。
3. 需要架构判断时调用 `architect`。
4. 新功能或 Bug 修复必须先调用 `tdd-guide`。
5. 生产代码默认由主会话串行写入。
6. `tdd-guide` 只有在 WRITE_SCOPE 明确包含测试文件时，才能修改测试文件。
7. 完成 Python 修改后必须调用 `python-reviewer`。
8. 每个 Task 完成后必须调用 `code-reviewer`。
9. 涉及文件路径、子进程、模型加载、用户输入和本地数据时，必须调用 `security-reviewer`。
10. 构建失败时调用对应 `build-error-resolver` 分析根因。
11. 所有专业 Agent 必须返回结构化报告。
12. 审核 Agent 默认只读，不允许直接修改源码。
13. 主会话根据专业 Agent 报告实施修复。
14. 禁止两个 Agent 同时修改同一个文件。
15. 独立只读分析可以并行；写入任务必须串行。
16. 任何 Agent 不得执行 `git push`, `merge`, `rebase`, `reset`, `clean`。
17. 提交仅由主会话在 Phase 完成后统一执行。
18. Auto 模式只用于权限自动判断，不得替代 Agent 编排。
19. 最终 Implementation Report 必须增加 Agent Execution Log。

### Agent Assignment

| Agent | Role | Tasks | Scope |
|-------|------|-------|-------|
| `architect` | 架构审查 | T1, T2, T3, T4, T5, T7, T9 | 6 个新 Widget API + WorkbenchWindow 重构 + LabelWorkspace 信号 |
| `tdd-guide` | 测试驱动 | T1, T2, T3, T4, T5, T7 | 新 Widget 测试先行 + Shell 重构回归测试 |
| `security-reviewer` | 安全审查 | T7, T8 | WorkbenchWindow 路径处理 + NavigationBar deprecated 导入 |
| `code-reviewer` | 代码审查 | All | 每个 Task 完成后强制审查 |
| `python-reviewer` | Python 审查 | All | PEP 8 合规 + PyQt6 惯用法检查 |

### EXECUTION_MODE

**Sequential** — Task 串行执行：T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9。

每个 Task 内部：
- **PRECHECK** Agent 可并行调用（只读互不干扰）
- **IMPLEMENT** 由主会话串行写入（同一时间只有一个写入者）
- **POST_REVIEW** Agent 可并行调用（只读互不干扰）

### WRITE_SCOPE

| Agent | Permitted Files | Constraint |
|--------|-----------------|------------|
| 主会话 | `anylabeling/` 下所有源码 + `docs/` 下文档 | 生产代码与文档唯一写入者 |
| `tdd-guide` | `tests/` 下测试文件 | 仅限测试文件，不得修改生产代码 |
| `architect` | 只读 | 不得修改任何文件 |
| `code-reviewer` | 只读 | 不得修改任何文件 |
| `python-reviewer` | 只读 | 不得修改任何文件 |
| `security-reviewer` | 只读 | 不得修改任何文件 |

### Agent Execution Log

| Task | Agent | 阶段 | 输出摘要 | 是否采纳 | 验证结果 |
|------|-------|------|----------|----------|----------|
| ... | ... | ... | ... | ... | ... |

---

## Acceptance Criteria
- [ ] 一级导航不超过 5 项
- [ ] AppBar 显示当前项目名和健康状态
- [ ] PageHeader 统一出现在所有页面顶部
- [ ] 每页最多一个主按钮（位于 PageHeader 右侧）
- [ ] StatusBar 显示保存状态、设备、后台任务数、离线状态
- [ ] 数据准备域内显示 4 步子导航
- [ ] 标注页面自动折叠一级导航为 56px
- [ ] 1280×720 最小窗口下所有控件可见
- [ ] 所有已有测试无回归

## Notes
- Phase 2a 是纯 Shell 骨架 — 所有现有页面内容通过 QStackedWidget 保持不变
- PrimaryNav 状态指示器为静态占位（Phase 2b WorkflowState 驱动动态状态）
- TaskCenterDrawer 仅创建容器 + 占位按钮（Phase 2b 实现完整功能）
- QTreeWidget/Inspector 从布局移除但代码保留（Phase 3 彻底清理）
- 窗口最小尺寸从 1200×800 提高到 1280×720（PRD 规范）
