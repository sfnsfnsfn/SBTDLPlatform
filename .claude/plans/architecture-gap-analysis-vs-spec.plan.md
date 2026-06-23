# Plan: 架构差距分析 — 当前工程 vs 产品交互优化方案

**Source Spec**: `docs/superpowers/specs/2026-06-07-platform-interaction-optimization.md`
**Complexity**: Large
**Created**: 2026-06-07

---

## 1. 评估摘要

当前 V4 MVP 架构在 **领域模型层** 和 **服务层** 已具备方案 70% 的能力基础，但 **视图层** 严重不足。核心结论：

| 层 | 完整度 | 说明 |
|---|---|---|
| Domain (领域模型) | **85%** | 缺 SplitManifest/AugmentationPlan 独立模型, TaskSpec 缺 OCR family |
| Application (服务层) | **75%** | 缺 ImportService, 训练/评估/导出服务已完备 |
| Infrastructure (基础设施) | **80%** | 文件存储/哈希/原子写/子进程已完备，缺导入扫描 |
| Adapters (适配器) | **60%** | 仅 Ultralytics YOLO, 缺多算法接入的 UI 呈现 |
| Tiling (切片) | **90%** | SAHI 集成完整，5 种 label splitter 齐备 |
| Views (视图层) | **40%** | 6 页骨架存在，缺 ImageImport/TaskConfigurator/PreprocessWorkspace 三页 |

**综合评定**: 服务层架构设计良好，可以直接支撑 8 步流水线的后端逻辑。主要工作集中在 **视图层的三页新建 + 四页增强 + 导航重构**。

---

## 2. 逐步骤差距分析

### STEP 1: 创建工程 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 轻量两步创建（名称+位置） | `NewProjectDialog` 强制选任务类型+配置标签 | 需重构为名称+描述+位置三步，任务类型/标签移到后续 | Critical |
| 可选快速模板 | 无 | 需新增 5 个预设模板 radio 组 | High |
| 创建后跳转导入 | 创建后直接激活项目 | 需修改 WorkbenchWindow 流程控制 | Medium |
| 工程描述字段 | `project.json` 无 description 字段 | `ProjectFileStore.create_project` 和 `project.json` 需扩展 | Low |

**涉及文件**:
- 修改: `views/platform/new_project_dialog.py` — 重做 UI
- 修改: `platform/infrastructure/project_file_store.py` — 加 description + 可选 template
- 修改: `views/platform/workbench_window.py` — 修改创建后流程

### STEP 2: 导入数据 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 拖拽导入图片/文件夹 | 不存在 | 全新功能 | Critical |
| SHA-256 自动去重 | `infrastructure/checksum.py` 有 `compute_sha256` | 已就绪，需要在 ImportService 中调用 | Low |
| 大图自动检测 (>2000px) | 不存在 | 需在导入扫描时读取尺寸并标记 `Asset.is_large` | High |
| 按文件夹名自动分组 | 不存在 | 需在导入时解析文件夹名 `Asset.group_id` | Medium |
| 导入缩略图预览 | 不存在 | 需新建 `ImportPreviewWidget` | Medium |
| 标注数据导入 (YOLO/COCO/VOC) | 格式转换器在 `views/common/converter.py` | 需暴露为 ImportService 接口 | Medium |
| 导入进度与统计 | 不存在 | 需在 ImportService 中计数组/去重数/大图数 | Low |
| ImageSource 注册 | `image_sources/` 有 file/tiff/qt/memory | 已就绪 | 完备 |

**涉及文件**:
- 新建: `views/platform/image_import_dialog.py` — 拖拽导入 UI
- 新建: `views/platform/widgets/import_preview.py` — 缩略图预览组件
- 新建: `platform/application/import_service.py` — 导入业务逻辑
- 新建: `platform/domain/import_config.py` — 导入配置

