# 视觉算法一站式平台设计文档

**状态:** 草案  
**日期:** 2026-06-06  
**范围:** 将当前 X-AnyLabeling 从“AI 辅助标注工具 + 单算法训练向导”升级为“标注、训练、验证、推理、导出、部署交付”的桌面优先视觉算法一站式平台。

---

## 1. 结论摘要

当前项目已经具备一站式平台的核心底座：图像/视频标注、AI 自动标注、多种标注格式导入导出、Ultralytics GUI 训练、训练后模型导出、ONNX/TensorRT/OpenCV DNN 推理和远程推理入口。要变成类似 AIDI 的平台，重点不是围绕某一个算法做封闭流程，而是把这些能力纳入统一项目工作区、数据版本、任务分类算法注册表、实验追踪、模型资产、误判回流和部署包交付。

推荐路线是 **桌面优先的平台化改造**：保留 PyQt 客户端和现有标注体验，新建平台服务层，把训练、评估、推理、导出串成项目闭环。后续如果需要多人协作或云端训练，再把同一套服务层接到 X-AnyLabeling-Server 或独立后端。

新增开发约束：图像切割和切片结果合并统一使用 SAHI；遇到新功能需求时优先评估成熟开源库，只有在库不能满足边界条件或引入成本过高时才自研；实施顺序先补齐功能闭环和服务层接口，再做大幅 UI 调整；所有新功能都应通过服务层和 adapter 解耦，避免把业务逻辑写死在 PyQt 界面里。

---

## 2. AIDI 平台软件分析

参考网址: <https://cn.aqrose.com/aidi.html#izn9sr>

AIDI 的产品定位是工业 AI 视觉小模型开发平台，面向高速、高精度检测场景。它强调监督学习和非监督学习模块、实时缺陷检测与分类、小样本训练、本地训练、增量训练和无需代码的图形化使用流程。

它的平台闭环可以拆成八段：

1. 图像输入：JPEG、PNG、BMP、TIFF 等常见格式。
2. AI 算法画布与模块选择：分割、检测、分类、非监督分割、非监督分类、定位、字符识别、装配检查。
3. 数据标注：画笔工具、智能标注、数据分布可视化。
4. 模型训练：数据增广、自动参数调优、常规训练和增量训练。
5. 模型验证与测试：准确率、召回率、混淆矩阵、损失曲线、项目级测试。
6. 分析与优化：误判样本筛选、错误分析、推理速度预估。
7. 模型导出：标准格式模型，支持 GPU 和 CPU 运行。
8. 集成与部署：自动代码生成，支持 C++、C#、Python。

对 X-AnyLabeling 的启发是：AIDI 的竞争力来自“完整工作流”和“工业落地辅助”，不是单个模型算法。X-AnyLabeling 要追齐这种体验，需要把已有标注、自动标注、训练、导出能力做成一个项目级操作台。

---

## 3. 当前项目能力基线

### 3.1 已有能力

当前仓库已经有以下平台化基础：

- 标注主工作台：支持多种 shape、标签、属性、检查状态和导出流程。
- 自动标注：`anylabeling/services/auto_labeling/model_manager.py` 管理大量内置模型和自定义模型，支持本地模型、远程服务、批量推理线程。
- 推理后端：现有 YOLO 系列已覆盖 ONNX Runtime、OpenCV DNN、TensorRT 等路径，可作为首批算法 adapter 的实现参考。
- 格式转换：`anylabeling/views/common/converter.py` 和 `anylabeling/views/labeling/label_converter.py` 支持 YOLO、COCO、VOC、DOTA、MOT、MOTS、PPOCR、ODVG 等导入导出。
- 首批训练入口：`anylabeling/views/training/ultralytics_dialog.py` 提供 Data / Config / Train 三页 GUI，支持 Classify、Detect、OBB、Segment、Pose；后续训练入口应由任务算法注册表选择，而不是固定为 YOLO。
- 训练服务：`anylabeling/services/auto_training/ultralytics/trainer.py` 通过独立 worker 子进程运行 Ultralytics 训练，避免阻塞主 UI。
- 数据集生成：`anylabeling/services/auto_training/ultralytics/general.py` 从当前图片列表和 XLABEL JSON 生成 YOLO 数据集；未来应抽象成算法数据集 adapter，支持 DINO、VLM、OCR、异常检测等不同数据格式。
- 模型导出：`anylabeling/services/auto_training/ultralytics/exporter.py` 可从 `weights/best.pt` 导出 ONNX、TensorRT、OpenVINO、CoreML、TFLite 等 Ultralytics 支持格式。

