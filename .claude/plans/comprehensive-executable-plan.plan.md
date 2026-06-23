# Comprehensive Executable Plan: X-AnyLabeling 平台交互优化

**Source**: 架构评估 (Architect Agent) + UI 评审 (Code Reviewer Agent) + 产品交互方案
**Complexity**: Large
**Created**: 2026-06-07
**Status**: Draft — WAITING FOR CONFIRMATION

---

## 0. 执行摘要

本方案综合了三层分析：
- **产品交互方案**: `docs/superpowers/specs/2026-06-07-platform-interaction-optimization.md` (8 步流水线)
- **架构评估 (Architect Agent)**: 算法扩展架构 — Capability-Based Provider Pattern
- **UI 评审 (Code Reviewer Agent)**: 8 项问题，其中 3 HIGH + 3 MEDIUM

核心结论：**服务层架构良好但需解耦，视图层需 3 页新建 + 4 页增强 + 导航重构。算法层需引入 Capability ABC 体系确保可扩展性。**

实施策略：**Phase A (Provider 解耦) → Phase B (导航+工程重构) → Phase 1-4 (8 步流水线)**

---

## 1. 架构评审摘要

### 1.1 算法层 — Architect Agent 评估

**当前 5 个结构性问题**:

| # | 问题 | 影响 |
|---|------|------|
| P1 | `AlgorithmRegistry` 只存元数据，不存行为。服务层直接 import Ultralytics | 加 DINO 要改所有 service |
| P2 | 5 个 Service 全部硬编码 Ultralytics import | 无法热切换算法 |
| P3 | 无 Adapter 接口契约。每个 adapter 方法签名不一致 | 新算法作者无参照 |
| P4 | `TrainRequest` 是 YOLO 专用（40+ 参数如 mosaic/mixup） | DINO 无法复用 |
| P5 | `AlgorithmCapabilities` 粒度不足 — `supports_export_onnx` 不够 | 无法表达 SAM（仅推理） |

**推荐方案**: Capability-Based Provider Pattern

```
                    AlgorithmRegistry
                           |
            +--------------+--------------+
            |              |              |
    UltralyticsProvider  DINOProvider  SAMProvider
    +-- train [check]    +-- train [check]   +-- inference [check]
    +-- val [check]      +-- val [check]
    +-- export [check]   +-- export [check]
    +-- inference [check]+-- inference [check]
    +-- dataset [check]  +-- dataset [check]
    +-- run_parser [check]   +-- run_parser [check]
```

**6 个 Capability ABC** (新文件 `adapters/interfaces.py`):
- `TrainCapability` — `build_train_kwargs()`, `get_train_command()`, `train_param_schema()`
- `ValCapability` — `build_val_kwargs()`, `get_val_command()`
- `ExportCapability` — `get_supported_formats()`, `build_export_kwargs()`, `get_export_command()`
- `InferenceCapability` — `get_infer_command()`, `inference_param_schema()`
- `DatasetCapability` — `adapt()`, `write_config()`, `get_data_path()`
- `RunParser` — `parse_train_results()`, `parse_val_results()`, `find_best_epoch()`, `get_best_weight_path()`

**1 个 Provider ABC** (新文件 `adapters/provider.py`):
- `AlgorithmProvider` 组合 0-6 个 Capability Adapter
- 属性 `id`, `capabilities`, `train_adapter?`, `val_adapter?`, `export_adapter?`, `inference_adapter?`, `dataset_adapter?`, `run_parser?`
- SAM 只设 `inference_adapter`，其余返回 `None`

**迁移路径** (6 步，互不破坏):
1. 新建 `interfaces.py` + `provider.py` (不碰现有代码)
2. 包装现有 Ultralytics adapters 为 `UltralyticsProvider`
3. 更新 `AlgorithmCapabilities` 字段
4. 逐个重构 Service 为 `AlgorithmRegistry.get(adapter_id)`
5. 新增 DINO adapter (零改动现有文件)
6. 新增 SAM adapter (零改动现有文件)

### 1.2 UI 层 — Code Reviewer Agent 评估

