<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~950 -->

# UI 层 (User Interface)

## 顶层窗口

| 窗口 | 文件 | 状态 |
|------|------|------|
| `MainWindow(QMainWindow)` | `views/mainwindow.py` | ✅ 标注中心模式 |
| `WorkbenchWindow(QMainWindow)` | `views/platform/workbench_window.py` | ✅ V4 平台模式 |

## 传统模式布局 (MainWindow)

```
MainWindow → QVBoxLayout → LabelingWrapper(QWidget)
  └── LabelingWidget(QWidget)                    ← 中心控制器
      ├── Canvas(QWidget)                        ← QPainter 绘制
      ├── ToolBar(QFrame)                        ← 左侧竖排
      ├── LabelListWidget (标注对象列表)
      ├── UniqueLabelQListWidget (标签列表)
      ├── AutoLabelingWidget → ModelDropdown
      ├── NavigatorWidget (缩略图导航)
      ├── ZoomWidget(QSpinBox) (缩放显示)
      └── 30+ 对话框: Settings, Chatbot, Classifier, VQA, PPOCR, ...
```

## V4 平台工作台布局

```
WorkbenchWindow
├── AppBar(QWidget)                  ← 48px 顶栏: 项目选择 + 任务中心
├── PrimaryNavigation(QWidget)       ← 5 域左侧导航 (替代旧 NavigationBar)
├── SubNav(QWidget)                 ← 域内子步骤导航
├── PageHeader(QWidget)             ← 56px 页面标题/副标题
├── QStackedWidget (9 页)
│   ├── [0] ProjectHomeWidget       ✅ 创建/打开项目
│   ├── [1] DataWorkspace           ✅ 数据概览 + ImportWorkspace
│   ├── [2] TaskConfigurator        ✅ 任务族配置 (动态)
│   ├── [3] LabelWorkspace          ✅ 嵌入 LabelingWidget
│   ├── [4] PreprocessWorkspace     ✅ 切分 + 分割 + 数据增强
│   ├── [5] TrainWorkspace          ✅ 超参数 + 监控 + 就绪检查
│   ├── [6] EvaluateWorkspace       ✅ 指标 + 混淆矩阵 + 误分类
│   ├── [7] ExportWorkspace         ✅ 格式选择 + 加密 + 部署
│   └── [8] ModelLibrary            ✅ 模型注册浏览 + 对比
├── StatusBar(QWidget)              ← 24px 底栏: 保存/设备/任务/状态
├── ErrorBanner(QWidget)            ← 可折叠错误/警告/信息横幅
└── TaskCenterDrawer(QWidget)       ← 滑出式任务进度面板
```

## Shell 组件 (`views/platform/shell/`) — V4 新导航

| 组件 | 文件 | 用途 |
|------|------|------|
| `AppBar` | `app_bar.py` | 项目名称, 任务中心按钮, 溢出菜单 |
| `PrimaryNavigation` | `primary_navigation.py` | 5 域导航: Project/DataPrep/Train/Eval/Export |
| `SubNav` | `sub_nav.py` | 域内子步骤二级导航 |
| `PageHeader` | `page_header.py` | 标题 + 副标题 + 行动栏 |
| `StatusBar` | `status_bar.py` | 保存状态/设备/任务/通用状态 |
| `ErrorBanner` | `error_banner.py` | 可关闭错误/警告/信息横幅 |
| `TaskCenterDrawer` | `task_center_drawer.py` | 作业进度滑出面板 |

## 工作区页面实现状态

| 页面 | 文件 | 行数 | 状态 |
|------|------|------|------|
| ProjectHome | `project_home.py` | — | ✅ 创建/打开/最近项目 |
| DataWorkspace | `data_workspace.py` | 159 | ✅ 数据概览 + 分割比例 |
| ImportWorkspace | `workspaces/import_workspace.py` | 803 | ✅ 完整导入管线 |
| TaskConfigurator | `task_configurator.py` | — | ✅ 动态任务族配置 |
| LabelWorkspace | `label_workspace.py` | 526 | ✅ 资产列表 + 生命周期 |
| PreprocessWorkspace | `preprocess_workspace.py` | 310 | ✅ 切分 + 分割配置 |
| TrainWorkspace | `train_workspace.py` | 1174 | ✅ 超参数 + 监控 |
| EvaluateWorkspace | `evaluate_workspace.py` | 420 | ✅ 指标 + 混淆矩阵 |
| ExportWorkspace | `export_workspace.py` | 383 | ✅ 格式 + 加密 + 部署树 |
| ModelLibrary | `widgets/model_library.py` | 305 | ✅ 注册浏览 + 对比 |
| InferWorkspace | `infer_workspace.py` | 206 | ⚠️ 已实现但未实例化 |