### STEP 3: 配置任务 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 独立 TaskConfigurator 页面 | 不存在 | 全新页面 | Critical |
| 任务类型智能推荐 | 不存在 | 需新增推荐逻辑（基于图片数/尺寸/已有标注） | Medium |
| 运行时任务类型切换 | `TaskSpec` 是 frozen dataclass | 需改为可修改或创建新版本 | High |
| 标签 CRUD + 快捷键 | `NewProjectDialog` 的标签表 | 可复用标签表逻辑 | Medium |
| 从文件夹/JSON/模型导入标签 | 不存在 | 需新增标签导入逻辑 | Medium |
| TaskSpec OCR family | 只有 7 种，缺 `ocr` | 扩展 `TaskSpec.family` Literal | Low |

**涉及文件**:
- 新建: `views/platform/task_configurator.py` — 任务配置页面
- 修改: `platform/domain/task.py` — TaskSpec 加 ocr family + version 字段
- 修改: `views/platform/navigation_bar.py` — 8 步导航
- 修改: `views/platform/workbench_window.py` — 注册新页面

### STEP 4: 数据标注 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 智能预标注（单图） | AI auto-labeling 50+ 模型存在 | 可复用 `services/auto_labeling/` | 完备 |
| 批量预标注（全部未标注） | 不存在 | 需新增批量推理循环 + 进度条 | High |
| 标注建议（AI 提案+确认） | 不存在 | 需新增候选框交互模式 | Medium |
| 标注进度统计 | 不存在 | 需在 LabelWorkspace 底部加状态栏 | Medium |
| 标注状态图标 | 部分存在 | `AnnotationAdapter.load_annotations_for_asset` 可检测 | Medium |
| 快捷键驱动 | Canvas 已有部分快捷键 | 需补充标签快捷键绑定 | Low |

**涉及文件**:
- 修改: `views/platform/label_workspace.py` — 增加 AI 按钮 + 状态栏 + 进度
- 新建: `platform/application/batch_labeling_service.py` — 批量预标注

### STEP 5: 数据预处理 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 独立 PreprocessWorkspace | 不存在 | 全新页面 | Critical |
| 大图切片配置 (可视化) | `DatasetBuildService` 有完整 tiling | 后端完备，只需 UI | Medium |
| 切片参数智能推荐 | 不存在 | 需新增推荐逻辑 | Medium |
| 数据切分配置 (train/val/test) | `DatasetBuildService._assign_splits` 支持 | 后端完备 | 完备 |
| 数据增强配置 | 不存在 | 需新增增强参数 UI | High |
| SplitManifest 持久化 | `split_manifest.jsonl` 在 build 时写入 | 已实现 | 完备 |
| 切分预览 | 不存在 | 需显示预估切分数量 | Low |

**涉及文件**:
- 新建: `views/platform/preprocess_workspace.py` — 预处理配置页面
- 新建: `platform/domain/preprocess_config.py` — 预处理配置领域模型
- 修改: `views/platform/data_workspace.py` — 简化为纯数据概览

### STEP 6: 模型训练 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 模型算法选择 (多算法) | 仅 Ultralytics YOLO 系列 | 需暴露 `AlgorithmRegistry.for_task()` 到 UI | Medium |
| 模型规模推荐 | 不存在 | 需新增推荐逻辑 | Low |
| 参数智能推荐 | 不存在 | 需基于数据集特征推荐 | Medium |
| 实时训练监控 | `JobConsole` 轮询 job 状态 | 需改为实时 Loss 曲线图 | High |
| 增量训练 | 不存在 | 需支持从 best.pt 继续训练 | Medium |
| 训练队列 | `JobService` 支持并发 job | 已支持 | 完备 |

**涉及文件**:
- 修改: `views/platform/train_workspace.py` — 多算法选择 + 参数推荐
- 新建: `views/platform/widgets/training_monitor.py` — 实时曲线

### STEP 7: 模型验证 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 量化指标展示 | mAP/precision/recall 解析完成 | 完备 | 完备 |
| 混淆矩阵可视化 | `confusion_matrix.npy` 已保存 | 需渲染为 heatmap 图片 | Medium |
| Grad-CAM 热力图 | 不存在 | 需新增热力图推理逻辑 | High |
| 逐类分析 | per_class_metrics.json 已解析 | 需逐类展示的表格 | Medium |
| 误判回流 (FP/FN复查队列) | 不存在 | 全新功能 | High |
| 多 Run 对比视图 | 不存在 | 需新增对比选择器 + 指标并排 | Medium |