| Severity | ID | 问题 | 文件位置 |
|----------|----|------|----------|
| HIGH | #1 | NavigationBar 用 raw int 常量 — 6→8 步会静默破坏所有页面路由 | `navigation_bar.py:17-22` |
| HIGH | #2 | LabelingWidget 每次切 asset 销毁重建 — 丢失 undo/zoom/tool 状态 | `label_workspace.py:334-352` |
| HIGH | #3 | 31 个训练超参标签从未 i18n — `_format_label()` 机械转换 | `train_workspace.py:778-779` |
| MEDIUM | #4 | LabelWorkspace 无 AI 预标注/批量标注按钮 | `label_workspace.py:62-163` |
| MEDIUM | #5 | 切片配置无预览/估算 — 用户不知道会产生多少 tile | `data_workspace.py:73-90` |
| MEDIUM | #6 | 所有页面 eager 创建 — 8 页全量构造浪费资源 | `workbench_window.py:239-272` |
| LOW | #7 | Emoji 作为唯一状态指示器，无文本 fallback | `label_workspace.py:48-51` |
| LOW | #8 | i18n 系统无复数支持 | `i18n.py:55-67` |

---

## 2. Phase A: Provider 解耦 (P0 — 先于任何视图工作)

> 理由: 如果不先建立 Provider 抽象，新算法接入时又要改服务层。必须先建接口再改视图。

### Task A.1: 创建算法接口层

**新建文件**: `anylabeling/platform/adapters/interfaces.py`

**内容**: 6 个 Capability ABC — `TrainCapability`, `ValCapability`, `ExportCapability`, `InferenceCapability`, `DatasetCapability`, `RunParser`

**Mirror**: 现有 `ports.py` 的 Protocol 模式，改用 ABC 以获得更好的错误信息

**Validate**:
```bash
python -c "from anylabeling.platform.adapters.interfaces import TrainCapability, InferenceCapability; print('ABCs OK')"
```

### Task A.2: 创建 AlgorithmProvider ABC

**新建文件**: `anylabeling/platform/adapters/provider.py`

**内容**: `AlgorithmProvider` 基类，组合 0-6 个 Capability Adapter。所有属性默认返回 `None`，子类按需 override。

**Mirror**: 现有 `AlgorithmRegistry` 的注册模式

**Validate**:
```bash
python -c "from anylabeling.platform.adapters.provider import AlgorithmProvider; print('Provider ABC OK')"
```

### Task A.3: 增强 AlgorithmCapabilities

**修改文件**: `anylabeling/platform/adapters/registry.py`

**改动**:
- `supports_export_onnx: bool` → `supports_export: bool` + `export_formats: frozenset[str]`
- 新增 `supports_inference: bool`, `supports_dataset_build: bool`
- 保留 `supports_export_onnx` 作为 deprecated property（兼容过渡）
- `register()` 改为接收 `AlgorithmProvider` 并同时存储 capabilities

**Validate**:
```bash
python -c "
from anylabeling.platform.adapters.registry import AlgorithmCapabilities
caps = AlgorithmCapabilities(
    adapter_id='test', display_name='Test',
    task_families=frozenset({'detection_hbb'}),
    supports_training=True, supports_validation=True,
    supports_export=True,
    export_formats=frozenset({'onnx', 'tensorrt'}),
    supports_inference=True, supports_dataset_build=True,
    supports_sliced_inference=False,
)
print('AlgorithmCapabilities OK')
"
```

### Task A.4: 包装 Ultralytics 为 Provider

**新建文件**: `anylabeling/platform/adapters/ultralytics/provider.py`
**新建文件**: `anylabeling/platform/adapters/ultralytics/inference_adapter.py`
**修改文件**: `anylabeling/platform/adapters/ultralytics/__init__.py` — 加注册行

**内容**: `UltralyticsProvider(AlgorithmProvider)` 组合现有的 `UltralyticsTrainAdapter`, `UltralyticsValAdapter`, `UltralyticsExportAdapter`, `UltralyticsInferenceAdapter`(新建), `UltralyticsDatasetAdapter`, `UltralyticsRunParser`

