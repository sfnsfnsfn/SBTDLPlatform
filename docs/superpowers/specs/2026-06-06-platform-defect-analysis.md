# X-AnyLabeling V4 平台缺陷分析报告

> **视角**: 离线单机通用深度学习一站式平台技术总监审查
> **分支**: `vision_platfrom`
> **日期**: 2026-06-06
> **范围**: `anylabeling/platform/` + `anylabeling/views/platform/` + `anylabeling/adapters/`
> **更新**: 2026-06-06 — 第一阶段 C1–C8 已修复（✅ 标记）

---

## 1. 总览

当前 V4 MVP 已打通 **项目创建 → 训练 → 导出** 的最小骨架路径，但作为一个完整的离线深度学习平台，存在 **5 大类、共 37 项缺陷**。

| 严重级别 | 数量 | 定义 |
|---------|------|------|
| 🔴 Critical | 8 | 阻断核心流程，当前无法使用 |
| 🟠 High | 10 | 功能严重缺失或数据完整性风险 |
| 🟡 Medium | 12 | 影响用户体验或扩展性 |
| 🟢 Low | 7 | 代码质量 / 健壮性问题 |

---

## 2. 🔴 Critical — 阻断性缺陷

### ✅ C1. DataWorkspace 完全不可用（已修复）

**位置**: `views/platform/workbench_window.py:156-158` + `views/platform/data_workspace.py:46`

`WorkbenchWindow.set_project()` 尝试调用 `self._data_workspace._vm.set_task_specs(task_specs)`，但 `_vm` 在 `DataWorkspace.__init__` 中初始化为 `None`，且从未被赋值。**运行时必定抛出 `AttributeError`**。

此外，`_build_btn` 始终保持禁用状态，`_asset_list` 从不填充，`_stats_label` 从不更新。

### ✅ C2. EvaluateWorkspace 完全未连接（已修复）

**位置**: `views/platform/evaluate_workspace.py`

- 无 `set_project_context()` 方法，WorkbenchWindow 不向其传递任何数据
- `_run_combo`（训练运行下拉框）永远不会被填充
- `_evaluate_btn` 始终保持禁用状态
- `evaluate_requested` 信号永远不会被触发

评估功能在 UI 层面是纯装饰性的。

### ✅ C3. ExportWorkspace 按钮永远禁用（已修复）

**位置**: `views/platform/export_workspace.py`

- `_export_btn` 在 `__init__` 中设为 `setEnabled(False)`，且无任何代码启用它
- 工作区未接收训练运行数据，无法触发 `export_requested` 信号
- `_status_label` 始终显示 "选择已训练的 Run 以导出"

### ✅ C4. 推理 (Infer) 完全缺失（已修复）

**位置**: `views/platform/workbench_window.py` (已替换为 `InferWorkspace`)

- UI 显示 "(Coming soon)" 占位标签
- **完全没有 `InferenceService`**（尽管 `domain/prediction.py` 定义了 `UnifiedPrediction` 和 `PredictionObject`）
- 平台无法对任何图像运行推理——这是深度学习平台的核心功能

### ✅ C5. 数据集构建处理器是存根（已修复）

**位置**: `views/platform/workbench_window.py:_on_dataset_build_requested()`

DataWorkspace 的 `build_requested` 信号被连接，但处理器仅打印日志并显示 "将会可用" 的消息框，从未调用 `DatasetBuildService.build()`。

### ✅ C6. 训练后指标从未回写 Run 记录（已修复）

**位置**: `platform/application/training_service.py:170-174`

`Run` 的 `metrics` 列表和 `best_metric` 在训练工作进程完成后保持为空。`UltralyticsRunParser` 存在且功能完整，但无任何代码在工作进程退出后调用它来解析 `results.csv` 并回写 `Run` 记录。`update_run_record()` 方法存在但从不会被调用。

### ✅ C7. 数据集构建在无 image_sources 时静默生成不完整数据集（已修复）

**位置**: `platform/application/dataset_build_service.py`

当 `tile_plan=None` 且 `image_sources` 未提供时，图像**根本不会被复制**到输出目录。构建过程正常完成并写入 `_READY` 标记，但 `labels/` 目录包含 `.txt` 文件而 `images/` 目录为空。这是一个**静默数据完整性错误**——不会引发异常。

### ✅ C8. TrainWorkspace 轮询不更新 Run 状态（已修复）

训练启动后，`TrainWorkspace` 的轮询计时器检查 `JobService` 的作业状态，训练完成时自动调用 `parse_and_update_run()` 解析 `results.csv` 回写 `Run` 记录。这意味着：
- 训练完成后 `best_metric` 仍为 `None`
- 用户看不到最终训练指标
- `ExportWorkspace` 和 `EvaluateWorkspace` 无法获取有效的运行数据

---

## 3. 🟠 High — 严重功能缺失

### H1. 无推理服务

