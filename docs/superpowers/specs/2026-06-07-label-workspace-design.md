# Design Spec: Label Workspace Integration

**Date**: 2026-06-07
**Branch**: `vision_platfrom`
**Status**: approved

## Summary

为 X-AnyLabeling 平台的 6 步流水线（数据→标注→训练→评估→推理→导出）创建原生 LabelWorkspace 页面，将现有 `LabelingWidget` + `Canvas` 标注组件完整嵌入平台工作区，通过 AnnotationAdapter 桥接平台领域模型，实现任务驱动的标注工具筛选。

## Design Principles

1. **原有标注代码一行不改** — `Canvas`、`Camera2D`、`Shape`、`LabelingWidget` 全部原样复用
2. **平台层薄包装** — 新增代码仅做嵌入、桥接、筛选，不侵入原有交互逻辑
3. **任务驱动** — 根据 `TaskSpec.family` 控制可见的标注工具，非当前任务类型自动隐藏
4. **零破坏** — 现有 `add_label_workspace()` API 保持不变，LabelWorkspace 作为新的默认实现

## Architecture

```
WorkbenchWindow
├── NavigationBar (Data→Label→Train→Evaluate→Infer→Export)
├── QStackedWidget
│   ├── [0] ProjectHomeWidget
│   ├── [1] LabelWorkspace          ← NEW (was DataWorkspace placeholder)
│   ├── [2] TrainWorkspace
│   ├── [3] EvaluateWorkspace
│   ├── [4] InferWorkspace
│   └── [5] ExportWorkspace
├── Explorer QTreeWidget
├── Inspector QTextEdit
└── JobConsole

LabelWorkspace (new file: views/platform/label_workspace.py)
├── AssetListPanel                   ← 资产列表 + 标注状态图标
│   ├── Search/filter bar
│   ├── QListWidget (文件列表)
│   └── Progress bar (已标注/总计)
├── QSplitter
│   ├── [Embedded LabelingWidget]   ← 原封不动复用
│   │   ├── Canvas                  ← 一行不改
│   │   ├── ToolBar                 ← 按钮显隐由外部控制
│   │   └── LabelDialog             ← 原有标签选择
│   └── InspectorPanel              ← 属性查看/编辑
└── StatusBar (文件名、尺寸、标注数)

AnnotationAdapter (new file: platform/application/annotation_adapter.py)
├── load_annotation(asset_id) → 注入 shapes 到 LabelingWidget
├── save_annotation(asset_id, shapes) → AnnotationDocument → JSON
├── task_family_to_shape_types(family) → list[str]
└── shape_to_annotation_object(shape) → AnnotationObject
```

## Component Details

### 1. LabelWorkspace (`views/platform/label_workspace.py`)

**职责**: 平台原生 QWidget 页面，组合资产列表 + 标注画布 + 属性面板

**关键方法**:
- `set_project_context(project_path, task_spec)` — 初始化项目上下文
- `_on_asset_selected(asset_path)` — 切换标注图片
- `_on_annotation_changed()` — 形状变更时触发保存
- `_apply_task_tool_filter(family)` — 根据任务类型筛选工具

**布局**: QSplitter 水平分割，左侧 AssetListPanel(200px) + 中央 LabelingWidget(stretch=3) + 右侧 Inspector(220px)

### 2. AssetListPanel

**职责**: 显示 `assets/` 目录下的所有图片，标注状态图标

**状态图标**:
- ✅ 绿色 — 已标注（`annotations/{asset_id}.json` 存在且有 shapes）
- 🔄 黄色 — 标注中（有部分标注）
- ⭕ 灰色 — 未标注

**底部统计**: `总计: N | 已标注: M | 进度: K%`

### 3. AnnotationAdapter (`platform/application/annotation_adapter.py`)

**职责**: 薄桥接层，连接 `views/labeling/Shape` 和 `platform/domain/AnnotationObject`

**核心映射**:

| Shape (views) | AnnotationObject (platform) |
|---|---|
| `shape.shape_type` ("rectangle") | `geometry_type` ("bbox_xyxy") |
| `shape.shape_type` ("rotation") | `geometry_type` ("obb_polygon") |
| `shape.shape_type` ("polygon") | `geometry_type` ("polygon") |
| `shape.shape_type` ("point") | `geometry_type` ("keypoints") |
| `shape.points` | `geometry` (转换) |
| `shape.label` | `label_id` (通过 TaskSpec.labels 查找) |

### 4. Task Family → Shape Type Mapping