**Validate**: 现有 import 不报错
```bash
python -c "from anylabeling.platform.adapters.ultralytics import *; print('UltralyticsProvider registered')"
```

### Task A.5: 重构 TrainingService 为 Provider 驱动

**修改文件**: `anylabeling/platform/application/training_service.py`

**改动**:
- 移除 `from anylabeling.platform.adapters.ultralytics.train_adapter import TrainRequest, UltralyticsTrainAdapter`
- 移除 `from anylabeling.platform.adapters.ultralytics.dataset_adapter import UltralyticsDatasetAdapter`
- 移除 `_FAMILY_TO_ADAPTER` 字典
- `start_training` 改为 `start_training(adapter_id, base_model, params, task_spec, dataset_build)`
- 通过 `AlgorithmRegistry.get(adapter_id)` 获取 provider
- `parse_and_update_run` 使用 `provider.run_parser`

**Validate**: 现有训练流程不受影响

### Task A.6: 重构 EvaluationService / ExportService / InferenceService

**修改文件**: `evaluation_service.py`, `export_service.py`, `inference_service.py`

**改动**: 与 Task A.5 同模式 — 移除硬 import，改用 Registry

**Validate**: 评估/导出/推理流程不受影响

---

## 3. Phase B: 导航 + 工程重构 (P0 — 8 步流水线骨架)

> 必须先修复 UI 评审 Finding #1 的 int 常量耦合问题，后续 8 步迁移才安全。

### Task B.1: PipelineStep 枚举重构 (修复 UI Finding #1)

**修改文件**: `views/platform/navigation_bar.py`

**改动**:
- 引入 `PipelineStep(IntEnum)`:
  ```python
  class PipelineStep(IntEnum):
      PROJECT = 0
      IMPORT = 1
      CONFIG = 2
      LABEL = 3
      PREPROCESS = 4
      TRAIN = 5
      EVALUATE = 6
      EXPORT = 7
  ```
- `STEP_LABELS_EN/STEP_LABELS_ZH` 改为 `dict[PipelineStep, str]`
- `_STEP_COUNT` 自动推导 `len(PipelineStep)`
- `page_changed` 信号 emit `PipelineStep` 而非 int

**Validate**: `assert len(PipelineStep) == 8`

### Task B.2: WorkbenchWindow 适配 PipelineStep

**修改文件**: `views/platform/workbench_window.py`

**改动**:
- 所有 `setCurrentIndex(int)` → `setCurrentIndex(PipelineStep.XXX.value)`
- `_on_page_changed` 接收 `PipelineStep` 参数
- 注册 8 个页面到 QStackedWidget（ProjectHome 单独管理）
- STEP 2/3/5 先用空 QWidget placeholder

**Validate**: 6 个现有页面导航正确

### Task B.3: 重构 NewProjectDialog → 轻量两步

**修改文件**: `views/platform/new_project_dialog.py`, `platform/infrastructure/project_file_store.py`, `platform/domain/task.py`

**改动**:
- 移除任务类型 QComboBox 和标签 QTableWidget
- 仅保留: 名称 QLineEdit + 描述 QLineEdit(新) + 位置 QLineEdit
- 新增可选快速模板 radio 组（"缺陷检测"/"OCR"/"目标定位"/"分类"/"稍后配置"）
- `project.json` 加 `description` 字段
- `TaskSpec` 加 `ocr` family + `version: int = 1`
- 创建后 WorkbenchWindow 自动跳到 `PipelineStep.IMPORT`

**Validate**: Dialog 创建后 `get_result()` 返回不含 TaskSpec 的结果

### Task B.4: 修复 LabelingWidget 每次切 asset 重建 (修复 UI Finding #2)

**修改文件**: `views/platform/label_workspace.py` (lines 334-352)

**改动**:
- 移除 `_create_labeling_widget` 中的 `while self._canvas_layout.count(): ... deleteLater()` 块
- 在 `set_project_context` 中创建 LabelingWidget 一次
- `_on_asset_selected` 只调用 `loadFile()` + `_load_existing_annotations()` 换图
- 保留 zoom/pan/tool/undo 状态