**涉及文件**:
- 修改: `views/platform/evaluate_workspace.py` — 混淆矩阵渲染 + 逐类分析 + 对比
- 新建: `platform/application/misclassification_service.py` — 误判回流逻辑

### STEP 8: 模型部署 — 当前 vs 目标

| 需求 | 当前状态 | 差距 | 严重度 |
|------|----------|------|--------|
| 多格式选择 (ONNX/TRT/OpenVINO) | `ExportService` 仅 ONNX | 需扩展多格式支持 | High |
| 部署包生成 (含示例代码) | 不存在 | 全新功能 | High |
| 模型自动注册 | 不存在 | 需注册到自定义模型列表 | Medium |
| 模型加密 | 不存在 | 需新增密码保护逻辑 | Low |
| 推理示例代码 | 不存在 | 需生成 Python/C++ 示例 | Medium |

**涉及文件**:
- 修改: `views/platform/export_workspace.py` — 多格式选择 + 部署包
- 修改: `platform/application/export_service.py` — 扩展多格式
- 新建: `platform/application/model_registry_service.py` — 模型注册

---

## 3. 架构层面全局问题

### 3.1 NavigationBar — 6 步 改为 8 步

```
当前:  Data / Label / Train / Evaluate / Infer / Export  (6步)
目标:  Project / Import / Config / Label / Preprocess / Train / Evaluate / Export  (8步)
```

**NavigationBar** 需要完全重构步骤常量、状态管理、依赖检查。

### 3.2 TaskSpec 不可变性

`TaskSpec` 是 frozen dataclass — 这意味着用户无法在 STEP 3 修改任务类型后更新。方案有二:
- **方案 A**: 改为 mutable dataclass，加 `version: int` 追踪修改
- **方案 B**: 每次修改创建新的 TaskSpec 实例（推荐，保持不可变性）

### 3.3 WorkbenchWindow 流程控制

当前 `set_project()` 一次性初始化所有子页。8 步流水线需要:
- 项目打开后检测 `assets/` 是否为空，自动跳到 STEP 2
- 步骤间依赖检查（如 STEP 5 检查标注进度）
- 步骤状态持久化到 `project.json`

### 3.4 缺失的领域模型

| 模型 | 用途 | 优先级 |
|------|------|--------|
| `SplitManifest` | 数据切分清单（种子/哈希/分配） | P1 |
| `AugmentationPlan` | 数据增强配置 | P2 |
| `ImportConfig` | 导入配置 | P2 |
| `ModelRegistry` | 模型注册表 | P2 |
| `ReviewQueue` | 误判复查队列 | P2 |

---

## 4. Patterns to Mirror（现有代码规范）

| Category | Source | Pattern |
|----------|--------|---------|
| Naming | `views/platform/*_workspace.py` | 页面用 `*Workspace(QWidget)`, 对话框用 `*Dialog(QDialog)` |
| Naming | `platform/application/*_service.py` | 服务层用 `*Service` 类, 构造函数接收 `(job_service, project_root)` |
| Naming | `platform/domain/*.py` | dataclass 领域模型, frozen=True, 无 UI 依赖 |
| Errors | `dataset_build_service.py:142-170` | `ValueError` + 描述性消息, 在 service 层验证 |
| Logging | 全项目 | `logger = logging.getLogger(__name__)` 模块级 logger |
| Data access | `project_file_store.py` | `AtomicWriter.write_json()` 确保原子写入 |
| Data access | `manifest_store.py` | `ManifestStore.append_jsonl()` 追加 JSONL |
| Tests | 项目根 `tests/` 目录 | pytest + fixtures |
| I18n | `views/platform/i18n.py` | `tr("中文", "English")` 双语文案 |
| UI style | `views/platform/style.py` | `get_primary_button_style()` 等工厂函数 |
| Subprocess | `training_service.py:_build_train_command` | inline Python 脚本 + `sys.executable -c` |