`domain/prediction.py` 定义了完整的预测领域模型，`JobKind` 枚举包含 `"inference"`，但应用层完全缺少 `InferenceService`。平台无法：
- 用已训练模型对新图像运行推理
- 执行切片推理 + 结果合并（大图场景）
- 对比推理结果与标注真值

### H2. 无模型管理/注册

- 无预训练模型注册表或发现机制
- 无模型下载管理（`OfflinePolicy.allow_network_download()` 存在但无调用方）
- `base_model_sha256` 从未计算或填充
- 无模型版本控制或血统追踪

### H3. 无 ONNX 推理自检

`ExportService` 导出 ONNX 模型后，`onnx_check.json` 的写入逻辑存在，但导出流程中没有一个步骤实际用 ONNX Runtime 加载导出的模型并用测试输入验证其输出与 PyTorch 原始输出一致。这意味着导出的 ONNX 模型可能损坏而无人知晓。

### H4. 仅支持 Ultralytics YOLO 算法

`AlgorithmRegistry` 是通用注册表，但仅注册了 5 个 Ultralytics YOLO 变体。不支持：
- SAM / SAM2（已存在于标注工具中但未纳入平台）
- MMDetection / MMSegmentation
- 任何 ViT 模型
- TensorFlow / OpenVINO 后端

### H5. 适配器无抽象基类

无 `BaseTrainAdapter`、`BaseDatasetAdapter` 等抽象合约。所有 Ultralytics 适配器是独立类，新适配器的开发者必须手动匹配隐式合约（返回字典的键名、JSON 文件模式）。

### H6. `TaskSpec.family` 定义了 7 种类型，但仅 5 种有适配器

| family | 适配器 |
|--------|--------|
| `classification` | ✅ ultralytics_yolo_classify |
| `detection_hbb` | ✅ ultralytics_yolo_detect |
| `detection_obb` | ✅ ultralytics_yolo_obb |
| `instance_segmentation` | ✅ ultralytics_yolo_segment |
| `pose` | ✅ ultralytics_yolo_pose |
| `semantic_segmentation` | ❌ 无适配器 |
| `anomaly` | ❌ 无适配器 |

### H7. 导出仅支持 ONNX

`export_adapter.py:73` 硬编码 `"format": "onnx"`。不支持 TensorRT、OpenVINO、CoreML。

### H8. 无项目配置管理

- 项目创建后无法修改 `TaskSpec`（标签列表、任务类型）
- 无项目级设置（默认设备、默认超参数、导出偏好）
- 无项目备份/归档机制

### H9. 无数据版本控制

`DatasetBuild` 通过输入哈希生成确定性 `build_id`，但：
- 原始图片/标注无版本追踪
- 无法对比两次构建之间的差异
- 无法追溯某次训练使用的确切数据版本

### H10. 超大图切片推理未整合

`domain/tile.py` 定义了完整的 `TilePlan` 和 `TileRecord`，`DatasetBuildService` 支持切片构建，但切片推理（sliced inference）+ NMS 合并流程在应用层完全缺失。

---

## 4. 🟡 Medium — 用户体验与扩展性

### M1. 无流水线编排

构建 → 训练 → 评估 → 导出是独立操作，无法一键串联。用户必须在每个阶段完成后手动触发下一阶段。

### M2. 无模型对比功能

无法在同一测试集上并排对比两个模型的指标。

### M3. 无主动学习/数据选择

无难例挖掘、数据分布分析或主动学习循环。

### M4. 无超参数优化

无网格搜索、贝叶斯优化或 AutoML 支持。

### M5. UI 无空状态/加载状态/错误状态

- **DataWorkspace**: 无 "此项目无资源" 空状态
- **TrainWorkspace**: 无 "无可用数据集构建" 提示
- **EvaluateWorkspace**: 无 "尚未训练" 空状态
- **ExportWorkspace**: 状态标签不随数据变化而动态更新
- **JobConsole**: 无 "打开项目以查看任务" 空状态
- **全局**: 无 `QProgressDialog` 或加载动画用于长耗时操作

### M6. 项目浏览器仅显示一层目录

`WorkbenchWindow._build_explorer_tree()` 只遍历一级子目录，不显示文件内容或缩略图。

### M7. 硬编码导出预处理/后处理参数

`export_adapter.py` 中 `preprocess.json` 始终写入 `imgsz: 640`、`mean: [0,0,0]`、`std: [255,255,255]`，无论实际训练配置如何。`postprocess.json` 硬编码 `conf_threshold: 0.25`、`nms_iou_threshold: 0.45`。

### M8. 领域模型无字段验证

所有 `@dataclass` 缺少 `__post_init__` 验证。`Asset.width`/`height` 可能为零或负数，`TilePlan.tile_width` 可能为负，`min_visibility_ratio` 可能超出 `[0,1]` 范围。

### M9. 无训练日志增量读取