**Validate**: 切换到不同 asset 再切回，zoom 和 tool 选择保留

### Task B.5: 修复训练超参标签 i18n (修复 UI Finding #3)

**修改文件**: `views/platform/train_workspace.py` (lines 778-779)

**改动**:
- 替换 `_format_label()` 为映射字典 `_FIELD_LABELS`
- 每个 field name 映射到 `tr("中文:", "English:")`
- 覆盖全部 31 个参数: epochs, batch, imgsz, device, lr0, lrf, momentum, weight_decay, warmup_epochs, cos_lr, amp, hsv_h, hsv_s, hsv_v, degrees, translate, scale, shear, perspective, fliplr, mosaic, mixup, copy_paste, close_mosaic, box, cls, dfl, pose, kobj, workers, seed

**Validate**: locale=zh_CN 时参数标签全为中文

### Task B.6: WorkbenchWindow 页面懒加载 (修复 UI Finding #6)

**修改文件**: `views/platform/workbench_window.py` (lines 239-272)

**改动**:
- `_create_pages()` 中除首页外使用 `QWidget()` placeholder
- 首次导航到某页时调用真实构造函数，replace placeholder
- TrainWorkspace 的 timer 只在 `_active_job_id` 不为 None 时启动
- `QStackedWidget.currentChanged` 暂停不可见页的 timer

**Validate**: 启动时仅 1 个首页 widget 被构造

---

## 4. Phase 1: 导入 + 配置 (P0 — 方案 STEP 2 + 3)

### Task 1.1: 新建 ImportService

**新建文件**: `platform/application/import_service.py`, `platform/domain/import_config.py`

**内容**:
- `import_images(paths: list[str]) → ImportResult`
- 文件复制到 `assets/`（shutil.copy2，保留元数据）
- SHA-256 去重（调用 `compute_sha256`）
- 图像属性分析（cv2 读尺寸/通道/位深）
- 大图标记 (>2000px → `Asset.is_large`)
- 按文件夹名分组 (→ `Asset.group_id`)

**Mirror**: `TrainingService` 的构造函数模式 `(project_root)`

**Validate**: `ImportService(project_root).import_images(paths=["/tmp/img1.jpg"])` 返回正确结果

### Task 1.2: 新建 ImageImportDialog

**新建文件**: `views/platform/image_import_dialog.py`, `views/platform/widgets/import_preview.py`

**内容**:
- 拖拽区域 (Qt dropEvent + mimeData 解析)
- 文件选择器 (QFileDialog)
- 导入选项 checkbox 组（去重/分组/大图检测/标注导入）
- 缩略图预览网格（QListWidget + IconMode）
- 底部统计栏（总计/大图/重复计数）
- 异步导入（QThread 避免 UI 卡死）

**Mirror**: `NewProjectDialog` 的 modal + i18n + style 模式

**Validate**: 从 STEP 2 拖入图片文件夹，缩略图正确显示，统计计数准确

### Task 1.3: 新建 TaskConfigurator

**新建文件**: `views/platform/task_configurator.py`

**内容**:
- 图片预览横向滚动区
- 任务类型下拉（8 种）
- 智能推荐提示条（基于数据特征）
- 标签 CRUD 表（复用 NewProjectDialog 的 table 逻辑）
- 标签批量导入按钮（从文件夹名/JSON 文件）
- 任务类型切换时弹确认框

**Mirror**: `DataWorkspace` 的 QWidget 嵌入 + `set_project_context()` 模式

**Validate**: 切换任务类型后 `get_allowed_shape_types()` 返回正确工具

---

## 5. Phase 2: 标注 + 预处理 (P1 — 方案 STEP 4 + 5)

### Task 2.1: LabelWorkspace AI 标注增强 (修复 UI Finding #4 + #7)

**修改文件**: `views/platform/label_workspace.py`
**新建文件**: `platform/application/batch_labeling_service.py`