---

## 5. Files to Change（完整清单）

### 新建文件 (12 个)

| File | Action | Why |
|------|--------|-----|
| `views/platform/image_import_dialog.py` | CREATE | STEP 2 拖拽导入 UI |
| `views/platform/widgets/import_preview.py` | CREATE | 导入缩略图网格组件 |
| `views/platform/task_configurator.py` | CREATE | STEP 3 任务配置页面 |
| `views/platform/preprocess_workspace.py` | CREATE | STEP 5 预处理独立页面 |
| `views/platform/widgets/training_monitor.py` | CREATE | STEP 6 实时训练曲线 |
| `platform/application/import_service.py` | CREATE | 导入业务逻辑 |
| `platform/application/batch_labeling_service.py` | CREATE | 批量预标注 |
| `platform/application/misclassification_service.py` | CREATE | 误判回流 |
| `platform/domain/import_config.py` | CREATE | 导入配置领域模型 |
| `platform/domain/preprocess_config.py` | CREATE | 预处理配置领域模型 |
| `platform/domain/split_manifest.py` | CREATE | 切分清单领域模型 |
| `platform/application/model_registry_service.py` | CREATE | 模型注册服务 |

### 修改文件 (11 个)

| File | Action | Why |
|------|--------|-----|
| `views/platform/new_project_dialog.py` | UPDATE | 简化为名称+描述+位置，移除任务类型/标签 |
| `views/platform/workbench_window.py` | UPDATE | 8 步流程控制，注册新页面，导入后检测 |
| `views/platform/navigation_bar.py` | UPDATE | 6 步改为 8 步，新步骤常量/状态 |
| `views/platform/label_workspace.py` | UPDATE | AI 预标注按钮，批量预标注，标注进度 |
| `views/platform/data_workspace.py` | UPDATE | 简化为纯数据概览，超参数移到预处理页 |
| `views/platform/train_workspace.py` | UPDATE | 多算法选择，参数推荐 UI |
| `views/platform/evaluate_workspace.py` | UPDATE | 混淆矩阵渲染，逐类分析，多 Run 对比 |
| `views/platform/export_workspace.py` | UPDATE | 多格式选择，部署包生成 |
| `platform/domain/task.py` | UPDATE | TaskSpec 加 ocr family + version 字段 |
| `platform/infrastructure/project_file_store.py` | UPDATE | project.json 加 description + import_state |
| `platform/application/export_service.py` | UPDATE | 多格式导出支持 |

---

## 6. Tasks — 实施任务分解

### Phase 1: 架构基础 (P0) — 打通 8 步流水线骨架

#### Task 1.1: 重构 NavigationBar 为 8 步
- **Action**: 更新步骤常量为 PROJECT/IMPORT/CONFIG/LABEL/PREPROCESS/TRAIN/EVALUATE/EXPORT，步骤状态管理 (completed/active/pending/disabled)，依赖检查逻辑
- **Mirror**: 现有 `NavigationBar` 的 `page_changed` 信号 + `set_current_page` 模式
- **Files**: `views/platform/navigation_bar.py`
- **Validate**: `python -c "from anylabeling.views.platform.navigation_bar import NavigationBar; nb = NavigationBar(); assert nb.page_count == 8"`

#### Task 1.2: 重构 NewProjectDialog 为轻量两步
- **Action**: 移除任务类型/标签配置，仅保留名称+描述+位置，新增可选快速模板 radio 组（带"稍后配置"选项），创建后跳转 STEP 2
- **Mirror**: 现有 `NewProjectDialog` 的双语 i18n 模式 + style 工厂函数
- **Files**: `views/platform/new_project_dialog.py`, `platform/infrastructure/project_file_store.py`
- **Validate**: Dialog 创建后 `get_result()` 返回 `(name, parent_dir, description, template_key_or_none)`