| TaskSpec.family | Allowed shape_types | geometry_type |
|---|---|---|
| `classification` | (none) | (image_labels only) |
| `detection_hbb` | `["rectangle"]` | `bbox_xyxy` |
| `detection_obb` | `["rotation"]` | `obb_polygon` |
| `instance_segmentation` | `["polygon"]` | `polygon` |
| `pose` | `["point"]` | `keypoints` |
| `semantic_segmentation` | `["polygon"]` | `polygon`, `raster_mask` |
| `anomaly` | `["rectangle", "polygon"]` | `bbox_xyxy`, `polygon` |

### 5. 标注增删改

所有操作由原有 Canvas/LabelingWidget 原生支持，无需新增代码：

- **增**: Canvas 绘图 → LabelDialog 选标签 → shapes 列表新增 → AnnotationAdapter 保存
- **删**: Canvas Delete 键 / 右键菜单 → shapes 列表移除 → AnnotationAdapter 保存
- **改**: 拖拽顶点/移动/Double-click 编辑标签 → shapes 更新 → AnnotationAdapter 保存

## Data Flow

```
打开项目
  → WorkbenchWindow.set_project(path)
    → LabelWorkspace.set_project_context(path, task_spec)
      → _apply_task_tool_filter(task_spec.family)
        → ToolBar 按钮显隐
      → _scan_assets() → AssetListPanel 填充

选择资产
  → AssetListPanel._on_click(asset_path)
    → LabelingWidget.loadFile(asset_path)
    → AnnotationAdapter.load(asset_id)
      → XLabelCodec.load_annotations(ann_path) → AnnotationDocument
      → AnnotationDocument.objects → Shape 列表
      → LabelingWidget.shapes = shapes

标注变更
  → Canvas.shape_moved / selection_changed / shape deleted
    → _on_annotation_changed()
      → AnnotationAdapter.save(asset_id, shapes)
        → shapes → AnnotationObject 列表 → AnnotationDocument
        → XLabelCodec.save_annotations(doc, ann_path)
      → AssetListPanel 更新状态图标
```

## Files to Create

| File | Lines (est.) | Purpose |
|---|---|---|
| `anylabeling/views/platform/label_workspace.py` | ~300 | LabelWorkspace page widget |
| `anylabeling/platform/application/annotation_adapter.py` | ~150 | Shape ↔ AnnotationObject bridge |

## Files to Modify

| File | Change | Lines |
|---|---|---|
| `anylabeling/views/platform/workbench_window.py` | `_create_pages()` 创建 LabelWorkspace；`set_project()` 初始化上下文；移除旧的 DataWorkspace→LABEL 占位逻辑 | ~20 |
| `anylabeling/views/platform/__init__.py` | 导出 LabelWorkspace | +1 |

## Existing Files NOT Touched

以下文件保持完全不变：

- `anylabeling/views/labeling/widgets/canvas.py` (2400+ lines)
- `anylabeling/views/labeling/label_widget.py`
- `anylabeling/views/labeling/label_wrapper.py`
- `anylabeling/views/labeling/label_file.py`
- `anylabeling/views/labeling/shape.py`
- `anylabeling/views/labeling/viewport/camera.py`
- `anylabeling/views/labeling/widgets/toolbar.py`
- `anylabeling/views/labeling/widgets/label_dialog.py`
- `anylabeling/platform/application/annotation_service.py` (XLabelCodec)
- `anylabeling/platform/domain/annotation.py`

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Canvas ToolBar 按钮名称不匹配（旧标注软件的按钮可能没有统一命名） | MEDIUM | 先 grep ToolBar 代码确认所有按钮的 objectName/引用路径 |
| LabelingWidget 初始化依赖旧配置文件格式 | MEDIUM | 通过 `project_context` dict 传入平台配置，兼容原有 config |
| 标注保存时机（自动 vs 手动）与用户预期不一致 | LOW | 采用变更即时保存策略（Canvas 信号驱动），符合原有行为 |
| DataWorkspace 被移除后影响现有数据集构建流程 | LOW | DataWorkspace 移至 DATA index，LabelWorkspace 占 LABEL index |

## Acceptance Criteria

- [ ] 打开项目后导航到"标注"页，显示资产列表和标注画布
- [ ] 根据 TaskSpec.family 只显示对应的标注工具按钮
- [ ] 选择资产后画布加载图片和已有标注
- [ ] 新增/删除/修改标注后自动保存到 `annotations/{asset_id}.json`
- [ ] 资产列表标注状态图标实时更新
- [ ] 原有所有 Canvas 交互（缩放/平移/polygon跟随鼠标/Undo-Redo/右键菜单）正常工作
- [ ] `detection_hbb` 项目只显示矩形工具
- [ ] `pose` 项目只显示关键点工具
- [ ] 其他 5 个 Workspace 不受影响