**改动**:
- 资产列表上方新增 toolbar:
  - "AI 预标注" 按钮（当前图片）
  - "批量标注" 按钮（全部未标注图片）
  - 模型选择 QComboBox（已训练 runs 列表）
- 底部加标注进度条（已标注/未标注/部分标注）
- 资产列表 item 加标注状态图标（用 QIcon 替代 emoji — 修复 UI Finding #7）

**Mirror**: 现有 `LabelWorkspace` QSplitter 布局 + `InferenceService` 调用

**Validate**: 点击"AI 预标注"后当前图片出现推理标注框

### Task 2.2: 新建 PreprocessWorkspace

**新建文件**: `views/platform/preprocess_workspace.py`, `platform/domain/preprocess_config.py`, `platform/domain/split_manifest.py`

**内容**:
- 大图预览区（标记大图 >2000px）
- 切片参数：宽/高 QSpinBox，overlap_x/overlap_y 独立 SpinBox（修复 UI Finding #5），边缘模式 QComboBox (strict/crop/pad)
- 切片预估标签："预计每张图 N 块切片，总计约 M 块"（修复 UI Finding #5 无预览）
- 切分配置：策略 QComboBox + 比例 SpinBox + 种子 SpinBox
- 切分预览："训练 N | 验证 M | 测试 K"
- 增强配置：checkbox 组
- 一键构建按钮 → 触发 `DatasetBuildService.build()`

**Mirror**: `DatasetBuildService.build()` 调用参数

**Validate**: 点击构建后 `dataset_builds/<id>/_READY` 被创建

### Task 2.3: DataWorkspace 简化为数据概览

**修改文件**: `views/platform/data_workspace.py`

**改动**:
- 移除切片/切分/增强配置 UI
- 仅保留数据统计（总数/已标注/类别分布）
- 添加引导按钮 → 跳转 `PipelineStep.PREPROCESS`

**Validate**: DataWorkspace 不再包含超参数配置

---

## 6. Phase 3: 训练 + 验证 (P1 — 方案 STEP 6 + 7)

### Task 3.1: TrainWorkspace 多算法增强

**修改文件**: `views/platform/train_workspace.py`
**新建文件**: `views/platform/widgets/training_monitor.py`

**改动**:
- 算法选择 QComboBox（从 `AlgorithmRegistry.for_task_capabilities(family)` 填充）
- 模型规模推荐："基于 N 张图片，推荐 YOLOv8m"
- 参数从 `provider.train_adapter.train_param_schema()` 动态生成
- 实时 Loss 曲线（`training_monitor.py` — matplotlib FigureCanvas 嵌入）
- 增量训练 checkbox

**Mirror**: 现有三页结构 (Data/Config/Train) + `AlgorithmRegistry` 查询

**Validate**: 选择不同算法时参数面板自动适配

### Task 3.2: EvaluateWorkspace 增强

**修改文件**: `views/platform/evaluate_workspace.py`
**新建文件**: `platform/application/misclassification_service.py`

**改动**:
- 混淆矩阵热力图渲染（matplotlib/seaborn → QPixmap）
- 逐类分析表格（Precision/Recall/mAP per class）
- 多 Run 对比：双下拉选择器 + 指标并排显示
- 误判回流面板：FP 误检 / FN 漏检 / 低置信度 / 混淆样本四个 tab
- "加入标注复查队列" 按钮

**Mirror**: 现有 `EvaluateWorkspace.set_project_context()` + `EvaluationService.parse_val_results()`

**Validate**: 混淆矩阵正确渲染，FP 列表可点击加入复查队列

---

## 7. Phase 4: 导出 (P2 — 方案 STEP 8)

### Task 4.1: ExportWorkspace 多格式增强

**修改文件**: `views/platform/export_workspace.py`, `platform/application/export_service.py`
**新建文件**: `platform/application/model_registry_service.py`

**改动**:
- 多格式 checkbox 组（从 `provider.export_adapter.get_supported_formats()` 动态生成）
- 部署包内容预览树
- 模型加密 checkbox + 密码输入
- "自动注册为标注模型" checkbox
- `ModelRegistryService.register(model_artifact)`