#### Task 1.3: 扩展 TaskSpec 领域模型
- **Action**: 加 `ocr` family、加 `version: int = 1`、保持 frozen（修改时创建新版本）
- **Mirror**: 现有 `TaskSpec` dataclass 模式
- **Files**: `platform/domain/task.py`
- **Validate**: `from anylabeling.platform.domain.task import TaskSpec; ts = TaskSpec(id="t1", family="ocr", labels=(), annotation_schema="xjson", primary_metric="accuracy")`

#### Task 1.4: 更新 WorkbenchWindow 流程控制
- **Action**: 注册 8 个页面、项目打开后检测 assets/ 是否为空自动跳 STEP 2、存储步骤状态到 project.json
- **Mirror**: 现有 `WorkbenchWindow.set_project()` 模式
- **Files**: `views/platform/workbench_window.py`
- **Validate**: 创建新项目后自动跳转到 STEP 2

### Phase 2: 导入+配置 (P0) — 方案 STEP 2 + STEP 3

#### Task 2.1: 新建 ImportService
- **Action**: 文件复制到 assets/（使用 `shutil.copy2`），SHA-256 去重（调用 `compute_sha256`），图像属性分析（cv2 读尺寸/通道/位深），大图标记 (>2000px 标记为 is_large)，按文件夹名分组 (设置 group_id)
- **Mirror**: 服务层构造函数模式 `(project_root)` + dataclass 返回值
- **Files**: `platform/application/import_service.py`, `platform/domain/import_config.py`
- **Validate**: `ImportService(project_root).import_images(paths=["/tmp/img1.jpg", "/tmp/dir/"])` 返回 ImportResult

#### Task 2.2: 新建 ImageImportDialog
- **Action**: 拖拽区域 (Qt dropEvent + mimeData)，文件选择器 (QFileDialog)，导入选项 checkbox 组（去重/分组/大图检测/标注导入），缩略图预览网格，底部统计栏
- **Mirror**: `NewProjectDialog` 的 modal dialog + i18n + style 模式
- **Files**: `views/platform/image_import_dialog.py`, `views/platform/widgets/import_preview.py`
- **Validate**: 从 WorkbenchWindow STEP 2 触发，导入后图片出现在 assets/ 且缩略图预览正确

#### Task 2.3: 新建 TaskConfigurator
- **Action**: 图片预览滚动区，任务类型下拉（8 种），标签 CRUD 表（复用 NewProjectDialog 的 table 逻辑），智能推荐提示，标签导入按钮，任务类型切换时提示影响
- **Mirror**: `DataWorkspace` 的 QWidget 嵌入模式
- **Files**: `views/platform/task_configurator.py`
- **Validate**: 从 STEP 3 进入，任务类型切换时标注工具自动适配

### Phase 3: 标注+预处理 (P1) — 方案 STEP 4 + STEP 5

#### Task 3.1: LabelWorkspace 增强
- **Action**: AI 智能预标注按钮（调用 `services/auto_labeling/`），批量预标注（遍历未标注 assets），标注进度条（底部），标注状态图标，快捷键增强
- **Mirror**: 现有 `LabelWorkspace` 的 QSplitter 布局 + 信号连接
- **Files**: `views/platform/label_workspace.py`, `platform/application/batch_labeling_service.py`
- **Validate**: 点击"批量预标注"后未标注图片被自动推理标注

#### Task 3.2: 新建 PreprocessWorkspace
- **Action**: 大图预览区（标记大图），切片参数配置（宽/高/重叠/边缘模式 + 推荐按钮），切分配置（策略/比例/种子 + 预览），增强配置 (checkbox 组)，一键构建按钮
- **Mirror**: `DataWorkspace` 的参数布局 + `DatasetBuildService.build()` 调用
- **Files**: `views/platform/preprocess_workspace.py`, `platform/domain/preprocess_config.py`
- **Validate**: 配置后在 STEP 5 点击构建触发 `DatasetBuildService.build()`

#### Task 3.3: DataWorkspace 简化为数据概览
- **Action**: 移除超参数配置 UI，保留数据统计/概览，引导用户到 PreprocessWorkspace
- **Mirror**: 现有 `DataWorkspace` 的数据扫描逻辑
- **Files**: `views/platform/data_workspace.py`
- **Validate**: DataWorkspace 不再包含切片/切分配置