`TrainWorkspace` 通过 2 秒轮询获取日志，但日志是通过 `get_job_logs()` 全量拉取的，不支持增量读取。长时间训练时日志区域会越来越长。

### M10. AnnotationObject.geometry 类型为 `object`

`geometry` 字段类型为 `object`（无类型约束），而 `geometry_type` 是文字类型。两者之间无关联验证——`geometry_type: "rectangle"` 可以接受一个 6 元素的列表。

### M11. 缺少语义分割和异常检测适配器

`TaskSpec.family` 定义了 `semantic_segmentation` 和 `anomaly`，但无对应的适配器实现。

### M12. 新建项目只支持 Detection 和 OBB

`NewProjectDialog` 仅暴露 `detection_hbb` 和 `detection_obb` 两种任务类型，但 `TaskSpec` 和 `AlgorithmRegistry` 支持 5 种。`classification`、`instance_segmentation`、`pose` 无法通过 UI 创建。

---

## 5. 🟢 Low — 代码质量与健壮性

### L1. JobService.get_job_logs 破坏封装

直接访问 `self._runner._job_dir(job_id)`（私有属性），耦合到 `ProcessJobRunner` 内部实现。

### L2. JobService 存在竞态条件

`get_job_state` 和 `get_job_events` 在 `self._lock` 之外被调用，可能在 `create_job`/`cancel_job` 并发时读到过时状态。

### L3. ExportService 静默吞异常

`get_exported_models()` 中 `except (json.JSONDecodeError, OSError): pass` 静默丢弃解析错误，调用方无法知道模型工件列表是否不完整。

### L4. 内联 Python 脚本模式脆弱

`TrainingService._build_train_command()` 将 Python 代码构建为字符串传递给 `python -c`，使用嵌套的 `json.dumps`，可能在 kwargs 含特殊字符时产生转义错误。

### L5. _write_yolo_labels 无前置检查

`x1, y1, x2, y2 = obj.geometry` 假设 geometry 恰好为 4 元素元组，无 None 检查或长度验证。

### L6. save_annotations 不阻止损坏数据写入

即使 `validate_annotations()` 返回致命错误，保存操作仍会继续。

### L7. WorkbenchWindow.set_project 是超大同步方法

> 250 行的同步方法，依次初始化 5 个服务 + 4 个工作区。任何一步失败都可能导致不一致的 UI 状态。

---

## 6. 功能完整度矩阵

| 平台功能 | UI 状态 | 后端状态 | 整体 |
|---------|---------|---------|------|
| 项目管理（新建/打开） | ✅ 完整 | ✅ 完整 | ✅ |
| 数据导入 | ❌ 不可用 | ✅ 服务存在 | ❌ |
| 数据集构建（普通） | ❌ 存根 | ⚠️ 有缺陷 | ❌ |
| 数据集构建（切片） | ❌ 存根 | ✅ 服务存在 | ❌ |
| 标注 | ✅ 完整 | ✅ 完整 | ✅ |
| 训练 | ✅ 基本可用 | ⚠️ 缺回写 | ⚠️ |
| 评估 | ❌ 未连接 | ✅ 服务存在 | ❌ |
| 推理 | ❌ 占位符 | ❌ 服务不存在 | ❌ |
| ONNX 导出 | ❌ 按钮禁用 | ⚠️ 基本可用 | ❌ |
| ONNX 自检 | ❌ | ❌ 未实现 | ❌ |
| 任务控制台 | ✅ 完整 | ✅ 完整 | ✅ |
| 模型管理 | ❌ | ❌ | ❌ |
| 实验对比 | ❌ | ❌ | ❌ |
| 流水线编排 | ❌ | ❌ | ❌ |

**功能完整度**: 4 / 14 ≈ **29%**

---

## 7. 优先修复建议

### ✅ 第一阶段（已完成 — 2026-06-06）

1. ✅ **C1**: 为 DataWorkspace 实例化 `DatasetViewModel`，连接资产列表
2. ✅ **C5**: 实现 `_on_dataset_build_requested` 调用 `DatasetBuildService`
3. ✅ **C6**: 训练结束后调用 `UltralyticsRunParser` 回写 `Run` 记录
4. ✅ **C8**: TrainWorkspace 轮询中集成 Run 记录更新
5. ✅ **C2**: 为 EvaluateWorkspace 添加 `set_project_context`

### 第二阶段（核心功能补全）

6. **C4**: 实现 `InferenceService`
7. **C3**: 连接 ExportWorkspace 数据流
8. **C7**: 修复无 image_sources 时静默生成不完整数据集
9. **H10**: 实现切片推理 + NMS 合并

### 第三阶段（平台健壮性）

10. **H5**: 定义适配器抽象基类
11. **H4**: 接入 SAM 适配器
12. **M5**: 补全 UI 空状态/加载状态/错误状态
13. **M8**: 领域模型添加 `__post_init__` 验证

---

*本报告基于 2026-06-06 `vision_platfrom` 分支代码审查生成。*