**Mirror**: 现有 `ExportWorkspace` 信号驱动模式 + `ExportService.start_export()`

**Validate**: 导出后 models/ 目录包含完整部署包，inference.py 可独立运行

---

## 8. 完整文件清单

### 新建文件 (16 个)

| # | File | Phase | Purpose |
|---|------|-------|---------|
| 1 | `platform/adapters/interfaces.py` | A.1 | 6 个 Capability ABC |
| 2 | `platform/adapters/provider.py` | A.2 | AlgorithmProvider ABC |
| 3 | `platform/adapters/ultralytics/provider.py` | A.4 | UltralyticsProvider |
| 4 | `platform/adapters/ultralytics/inference_adapter.py` | A.4 | UltralyticsInferenceCapability |
| 5 | `platform/application/import_service.py` | 1.1 | 导入服务 |
| 6 | `platform/application/batch_labeling_service.py` | 2.1 | 批量预标注 |
| 7 | `platform/application/misclassification_service.py` | 3.2 | 误判回流 |
| 8 | `platform/application/model_registry_service.py` | 4.1 | 模型注册 |
| 9 | `platform/domain/import_config.py` | 1.1 | 导入配置领域模型 |
| 10 | `platform/domain/preprocess_config.py` | 2.2 | 预处理配置领域模型 |
| 11 | `platform/domain/split_manifest.py` | 2.2 | 切分清单领域模型 |
| 12 | `views/platform/image_import_dialog.py` | 1.2 | 拖拽导入 UI |
| 13 | `views/platform/widgets/import_preview.py` | 1.2 | 缩略图预览组件 |
| 14 | `views/platform/task_configurator.py` | 1.3 | 任务配置页面 |
| 15 | `views/platform/preprocess_workspace.py` | 2.2 | 预处理独立页面 |
| 16 | `views/platform/widgets/training_monitor.py` | 3.1 | 实时训练曲线 |

### 修改文件 (15 个)

| # | File | Phase | Purpose |
|---|------|-------|---------|
| 1 | `platform/adapters/registry.py` | A.3 | 增强 AlgorithmCapabilities + Provider 存储 |
| 2 | `platform/adapters/ultralytics/__init__.py` | A.4 | 注册 Provider |
| 3 | `platform/application/training_service.py` | A.5 | Provider 驱动重构 |
| 4 | `platform/application/evaluation_service.py` | A.6 | Provider 驱动重构 |
| 5 | `platform/application/export_service.py` | A.6+4.1 | Provider 驱动 + 多格式 |
| 6 | `platform/application/inference_service.py` | A.6 | Provider 驱动重构 |
| 7 | `platform/domain/task.py` | B.3 | ocr family + version 字段 |
| 8 | `platform/infrastructure/project_file_store.py` | B.3 | description + import_state |
| 9 | `views/platform/navigation_bar.py` | B.1 | PipelineStep 枚举 + 8 步 |
| 10 | `views/platform/workbench_window.py` | B.2+B.6 | 页面注册 + 流程控制 + 懒加载 |
| 11 | `views/platform/new_project_dialog.py` | B.3 | 轻量两步创建 |
| 12 | `views/platform/label_workspace.py` | B.4+2.1 | 不销毁重建 + AI 按钮 + 进度 |
| 13 | `views/platform/train_workspace.py` | B.5+3.1 | i18n + 多算法 + 参数推荐 |
| 14 | `views/platform/evaluate_workspace.py` | 3.2 | 混淆矩阵 + 逐类 + 对比 + 误判 |
| 15 | `views/platform/data_workspace.py` | 2.3 | 简化为数据概览 |

---

## 9. 实施顺序与依赖