## 标注 UI 组件树

| 组件 | 文件 | 类 | 状态 |
|------|------|-----|------|
| 中心控制器 | `labeling/label_widget.py` | `LabelingWidget(QWidget)` | ✅ |
| 包装器 | `labeling/label_wrapper.py` | `LabelingWrapper(QWidget)` | ✅ |
| 画布 | `labeling/widgets/canvas.py` | `Canvas(QWidget)` | ✅ |
| 工具栏 | `labeling/widgets/toolbar.py` | `ToolBar(QFrame)` | ✅ |
| 形状数据 | `labeling/shape.py` | `Shape` | ✅ |
| 文件持久化 | `labeling/label_file.py` | `LabelFile` | ✅ |
| 格式转换 | `labeling/label_converter.py` | `LabelConverter` | 🗑️ 遗留 |
| 标注列表 | `labeling/widgets/label_list_widget.py` | `LabelListWidget` | ✅ |
| 标签列表 | `labeling/widgets/unique_label_qlist_widget.py` | `UniqueLabelQListWidget` | ✅ |
| 自动标注控件 | `labeling/widgets/auto_labeling/auto_labeling.py` | `AutoLabelingWidget` | ✅ |
| 设置系统 | `labeling/settings/` | SettingsController/Dialog/RuntimeApplier | ✅ |

## 设置系统 (`views/labeling/settings/`)

| 文件 | 类 | 说明 |
|------|-----|------|
| `schema.py` | `SettingField`, `SETTINGS_FIELDS` | 设置字段定义 |
| `controller.py` | `SettingsController(QObject)` | 防抖保存, 字段变更信号 |
| `dialog.py` | `SettingsDialog(QDialog)` | 多页设置对话框 + 导航 |
| `editors.py` | `ColorRgbaEditor`, `ShortcutLineEditor` 等 | 自定义编辑器 |
| `runtime_applier.py` | `SettingsRuntimeApplier(QObject)` | 运行时应用设置变更 |

## 视口渲染路径 (活跃路径)

```
Canvas.paintEvent()
  → Camera2D.visible (图像坐标下的 RectF)
  → QImageRegionProvider.read_region(rect_l0, target_size)
    → _ensure_pyramid()    ← 惰性构建, 4 层, 256 MB/层
    → _select_level()      ← 最近 1:1 密度比
    → _read_from_level()   ← 从缓存的 QPixmap 复制 + 缩放
  → QPainter.drawPixmap()
```

## 平台控件 (`views/platform/widgets/`)

| 控件 | 用途 |
|------|------|
| `AssetFilterBar` / `AssetListModel` | 资产过滤 + 虚拟列表 |
| `TrainingMonitor` | 实时 matplotlib 损失/mAP 曲线 |
| `MetricsPlotWidget` | 指标可视化 |
| `EvalReportWidget` | 评估报告 (多页) |
| `MisclassGallery` | 误分类样本网格 |
| `TrainReadinessWidget` | 训练前检查清单 (红绿灯卡片) |
| `TileInspectorPanel` / `TilePreviewWidget` | 切片检查 + 预览 |
| `InferenceViewerWidget` | 推理结果预览 (bbox 叠加) |
| `ModelLibrary` | 模型注册浏览 |

## 视图模型 (`views/platform/view_models/`)

| VM | 绑定到 |
|----|--------|
| `DatasetViewModel` | PreprocessWorkspace |
| `ImportViewModel` | ImportWorkspace |
| `RunViewModel` | TrainWorkspace, ExportWorkspace |
| `TrainValidationViewModel` | TrainReadinessWidget |

## 未接入/死代码

| 组件 | 文件 | 备注 |
|------|------|------|
| `HugeImageCanvas` | `labeling/widgets/huge_image_canvas.py` | pyqtgraph 实现, 有测试, 从未导入 |
| `TileCache` | `labeling/viewport/tile_cache.py` | LRU 字节淘汰, 零消费者 |
| `tiles_for_rect()` | `labeling/viewport/tile_grid.py` | 零消费者 |
| `InferWorkspace` | `platform/infer_workspace.py` | 从未实例化 |
| `NavigationBar` (8-step) | `platform/navigation_bar.py` | 🗑️ 被 PrimaryNavigation (5-domain) 替代 |
| `LabelConverter` | `labeling/label_converter.py` | 🗑️ 用 XLabelCodec 替代 |