### Phase 4: 训练+验证+导出增强 (P1-P2) — 方案 STEP 6-8

#### Task 4.1: TrainWorkspace 增强
- **Action**: 多算法选择（`AlgorithmRegistry.for_task(family)`），模型规模推荐（基于数据量），参数智能推荐，实时 Loss 曲线（读取 results.csv + matplotlib 嵌入）
- **Mirror**: 现有 `TrainWorkspace` 的三页结构 (Data/Config/Train)
- **Files**: `views/platform/train_workspace.py`, `views/platform/widgets/training_monitor.py`
- **Validate**: 选择不同算法时参数面板自动适配

#### Task 4.2: EvaluateWorkspace 增强
- **Action**: 混淆矩阵渲染为热力图 (matplotlib/seaborn)，逐类分析表格，多 Run 对比（双下拉选择器），误判回流面板
- **Mirror**: 现有 `EvaluateWorkspace` 的 `set_project_context()` 模式
- **Files**: `views/platform/evaluate_workspace.py`, `platform/application/misclassification_service.py`
- **Validate**: 混淆矩阵正确渲染，FP/FN 列表可加入复查队列

#### Task 4.3: ExportWorkspace 增强
- **Action**: 多格式 checkbox 组 (ONNX/TensorRT/OpenVINO/CoreML)，部署包内容预览，导出选项 (labels/preprocess/示例代码/加密)，模型自动注册
- **Mirror**: 现有 `ExportWorkspace` 的信号驱动模式
- **Files**: `views/platform/export_workspace.py`, `platform/application/export_service.py`, `platform/application/model_registry_service.py`
- **Validate**: 导出后 models/ 目录生成完整部署包

---

## 7. Validation

```bash
# 领域模型导入检查
python -c "from anylabeling.platform.domain import TaskSpec, Asset, AnnotationDocument, TilePlan, DatasetBuild, Run, ModelArtifact"

# 服务层导入检查
python -c "from anylabeling.platform.application import ImportService; print('ImportService OK')"

# 视图层导入检查
python -c "from anylabeling.views.platform.image_import_dialog import ImageImportDialog; print('ImageImportDialog OK')"
python -c "from anylabeling.views.platform.task_configurator import TaskConfigurator; print('TaskConfigurator OK')"
python -c "from anylabeling.views.platform.preprocess_workspace import PreprocessWorkspace; print('PreprocessWorkspace OK')"

# 8步导航检查
python -c "
from anylabeling.views.platform.navigation_bar import NavigationBar
nb = NavigationBar()
assert nb.page_count == 8, f'Expected 8, got {nb.page_count}'
print('Navigation OK')
"

# 全量测试
pytest tests/ -x --tb=short
```

---

## 8. Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| NavigationBar 6步改8步破坏现有页面引用 | Medium | 先加兼容常量，逐步迁移 |
| 导入大文件 (>2GB TIFF) 卡死 UI | Medium | ImportService 用 QThread 异步执行 |
| 多算法接入后端不统一 | High | 先用 AlgorithmRegistry 统一接口，首批仍只 YOLO |
| 实时训练监控数据量大 | Low | 只绘制最近 N 个 epoch，旧数据 archive |
| TaskSpec 改为 mutable 导致并发问题 | Low | 保持 frozen，创建新版本而非修改 |

---

## 9. Acceptance

- [ ] 8 步导航完整可点击，步骤状态正确
- [ ] 新建工程 进入 STEP 2 导入页 拖拽导入 预览显示
- [ ] STEP 3 可切换任务类型，标签可增删改
- [ ] STEP 4 标注增强按钮功能正常（AI 预标注/批量预标注）
- [ ] STEP 5 切片/切分/增强独立配置，构建触发正确
- [ ] STEP 6 训练参数推荐，实时曲线显示
- [ ] STEP 7 混淆矩阵渲染，误判列表可导出
- [ ] STEP 8 多格式导出，部署包完整