```
Phase A: Provider 解耦 (5 天)
  +-- A.1 -> A.2 -> A.3 -> A.4 -> A.5 -> A.6
       |
       +-- 无前置依赖，纯新文件 + 服务层重构

Phase B: 导航 + 工程重构 (4 天)
  +-- B.1 -> B.2 -> B.3 -> B.4 + B.5 (并行) -> B.6
       |
       +-- 依赖 Phase A 完成（B.3 依赖 domain.task 更新）

Phase 1: 导入 + 配置 (6 天)
  +-- 1.1 -> 1.2 -> 1.3
       |
       +-- 依赖 Phase B 完成（NavigationBar 就绪）

Phase 2: 标注 + 预处理 (5 天)
  +-- 2.1 -> 2.2 -> 2.3
       |
       +-- 依赖 Phase 1 完成（有 assets 才能标注）

Phase 3: 训练 + 验证 (6 天)
  +-- 3.1 -> 3.2
       |
       +-- 依赖 Phase A 完成（Provider 驱动）

Phase 4: 导出 (4 天)
  +-- 4.1
       |
       +-- 依赖 Phase 3 完成（有模型才能导出）

总计: ~30 天 (6 周)
```

---

## 10. Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Provider 重构破坏现有 YOLO 训练 | Medium | A.4 先包装不移除，A.5 每个 Service 独立重构，每次 commit |
| 8 步导航静默路由错误 | Medium | B.1 PipelineStep 枚举 + 类型检查，B.2 grep 所有 setCurrentIndex |
| 导入大 TIFF (>2GB) 卡死 UI | Medium | 1.2 QThread 异步导入 + 进度条 |
| 多算法参数 schema 不一致 | High | 3.1 使用 provider 的 `train_param_schema()` 动态生成 UI |
| Phase B 改动量太大 | Low | B.4/B.5/B.6 可降级到 P1 |

---

## 11. Validation

```bash
# Phase A 验证
python -c "from anylabeling.platform.adapters.interfaces import TrainCapability, InferenceCapability, RunParser; print('ABCs OK')"
python -c "from anylabeling.platform.adapters.provider import AlgorithmProvider; print('Provider ABC OK')"
python -c "from anylabeling.platform.adapters.ultralytics.provider import UltralyticsProvider; p = UltralyticsProvider(); print(f'{p.id} registered')"

# Phase B 验证
python -c "from anylabeling.views.platform.navigation_bar import PipelineStep; assert PipelineStep.LABEL == 3; assert len(PipelineStep) == 8; print('PipelineStep OK')"

# Phase 1 验证
python -c "from anylabeling.platform.application.import_service import ImportService; print('ImportService OK')"
python -c "from anylabeling.views.platform.image_import_dialog import ImageImportDialog; print('ImageImportDialog OK')"

# 全量测试
pytest tests/ -x --tb=short -q
```

---

## 12. Acceptance

### Phase A
- [ ] 6 个 Capability ABC 完整，可通过 isinstance 检查
- [ ] UltralyticsProvider 注册成功
- [ ] `TrainingService.start_training()` 通过 Registry 获取 adapter
- [ ] 现有 YOLO 训练流程不受影响

### Phase B
- [ ] 8 步导航完整可点击，PipelineStep 枚举替代所有 int 常量
- [ ] NewProjectDialog 仅收集名称+描述+位置
- [ ] LabelingWidget 切换 asset 后保留 zoom/tool 状态
- [ ] 训练参数标签 locale=zh_CN 时全中文
- [ ] 启动时仅首页被构造

### Phase 1
- [ ] 拖拽图片到导入区 → assets/ 生成文件 → 缩略图预览正确
- [ ] TaskConfigurator 可切换 8 种任务类型，标注工具自动适配

### Phase 2
- [ ] "AI 预标注" 按钮对当前图片生成推理标注
- [ ] PreprocessWorkspace 切片预览显示估算 tile 数
- [ ] 构建数据集后 `_READY` 标记存在

### Phase 3
- [ ] 不同算法选择时 TrainWorkspace 参数面板动态适配
- [ ] 混淆矩阵热力图正确渲染
- [ ] 误判列表可加入复查队列

### Phase 4
- [ ] 多格式导出 checkbox 从 provider 动态填充
- [ ] 部署包包含 model.onnx + labels.json + inference.py + README.md
- [ ] 导出后模型出现在 LabelWorkspace 的 AI 模型选择下拉中