### 3.2 主要短板

这些能力目前更像“散落在菜单里的工具”，不是完整平台：

- 没有项目工作区概念：图片、标注、训练数据集、训练 run、导出模型之间缺少统一 ID 和生命周期。
- 数据集不可复现：训练集生成使用临时目录和随机切分，但没有保存 split manifest、数据版本、随机种子、样本 hash。
- 缺实验管理：训练参数和日志有保存，但缺结构化 run registry、指标解析、模型卡、对比视图。
- 缺模型闭环：训练完成后只能导出，不能一键注册为自定义自动标注模型并回到标注流程。
- 缺误判回流：没有把验证/批量推理的 FP、FN、低置信度和类别混淆样本组织成 review queue。
- 缺项目级测试：AIDI 强调“全项目测试”，当前更偏单次训练结果查看。
- 缺部署包交付：能导出模型格式，但没有包含模型配置、类别、预处理、后处理、示例代码、报告的完整交付包。
- 缺训练证据门禁：没有强制记录任务定义、指标合同、验证集选择规则、阈值冻结规则、holdout 禁用规则。

---

## 4. 目标产品形态

目标不是替换现有标注器，而是在现有主界面之上增加一个 **Vision Algorithm Project Workspace**。

首屏应从“打开图片/目录”扩展为“打开或创建项目”。项目内固定提供六个工作页：

1. **数据:** 导入图片/视频帧、查看标注覆盖率、类别分布、检查状态、数据版本。
2. **标注:** 复用现有标注画布、自动标注和人工修正。
3. **训练:** 先选择任务分类，再选择可用算法，生成可复现数据集版本，启动/停止/恢复训练。
4. **验证:** 查看指标、曲线、混淆矩阵、类别级和切片级结果。
5. **推理:** 对未标注集、验证集或外部目录批量推理；大图和小目标场景通过 SAHI 做切片推理与结果合并；生成候选标注和误判队列。
6. **导出/部署:** 导出模型、生成 X-AnyLabeling 自定义模型配置、生成部署包和示例调用代码。

首批可接入 Ultralytics YOLO 的 `classify / detect / segment / obb / pose`，但平台设计必须允许同一任务下切换 DINO 系列检测算法、VLM 视觉理解算法、SAM 类分割算法、OCR 算法、非监督异常检测算法和企业自研算法。

---

## 5. 推荐方案

### 方案 A: 桌面优先增强，推荐

在当前 PyQt 应用内新增平台工作区和服务层，复用现有标注、转换、训练、导出、推理模块。优点是改造成本最低，能最快形成闭环；缺点是多人协作和云端调度需要后续再接服务端。

### 方案 B: 桌面 + 本地服务

把训练、评估、批量推理、模型注册放到本地 HTTP 服务，PyQt 只做客户端。优点是职责更清晰，也更容易以后接 Web；缺点是打包、端口、进程管理和本地权限复杂度更高。

### 方案 C: 完整 Web 平台

重做 Web 前端和后端，把 X-AnyLabeling 当作标注组件或兼容工具。优点是多人协作强；缺点是会绕开现有 PyQt 资产，投入最大，不适合作为第一阶段。

**推荐:** 先做方案 A，但服务层按方案 B 的边界设计，避免后续迁移时重写业务逻辑。

---

## 6. 平台架构设计

### 6.1 分层

```text
PyQt UI
  ProjectDashboard
  DatasetWorkspace
  LabelingWidget (existing)
  TrainingWorkspace / EvaluationWorkspace / InferenceWorkspace / ExportWorkspace

Application Services
  ProjectService
  DatasetVersionService
  AnnotationQualityService
  TaskAlgorithmRegistry
  TrainingJobService
  EvaluationService
  ImageTilingService
  BatchInferenceService
  ModelRegistryService
  ExportPackageService

Adapters
  Existing LabelConverter
  Existing ModelManager
  Existing Ultralytics TrainingManager / ExportManager
  Existing auto_labeling inference backends
  Task-specific algorithm adapters
  SAHI slicing and prediction merge adapter

Storage
  project.json
  dataset manifests
  split manifests
  training run records
  model cards
  export packages
  reports and logs
```

### 6.2 项目目录

建议把项目资产存储在用户工作目录下，也允许用户选择外部目录。

```text
xanylabeling_data/
  projects/
    <project_id>/
      project.json
      labels.json
      sources/
        images/
        videos/
      annotations/
        xlabels/
      datasets/
        v001/
          dataset_manifest.json
          split_manifest.json
          algorithm_data/
            ultralytics_yolo_detect/
              data.yaml
              images/
              labels/
      runs/
        train/
          <run_id>/
            run.json
            logs/
            ultralytics/
      models/
        <model_id>/
          model_card.json
          weights/
          configs/
      inference/
        <batch_id>/
          predictions.jsonl
          slicing_manifest.json
          review_queue.jsonl
      exports/
        <package_id>/
          manifest.json
          model.*
          xanylabeling_model.yaml
          sample_python/
          report.html
```

### 6.3 核心数据对象

`project.json`:

```json
{
  "id": "pcb-defect-demo",
  "name": "PCB Defect Demo",
  "task_type": "detect",
  "created_at": "2026-06-06T00:00:00+08:00",
  "labels_file": "labels.json",
  "active_dataset_version": "v001",
  "active_model_id": null
}
```

`dataset_manifest.json`:

```json
{
  "version": "v001",
  "source_count": 1200,
  "labeled_count": 980,
  "checked_count": 760,
  "class_counts": {"scratch": 420, "dent": 560},
  "annotation_format": "xlabel",
  "created_from": "current_project_annotations",
  "content_hash": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

`split_manifest.json`:

```json
{
  "seed": 20260606,
  "strategy": "random_by_image",
  "train_ratio": 0.8,
  "group_key": "source_image",
  "train": ["images/a.jpg"],
  "val": ["images/b.jpg"],
  "holdout": [],
  "holdout_forbidden_use": true
}
```

`run.json`:

```json
{
  "id": "train_20260606_001",
  "dataset_version": "v001",
  "task_type": "detect",
  "algorithm_id": "ultralytics_yolo_detect",
  "framework": "ultralytics",
  "model_seed": "yolo11n.pt",
  "status": "completed",
  "started_at": "2026-06-06T00:00:00+08:00",
  "ended_at": "2026-06-06T00:30:00+08:00",
  "args": {"epochs": 100, "imgsz": 640, "batch": 16},
  "metrics": {},
  "artifacts": {
    "best_pt": "weights/best.pt",
    "last_pt": "weights/last.pt"
  }
}
```

`model_card.json`:

```json
{
  "id": "model_20260606_001",
  "name": "PCB Defect Detector",
  "source_run_id": "train_20260606_001",
  "algorithm_id": "ultralytics_yolo_detect",
  "dataset_version": "v001",
  "task_type": "detect",
  "classes": ["scratch", "dent"],
  "formats": ["pt", "onnx"],
  "primary_metric": null,
  "license": "project-defined",
  "checksums": {
    "best.pt": "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
  }
}
```

---

## 7. 需要修改的模块

### 7.1 项目工作区

新增：

- `anylabeling/services/platform/project_store.py`: 读写项目 manifest、路径解析、最近项目。
- `anylabeling/services/platform/project_models.py`: dataclass 或 pydantic-like 轻量 schema。
- `anylabeling/views/platform/project_dashboard.py`: 创建/打开项目、项目概览、最近项目。
- `anylabeling/views/platform/workspace_window.py`: 容纳数据、标注、训练、验证、推理、导出 tab。

修改：

- `anylabeling/views/labeling/label_widget.py`: 允许从项目上下文启动标注和训练，训练菜单保留兼容入口。
- `anylabeling/configs/xanylabeling_config.yaml`: 增加 `platform.projects_root`、`platform.last_project_id`。

### 7.2 数据版本和算法数据集生成

先改造 `anylabeling/services/auto_training/ultralytics/general.py` 作为首批 YOLO 数据集 adapter，再把接口抽象到平台服务层：

- 将现有 `create_yolo_dataset` 的字符串返回值扩展为结构化结果，例如 `CreatedDataset(path, manifest_path, split_manifest_path, warnings)`。
- 输出目录写入 `algorithm_data/<algorithm_id>/`，不把 YOLO 目录结构作为平台固定结构。
- 增加 `seed` 参数，保存到 split manifest。
- 支持固定 train/val/holdout 切分，避免每次训练随机变化。
- 保存 image path、label path、文件 hash、checked 状态、类别统计。
- 支持“仅 checked 文件训练”的同时记录被排除样本。
- 对 Windows 复制、Linux/macOS symlink 行为写入 manifest，避免后续找不到源文件。
- 为后续 DINO、VLM、OCR、异常检测等算法预留 `DatasetAdapter.prepare(task_contract, dataset_version, algorithm_id)` 接口。

新增测试：

- 同样 seed 生成同样 split。
- `only_checked_files=True` 时未检查样本不进入 train/val。
- `skip_empty_files=True` 时背景图处理符合预期。
- 标签缺失、未知类别、shape 类型不匹配会出现在 warnings。

### 7.2.1 大图切割与切片结果合并

新增 `ImageTilingService`，并把 SAHI 作为唯一默认实现：

- `ImageTilingService.plan_slices(image_path, policy)`: 生成切片计划，不直接依赖 UI。
- `ImageTilingService.run_sliced_inference(model_adapter, image_path, policy)`: 调用模型 adapter 对每个切片推理。
- `ImageTilingService.merge_predictions(slice_predictions, policy)`: 使用 SAHI 合并切片预测结果，处理坐标还原、重叠区域去重、NMS/NMM 等策略。
- `ImageTilingService.write_slicing_manifest(batch_id, policy, image_paths)`: 记录切片尺寸、重叠比例、合并策略、模型 ID 和输出路径。

SAHI 只出现在 adapter 层，平台服务层暴露自己的输入/输出对象，避免 UI、训练服务或模型注册服务直接依赖 SAHI API。后续如果替换切片库，只需要替换 adapter，不影响项目、推理、复核队列和导出包。

数据和推理 manifest 需要记录：

```json
{
  "library": "sahi",
  "slice_height": 640,
  "slice_width": 640,
  "overlap_height_ratio": 0.2,
  "overlap_width_ratio": 0.2,
  "postprocess_type": "NMS",
  "postprocess_match_metric": "IOU",
  "postprocess_match_threshold": 0.5
}
```

### 7.3 标签体系和任务合同

新增 `TaskContractService`：

- 管理项目任务类型、标签列表、shape 类型映射、pose keypoints。
- 从现有标注自动发现类别，但训练前要求用户确认并冻结。
- 自动生成 `classes.txt`、首批 YOLO `data.yaml`、pose config；后续由算法数据集 adapter 生成 DINO、VLM、OCR 等算法需要的数据描述文件。
- 校验标注中未知标签、空标签、跨任务 shape。

算法证据门禁：

- 训练前至少要求记录任务类型、输出 schema、数据版本、split manifest、主指标、验证集选择规则。
- 这不是最终训练配方；在没有 baseline gate 和指标合同前，不声明某个模型或参数“最佳”。

### 7.3.1 任务分类算法注册表

新增 `TaskAlgorithmRegistry`，算法必须先按任务分类，再按能力挂接到训练、推理、验证和导出流程。UI 的第一层选择是任务，第二层才是算法；服务层根据任务合同筛选可用算法，避免把所有模型平铺在一个列表里。

任务分类建议：

- `classification`: 图像分类、属性分类、多标签分类。
- `detection_hbb`: 水平框检测，包含 YOLO、DINO/DETR 系列、RT-DETR、RF-DETR、DEIM、D-FINE 等。
- `detection_obb`: 旋转框检测，包含 YOLO-OBB 等。
- `segmentation_instance`: 实例分割，包含 YOLO-Seg、SAM 辅助分割、RF-DETR-Seg 等。
- `segmentation_semantic`: 语义分割，预留 U-Net、DeepLab、SegFormer 等。
- `pose`: 姿态估计和关键点检测。
- `ocr`: 文本检测、识别、KIE、文档版面解析。
- `tracking`: MOT、MOTS、视频目标跟踪。
- `grounding`: 开放词表检测、文本提示定位、视觉定位。
- `vlm`: 视觉语言理解、图像问答、开放词表描述、结构化视觉问答。
- `counting`: 目标计数。
- `anomaly`: 非监督/弱监督异常检测，作为后续扩展。

算法注册对象使用统一结构：

```json
{
  "id": "ultralytics_yolo_detect",
  "display_name": "Ultralytics YOLO Detect",
  "task_family": "detection_hbb",
  "provider": "Ultralytics",
  "capabilities": {
    "train": true,
    "infer": true,
    "evaluate": true,
    "export": true,
    "sliced_inference": true
  },
  "supported_annotation_shapes": ["rectangle"],
  "supported_model_formats": ["pt", "onnx", "engine"],
  "adapter": "UltralyticsDetectionAdapter"
}
```

每个算法 adapter 需要实现按需接口，而不是继承一个臃肿基类：

- `prepare_dataset(task_contract, dataset_version)`: 可选，生成该算法需要的数据格式。
- `train(train_request)`: 可选，返回结构化 run event。
- `predict(predict_request)`: 可选，返回项目统一预测对象。
- `evaluate(evaluation_request)`: 可选，返回统一指标对象。
- `export(export_request)`: 可选，返回模型 artifact 和部署配置。
- `supports_slicing(policy)`: 可选，声明是否可接入 SAHI 切片推理。

新增算法流程：

1. 在任务分类下新增算法注册项。
2. 实现一个 adapter，只暴露该算法实际支持的能力。
3. 写入任务、shape、数据格式、模型格式和依赖声明。
4. 补充最小测试：注册表能发现算法，任务合同能筛选算法，adapter 能完成至少一个声明能力。

这样后续新增 YOLO、DINO/DETR、RT-DETR、D-FINE、SAM、VLM、OCR、异常检测或企业自研算法时，不需要改动项目工作区、数据版本、训练 run、推理队列、模型注册和导出包的主流程。

### 7.4 训练作业服务

保留 `TrainingManager` 子进程模式，但在外层新增 `TrainingJobService`：

- 创建 run id。
- 写入 `run.json` 初始状态。
- 从 `TaskAlgorithmRegistry` 读取当前任务和算法 adapter，确认该算法支持 `train` 能力。
- 调用现有 `TrainingManager.start_training(train_args)`。
- 监听 event 后更新 `run.json`。
- 保存环境信息：Python、torch、ultralytics、CUDA、设备。
- 训练结束后解析 `results.csv`、`args.yaml`、`confusion_matrix.png`、曲线图、weights。
- 支持“导入已有 Ultralytics run”为平台 run。

训练 UI 改造：

- Data 页显示当前项目数据版本，而不是仅当前 `image_list`。
- Config 页增加“保存为训练模板”和“从历史 run 复用参数”。
- Train 页增加 run 详情、artifact 链接、失败诊断。

### 7.5 验证与错误分析

新增 `EvaluationService`：

- 解析 Ultralytics 输出指标和图像。
- 提供类别级 Precision / Recall / mAP / F1 / 混淆矩阵展示。
- 支持按标签、图像来源、尺寸、checked 状态等切片统计。
- 支持阈值选择记录，但阈值必须来自 validation，不允许用 holdout 反复调参。

新增 `ReviewQueueService`：

- 从验证或批量推理结果生成 review queue。
- 队列类型包括低置信度、疑似漏检、疑似误检、类别混淆、空标注但高置信预测。
- 队列项能跳回标注画布，用户接受/拒绝/修正后更新 XLABEL。

### 7.6 批量推理闭环

新增 `BatchInferenceService`：

- 输入：model_id、dataset_version 或外部目录、阈值、是否保留已有标注。
- 调用现有 `ModelManager.predict_shapes` 的批量模式，或新增更轻量的模型 adapter。
- 对大图、小目标或用户开启切片推理的任务，先经 `ImageTilingService` 调用 SAHI 切片，再合并回原图坐标。
- 输出：`predictions.jsonl`、可视化图、候选 XLABEL、review queue。

UI：

- 在推理页选择模型和数据集。
- 展示速度、平均耗时、预测数量、异常失败样本。
- 提供“应用到标注”“只生成候选”“送入复核队列”三种动作。

### 7.7 模型注册和一键回灌

新增 `ModelRegistryService`：

- 训练完成后自动生成 model card。
- 导出 ONNX/TensorRT 后保存格式、checksum、类别、预处理配置。
- 生成 X-AnyLabeling 自定义模型 YAML。
- 自动把新模型加入用户自定义模型列表，不需要用户手工写 YAML。
- 支持模型版本对比和回滚。

需要复用或扩展：

- `anylabeling/services/auto_labeling/model_manager.py` 的 custom model 加载逻辑。
- `anylabeling/configs/auto_labeling/*.yaml` 的字段约定。
- `anylabeling/services/auto_labeling/__base__/yolo.py` 的通用 YOLO 后处理能力可作为首批检测 adapter 参考；DINO、VLM、SAM、OCR 等算法应各自封装为同级 adapter。

### 7.8 导出与部署包

扩展 `ExportManager` 为 `ExportPackageService`：

- 保留单模型格式导出。
- 新增“平台部署包”：
  - 模型文件。
  - X-AnyLabeling 自定义模型配置 YAML。
  - 类别文件。
  - 预处理/后处理参数。
  - 推理示例 Python。
  - 训练 run 和数据版本摘要。
  - 指标报告。
  - license 和第三方依赖说明。
- 可选生成 X-AnyLabeling-Server 注册配置。

注意：Ultralytics 官方文档说明 YOLO 有 AGPL-3.0 和 Enterprise 两类许可。若把训练功能作为商业网络服务或闭源产品能力交付，需要单独处理许可合规。

### 7.9 平台导航和 UI

推荐信息架构：

```text
Project Dashboard
  New Project
  Open Project
  Recent Projects

Workspace
  Overview
  Data
  Label
  Train
  Evaluate
  Infer
  Export
```

训练对话框可以先嵌入 Workspace 的 Train 页，后续再拆成独立 `TrainingWorkspace`。不要一开始重写整个标注 UI。

UI 改造策略：

- 第一阶段只做必要入口和状态展示，保证项目、数据版本、训练、推理、导出功能可以跑通。
- UI 中先选择任务分类，再显示该任务下可用算法；算法列表来自 `TaskAlgorithmRegistry`，不在界面里硬编码模型清单。
- 大幅 UI 重排放到功能闭环稳定之后，避免界面重构阻塞服务层落地。
- UI 只调用服务层接口，不直接操作 SAHI、Ultralytics、LabelConverter、ModelManager 或具体算法 adapter 的细节对象。

### 7.10 开源库优先策略

新增功能前先做依赖评估：

- 图像切割、切片推理、结果合并：默认使用 SAHI。
- 数据增强、指标计算、可视化、导出格式、日志解析等功能，优先评估成熟开源库。
- 新增算法时优先选择成熟开源实现，并通过任务分类 adapter 接入；避免把算法特有逻辑散落到项目、训练、推理或 UI 模块。
- 引入库前记录用途、许可、维护状态、可选依赖、打包影响和替代方案。
- 第三方库通过 adapter 封装；核心业务对象使用项目内定义的数据结构。
- 不在 UI 层直接调用第三方库 API。

### 7.11 文档和示例

新增：

- `docs/zh_cn/vision_algorithm_platform.md`
- `examples/platform/vision_algorithm_end_to_end/README.md`
- `examples/platform/vision_algorithm_end_to_end/project.json`
- `docs/zh_cn/model_lifecycle.md`

更新：

- `examples/training/ultralytics/README.md`: 从单次训练教程扩展到项目闭环教程。
- `docs/zh_cn/custom_model.md`: 增加平台自动生成模型配置的说明。
- `docs/zh_cn/cli.md`: 增加项目级 CLI 或说明 GUI 优先。

---

## 8. 分阶段路线

### Phase 1: 项目闭环 MVP

目标：用户能创建项目、标注、按任务和算法生成可复现数据集、训练、导出、把导出模型一键加载回自动标注。

范围：

- 项目 manifest 和项目目录。
- Dataset version + split manifest。
- `TaskAlgorithmRegistry` 和首批任务算法注册项，至少包含 YOLO 检测/分割/分类/OBB/姿态；预留 DINO/DETR、VLM、SAM、OCR、异常检测算法槽位。
- SAHI 切片/合并服务接口和 manifest。
- 训练 run registry。
- 训练完成后生成 model card。
- 一键生成自定义模型 YAML 并注册。
- 文档和核心单元测试。

不做：

- 多人协作。
- 云端训练。
- 自动调参。
- 非监督异常检测。

### Phase 2: 验证、分析、推理回流

目标：形成“训练 -> 验证 -> 误判样本 -> 修正标注 -> 再训练”的闭环。

范围：

- 指标解析和验证页。
- 批量推理页。
- 大图切片推理和切片预测合并。
- review queue。
- 标注画布跳转到队列样本。
- 训练 run 对比。

### Phase 3: 部署包和服务集成

目标：形成可交付部署资产。

范围：

- 平台部署包。
- 示例代码生成。
- X-AnyLabeling-Server 注册配置。
- CPU/GPU/TensorRT 后端检查。
- 推理速度基准。

### Phase 4: 协作和远程平台

目标：向团队平台演进。

范围：

- 项目锁和多人冲突策略。
- 远程训练队列。
- 共享模型仓库。
- 权限和审计日志。

---

## 9. 风险和约束

- **许可风险:** Ultralytics YOLO 使用 AGPL-3.0 或 Enterprise 许可，商业闭源和网络服务需要提前确认授权。
- **复现风险:** 当前随机切分和临时数据集目录不足以支撑实验复现，必须优先补 manifest。
- **训练稳定性风险:** 没有 baseline gate、指标合同、冻结阈值和 holdout 规则前，平台不能宣称自动选出的模型是最终最佳模型。
- **打包风险:** GUI 中自动安装缺失导出依赖可能失败，也可能污染用户环境；部署包应记录依赖而不是静默改变环境。
- **依赖风险:** 开源库优先可以降低自研成本，但必须记录许可、版本范围、打包影响和失败降级路径；SAHI 通过 adapter 隔离，不能让其 API 泄漏到 UI 层。
- **性能风险:** 批量推理和大数据集扫描不能放在 UI 线程；应沿用 QThread/子进程模式。
- **存储风险:** Windows 复制、Linux/macOS symlink 行为不同，项目迁移时要能重新定位源文件。

---

## 10. 验收标准

Phase 1 完成时，至少满足：

- 创建项目后生成稳定 `project.json`。
- 同一数据版本和 seed 多次生成相同 train/val split。
- 训练 run 有结构化 `run.json`，能恢复查看参数、日志、产物。
- 训练完成后能生成 model card。
- 导出模型能生成 X-AnyLabeling 自定义模型 YAML。
- 新模型能在自动标注面板加载并对当前项目图片推理。
- 算法按任务分类展示；至少 detection_hbb、detection_obb、segmentation_instance、classification、pose 五类能注册并筛选算法。
- SAHI 切片/合并服务能输出原图坐标预测和 `slicing_manifest.json`。
- 文档能指导用户完成“导入图片 -> 标注 -> 训练 -> 导出 -> 回灌推理”。

Phase 2 完成时，至少满足：

- 能展示训练指标和混淆矩阵。
- 能对数据集批量推理并生成 review queue。
- 能对大图执行 SAHI 切片推理，并把合并结果回写为候选 XLABEL。
- 用户能从 review queue 跳转到标注画布修正。
- 修正后的数据能生成新 dataset version 并再次训练。

---

## 11. 自检

- 本设计没有给出具体训练超参数搜索或“最佳模型”结论，因为当前缺少任务合同、baseline gate、固定 split、指标合同和 holdout 规则。
- 本设计优先复用现有 PyQt、LabelConverter、ModelManager，以及作为首批 adapter 的 Ultralytics TrainingManager 和 ExportManager。
- 本设计要求算法按任务分类注册，新增算法通过 adapter 声明能力，不修改平台主流程。
- 本设计要求图像切割和合并通过 SAHI adapter 实现，优先使用成熟开源库，并把第三方依赖隔离在 adapter 层。
- 本设计要求先完成功能闭环和服务层接口，再进行大幅 UI 调整。
- 本设计把平台化第一阶段限制在桌面单机闭环，避免一开始引入多人协作和云端调度。
- 本设计覆盖 AIDI 对标中的图像输入、标注、训练、验证、分析、导出、部署闭环；非监督异常学习和自动参数调优列为后续能力。
