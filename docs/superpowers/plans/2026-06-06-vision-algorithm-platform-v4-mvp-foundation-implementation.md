# Vision Algorithm Platform V4 MVP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 X-AnyLabeling 基线上落地单机离线视觉算法平台 MVP，打通项目、数据、标注、大图切片、可复现训练、验证、切片推理和 ONNX 自检的最小闭环。

**Architecture:** 采用 PyQt6 模块化单体、本地 Worker 子进程、文件化项目、平台领域 DTO、应用服务和算法 Adapter。已验证流畅的大图画布方案作为渲染基线冻结，平台 MVP 只做工作台嵌入、性能验收和接口保护，不默认重建或替换缩放渲染路径；Ultralytics 只作为首个算法 Adapter，不进入平台领域层。

**Tech Stack:** Python 3.11+、PyQt6、OpenCV、Shapely、Ultralytics、ONNX、ONNX Runtime、pytest、jsonl、PyYAML。

---

## 1. 技术总监调整结论

V4 文档方向正确，但按当前代码状态直接实施仍然偏大。调整后的落地策略是：

1. **先做平台地基和证据链，不先重做完整 UI。** Workbench 先作为外壳嵌入现有 Label Workspace，新的 Data/Train/Evaluate/Infer/Export 页面只实现 MVP 必需操作。
2. **先让单任务闭环跑通，再扩展五类 YOLO 任务。** HBB detection 作为第一条完整闭环样板；Classify、OBB、Segment、Pose 在同一接口下分批接入，并以明确任务验收完成。
3. **先修复可复现性和离线约束，再启动训练重构。** `create_yolo_dataset()` 当前随机切分、时间戳目录、无 seed/manifest，并导入 View 层 `LabelConverter`；这是 P0。
4. **画布缩放路径改为冻结基线，不作为平台地基重构对象。** 当前超大图缩放测试效果好，MVP 计划不得把它重新拉进“大图路径修复”主线。后续只允许补充性能记录、回归测试、配置保护和平台嵌入适配。
5. **pyqtgraph/HugeImageCanvas 不再写成“删除或延后替换”。** 仓库已有 `anylabeling/views/labeling/widgets/huge_image_canvas.py` 与 `scripts/test_pyqtgraph_canvas.py`。若这是当前验证流畅的方案，它应作为画布性能基线或候选生产路径保留；是否完整替换现有标注 Canvas，必须单独通过 Shape 编辑链路验收后再决定。
6. **不宣称训练质量最优。** 在任务合同、split manifest、metric contract、baseline gate、operating point 冻结规则缺失前，只建设协议和验证流程，不做模型优劣结论。
7. **离线模式是平台项目的硬约束。** 平台路径禁止自动下载模型、禁止自动 pip install、禁止远程推理自动进入主流程；原 X-AnyLabeling 兼容功能可保留但必须隔离。

### V4 范围收缩

本计划将 V4 MVP 分为 **MVP Foundation** 与 **V4.1 扩展**。

**MVP Foundation 必须交付：**

- 文件化项目、Manifest、AtomicWriter、Job 协议。
- 现有 Label Workspace 嵌入 Workbench。
- 已验证大图画布方案冻结为性能基线，并通过 32k 级打开、缩放、标注坐标回归验收。
- `TilePlan`、`TileRecord`、`tile_manifest.jsonl`。
- HBB/OBB/Polygon/Pose/Classify 标签切分和工程回并单元测试。
- 固定 seed 的 `DatasetBuild` 与 `split_manifest.jsonl`。
- Ultralytics 五类任务可从 `DatasetBuild` 启动训练，Run 可复查。
- HBB original-merged 验证完整闭环；OBB/Segment/Pose/Classify 完成预测恢复、叠加和基础指标。
- ONNX 导出、加载和固定样本 PT/ONNX 一致性报告。

**延后到 V4.1：**

- 完整 ReviewQueue 状态机。
- 通用算法节点画布。
- 自动超参数搜索。
- TensorRT/OpenVINO 正式交付。
- 完整模型注册中心 Champion/Alias。
- 语义分割、异常检测、OCR、VLM 训练实现。
- Shape 图元迁移到 `QGraphicsItem` 的完整画布统一工程。

---

## 2. 当前代码事实

### 2.1 可复用能力

- `anylabeling/views/labeling/label_widget.py` 约 6960 行，已有图像打开、标注、导航器、训练入口。
- `anylabeling/views/labeling/widgets/canvas.py` 约 4174 行，已有 `Camera2D`、provider paint path、render quality、shape 渲染。
- `anylabeling/views/labeling/widgets/huge_image_canvas.py` 已存在，基于 pyqtgraph `ViewBox + ImageItem`，并配有 `scripts/test_pyqtgraph_canvas.py` 作为超大图缩放验证脚本。
- `anylabeling/views/labeling/viewport/` 已有 `camera.py`、`coordinate_map.py`、`image_provider.py`、`tile_grid.py`、`tile_cache.py`。
- `anylabeling/services/auto_training/ultralytics/trainer.py` 已有子进程训练 worker 和结构化事件前缀。
- `anylabeling/services/auto_training/ultralytics/exporter.py` 已有 Ultralytics export 管理器。
- `anylabeling/services/auto_labeling/utils/sahi/` 已内置 SAHI 相关能力，可借鉴 HBB 切片推理，但平台层不能直接依赖 SAHI API。

### 2.2 必须前置修复的问题

- `label_widget.py` 中 `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000` 对旧 `LabelingWidget` provider 分支仍是风险，但这不应被理解为要重写当前已验证流畅的画布方案。**暂时不进行调整**。
- `create_yolo_dataset()` 使用 `random.sample()`，未固定 seed，未保存 split manifest。
- `create_yolo_dataset()` 直接导入 `anylabeling.views.labeling.label_converter.LabelConverter`，Dataset 层依赖 View 层。
- `ExportManager` 会在缺少包时调用 `install_packages_with_timeout()` 自动安装依赖，违反离线平台约束。
- `resolve_training_model_path()` 会对裸 `.pt` 文件名调用 Ultralytics `attempt_download_asset()`，平台离线模式必须禁止。
- `ModelManager` 包含远程 server、模型下载和自定义模型加载，平台项目模式必须只接入本地 `ModelArtifact`。

---

## 3. 分工模型

### 工程师角色

| 代号 | 角色 | 适合初级工程师执行的任务 |
|---|---|---|
| E1 | 平台后端工程师 | Domain DTO、ProjectFileStore、AtomicWriter、Manifest、Job 协议 |
| E2 | 大图与几何工程师 | 画布性能基线保护、ImageSource、TilePlan、标签切分、合并、坐标测试 |
| E3 | PyQt 工程师 | Workbench Shell、Data/Train/Evaluate/Infer/Export 页面、ViewModel |
| E4 | 算法适配工程师 | Ultralytics Adapter、Run Parser、ONNX 自检、离线预检 |
| E5 | 测试与样例工程师 | fixture、端到端样例、压力脚本、验收记录 |

### Review Agent 角色

| 代号 | Review 范围 | 输出 |
|---|---|---|
| R1 架构边界 | 分层导入、DTO、Manifest、AtomicWriter、Service 边界 | blocking issues + import graph 风险 |
| R2 几何坐标 | Camera2D、画布性能基线、TilePlan、标签切分/回并、预测恢复原图坐标 | 坐标误差、性能基线与边界目标报告 |
| R3 训练复现 | split seed、DatasetBuild、Run、离线模型、无网络下载 | 复现性和离线合规报告 |
| R4 UI/线程 | UI 状态、Worker 事件、取消、日志、无 UI 线程阻塞 | UI 回归和交互验收报告 |
| R5 发布验收 | 端到端闭环、32k 大图、ONNX 自检、文档证据 | release gate checklist |

每个 milestone 结束必须至少由两个 Review Agent 交叉 review，其中一个必须不是该 milestone 的主负责方向。

---

## 4. 目录与文件规划

### 4.1 新增生产代码

```text
anylabeling/platform/
  domain/
    task.py
    asset.py
    annotation.py
    tile.py
    dataset.py
    run.py
    prediction.py
    model.py
  application/
    dto.py
    ports.py
    project_service.py
    dataset_build_service.py
    tiling_service.py
    training_service.py
    evaluation_service.py
    inference_service.py
    export_service.py
    job_service.py
    offline_policy.py
  infrastructure/
    atomic_writer.py
    checksum.py
    project_file_store.py
    manifest_store.py
    process_job_runner.py
    image_sources/
      base.py
      qt_image_source.py
      memory_image_source.py
      tiff_image_source.py
  tiling/
    tile_planner.py
    tile_materializer.py
    label_splitters/
      classify.py
      hbb.py
      obb.py
      polygon.py
      pose.py
    mergers/
      hbb.py
      obb.py
      polygon.py
      pose.py
      classify.py
  adapters/
    registry.py
    ultralytics/
      capabilities.py
      dataset_adapter.py
      train_adapter.py
      run_parser.py
      predict_adapter.py
      evaluate_adapter.py
      onnx_exporter.py
    onnxruntime/
      predictor.py
  workers/
    protocol.py
    worker_main.py
    handlers/

anylabeling/views/platform/
  workbench_window.py
  navigation_bar.py
  project_home.py
  data_workspace.py
  train_workspace.py
  evaluate_workspace.py
  infer_workspace.py
  export_workspace.py
  job_console.py
  view_models/
    project_vm.py
    dataset_vm.py
    run_vm.py
    evaluation_vm.py
```

### 4.2 修改现有代码

```text
anylabeling/app.py
anylabeling/config.py
anylabeling/views/labeling/label_widget.py
anylabeling/views/labeling/widgets/canvas.py
anylabeling/views/labeling/viewport/image_provider.py
anylabeling/services/auto_training/ultralytics/general.py
anylabeling/services/auto_training/ultralytics/trainer.py
anylabeling/services/auto_training/ultralytics/exporter.py
anylabeling/services/auto_labeling/model_manager.py
pyproject.toml
```

### 4.3 新增测试

```text
tests/platform/
  domain/
  infrastructure/
  tiling/
  adapters/
  application/
tests/views/platform/
tests/e2e/platform/
```

---

## 5. Milestone 计划

| Milestone | 周期 | 目标 | 主责 | 必须通过的 Review |
|---|---:|---|---|---|
| M0 | 3 天 | 冻结接口和验收样例 | E1/E5 | R1/R5 |
| M1 | 1.5 周 | 项目、Manifest、Job、Workbench Shell | E1/E3 | R1/R4 |
| M2 | 2.5 周 | 画布基线保护、TilePlan、标签切分、DatasetBuild | E2/E1 | R2/R3 |
| M3 | 2 周 | Ultralytics Adapter、Run、Train Workspace | E4/E3 | R3/R4 |
| M4 | 2 周 | Evaluation、Sliced Inference、ONNX | E4/E2/E3 | R2/R3/R5 |
| M5 | 1.5 周 | 稳定性、压力、文档、发布验收 | E5/all | R5 |

建议 4 名工程师并行时总工期 8-10 周。若只有 2 名工程师，按 13-16 周排期。

---

## 6. Milestone M0: 接口冻结与验收样例

### Task M0.1: 建立平台开发基线

**Owner:** E1  
**Review:** R1

**Files:**

- Create: `docs/superpowers/specs/2026-06-06-vision-algorithm-platform-v4-mvp-contract.md`
- Create: `tests/e2e/platform/fixtures/README.md`
- Modify: `docs/superpowers/specs/2026-06-06-vision-algorithm-platform-design-v4-mvp-foundation.md`

- [ ] 写出平台 MVP 的冻结对象清单：`Project`、`Asset`、`AnnotationDocument`、`TilePlan`、`DatasetBuild`、`Run`、`Evaluation`、`ModelArtifact`。
- [ ] 明确首版任务验收顺序：HBB 完整闭环第一，Classify/OBB/Segment/Pose 接口同构接入。
- [ ] 在规格文档中标注 V4.1 延后项，避免实施时把 ReviewQueue、模型治理和部署包提前塞进 MVP。
- [ ] 运行 `git diff --check`，预期无输出。

### Task M0.2: 准备可重复测试样例

**Owner:** E5  
**Review:** R2/R5

**Files:**

- Create: `tests/e2e/platform/fixtures/create_platform_fixtures.py`
- Create: `tests/e2e/platform/fixtures/expected_manifests/`

- [ ] 生成 6 张小图：classification flags、HBB、OBB、Polygon、Pose、空背景各一张。
- [ ] 生成 1 张 synthetic large image：8192 x 8192，用于 CI 级大图测试。
- [ ] 记录 32k 真实或 synthetic 大图只作为 manual/stress fixture，不放入普通测试。
- [ ] 为每张图生成 X-AnyLabeling JSON，所有坐标使用原图 L0 像素坐标。
- [ ] 运行 `python tests/e2e/platform/fixtures/create_platform_fixtures.py`。
- [ ] 运行 `python -m pytest tests/e2e/platform -q`，预期 fixture smoke tests 通过。

### Task M0.3: 建立 Review Agent 模板

**Owner:** E5  
**Review:** R5

**Files:**

- Create: `docs/superpowers/reviews/vision_platform_review_checklists.md`

- [ ] 写入 R1-R5 的 checklist。
- [ ] 每个 checklist 包含：检查范围、必须查看的文件、必须运行的命令、blocking 条件。
- [ ] 将每个 milestone 的 review 结论格式固定为：`Findings`、`Blocking`、`Tests`、`Residual Risk`。

---

## 7. Milestone M1: 平台地基与 UI Shell

### Task M1.1: Domain DTO

**Owner:** E1  
**Review:** R1

**Files:**

- Create: `anylabeling/platform/domain/task.py`
- Create: `anylabeling/platform/domain/asset.py`
- Create: `anylabeling/platform/domain/annotation.py`
- Create: `anylabeling/platform/domain/tile.py`
- Create: `anylabeling/platform/domain/dataset.py`
- Create: `anylabeling/platform/domain/run.py`
- Create: `anylabeling/platform/domain/prediction.py`
- Create: `anylabeling/platform/domain/model.py`
- Create: `tests/platform/domain/test_domain_contracts.py`

- [ ] 定义 `TaskSpec`，字段为 `id`、`family`、`labels`、`annotation_schema`、`primary_metric`。
- [ ] 定义 `Asset`，字段为 `id`、`path`、`width`、`height`、`channels`、`bit_depth`、`group_id`、`sha256`。
- [ ] 定义 `AnnotationDocument` 与 `AnnotationObject`，坐标只允许 L0 image coordinates。
- [ ] 定义 `TilePlan` 与 `TileRecord`，字段与 V4 文档一致。
- [ ] 定义 `DatasetBuild`，包含 `split_seed`、`split_strategy`、`tile_plan`、`adapter_id`、`output_path`。
- [ ] 定义 `Run`、`Evaluation`、`UnifiedPrediction`、`ModelArtifact`，只使用标准 Python 类型和 dataclass。
- [ ] 测试 dataclass 可序列化为 dict，且不导入 PyQt、Ultralytics、View 层模块。
- [ ] 运行 `python -m pytest tests/platform/domain -q`。

### Task M1.2: AtomicWriter 与 ProjectFileStore

**Owner:** E1  
**Review:** R1

**Files:**

- Create: `anylabeling/platform/infrastructure/atomic_writer.py`
- Create: `anylabeling/platform/infrastructure/checksum.py`
- Create: `anylabeling/platform/infrastructure/project_file_store.py`
- Create: `anylabeling/platform/infrastructure/manifest_store.py`
- Create: `tests/platform/infrastructure/test_project_file_store.py`

- [ ] `AtomicWriter.write_json(path, data)` 先写 `.tmp`，重新读取 JSON 验证，再 `os.replace()`。
- [ ] `ProjectFileStore.create_project(root, name, task_spec)` 创建 V4 MVP 项目目录。
- [ ] 创建目录：`assets/`、`annotations/`、`dataset_builds/`、`jobs/`、`runs/`、`evaluations/`、`models/`、`cache/`、`logs/`。
- [ ] 写入 `project.json`、`labels.json`，并保证 `_READY` 只在必要目录完成后写入。
- [ ] `ManifestStore.append_jsonl(path, row)` 使用 UTF-8，行级 JSON 可独立解析。
- [ ] 测试故障写入不会留下半截 `project.json`。
- [ ] 运行 `python -m pytest tests/platform/infrastructure -q`。

### Task M1.3: OfflinePolicy

**Owner:** E1/E4  
**Review:** R3

**Files:**

- Create: `anylabeling/platform/application/offline_policy.py`
- Create: `tests/platform/application/test_offline_policy.py`
- Modify: `anylabeling/services/auto_training/ultralytics/exporter.py`
- Modify: `anylabeling/services/auto_training/ultralytics/trainer.py`

- [ ] 定义 `OfflinePolicy(offline_mode: bool)`。
- [ ] 在平台路径下禁止 `install_packages_with_timeout()` 自动执行。
- [ ] 在平台路径下禁止 `resolve_training_model_path()` 下载裸 `.pt` 权重；裸文件名必须先在本地模型目录存在。
- [ ] 保留原兼容路径行为，但必须通过参数明确区分 `platform_offline=True`。
- [ ] 测试缺 ONNX 包时返回 preflight error，不调用 pip。
- [ ] 测试不存在的 `yolo11s.pt` 在平台离线模式返回错误，不调用 `attempt_download_asset()`。

### Task M1.4: Job 协议与 LocalProcessJobRunner

**Owner:** E1  
**Review:** R1/R4

**Files:**

- Create: `anylabeling/platform/workers/protocol.py`
- Create: `anylabeling/platform/infrastructure/process_job_runner.py`
- Create: `anylabeling/platform/application/job_service.py`
- Create: `tests/platform/application/test_job_service.py`

- [ ] 定义 `JobRequest`、`JobEvent`、`JobState`、`CancellationToken`。
- [ ] `JobService.create_job()` 写入 `jobs/<job_id>/request.json` 和 `state.json`。
- [ ] `ProcessJobRunner` 将 stdout/stderr 写入 `stdout.log`、`stderr.log`。
- [ ] 事件写入 `events.jsonl`，状态包括 `queued`、`running`、`completed`、`failed`、`cancelled`。
- [ ] `cancel()` 写入 `stop.flag` 并终止进程树。
- [ ] 测试成功、失败、取消三种 job。

### Task M1.5: Workbench Shell 嵌入现有 Label Workspace

**Owner:** E3  
**Review:** R4

**Files:**

- Create: `anylabeling/views/platform/workbench_window.py`
- Create: `anylabeling/views/platform/navigation_bar.py`
- Create: `anylabeling/views/platform/project_home.py`
- Create: `anylabeling/views/platform/job_console.py`
- Modify: `anylabeling/app.py`
- Modify: `anylabeling/views/labeling/label_widget.py`
- Create: `tests/views/platform/test_workbench_shell.py`

- [ ] 新增菜单或启动入口打开 `WorkbenchWindow`。
- [ ] Workbench 包含顶部流程导航、左侧项目树、中央 `QStackedWidget`、右侧 inspector、底部 job console。
- [ ] Label Workspace 暂时嵌入现有 `LabelingWidget`，不重写标注交互。
- [ ] 未打开项目时，Data/Train/Evaluate/Infer/Export 操作禁用。
- [ ] JobConsole 订阅 `JobService` 事件，不直接扫描磁盘。
- [ ] 运行 `python -m pytest tests/views/platform -q`。

---

## 8. Milestone M2: 画布基线保护、切分与 DatasetBuild

### Task M2.1: 冻结当前画布性能基线

**Owner:** E2  
**Review:** R2/R4

**Files:**

- Create: `plans/AGENTS_vision_algorithm_platform_canvas_baseline.md`
- Modify: `docs/superpowers/plans/2026-06-06-vision-algorithm-platform-v4-mvp-foundation-implementation.md`
- Test: `tests/views/labeling/viewport/test_huge_image_canvas_source.py`
- Test: `tests/views/labeling/viewport/test_canvas_region_rendering.py`

- [ ] 记录当前实际通过测试的画布路径：`HugeImageCanvas`、现有 `Canvas + provider`，或两者的职责边界。
- [ ] 在 `plans/AGENTS_vision_algorithm_platform_canvas_baseline.md` 记录验证命令、图像尺寸、缩放/pan 主观结果、平均/最大延迟、内存峰值、截图路径。
- [ ] 明确 MVP 平台不得默认替换当前流畅缩放路径；Workbench 只嵌入当前可用 Label Workspace。
- [ ] 如果当前运行路径依赖 `HugeImageCanvas`，保留 pyqtgraph 依赖和测试；不得按旧 V4 文案删除 `HugeImageCanvas`。
- [ ] 如果当前运行路径依赖旧 `Canvas + QImageRegionProvider`，再评估 `PROVIDER_THRESHOLD_MEGAPIXELS` 是否需要配置化；调整阈值必须保持当前 32k 缩放验收不退化。
- [ ] 新增或保留回归测试，确保 8192 x 8192 CI 级图像能打开、缩放、坐标映射正确。
- [ ] 运行 `python -m pytest tests/views/labeling/viewport/test_huge_image_canvas_source.py tests/views/labeling/viewport/test_canvas_region_rendering.py -q`。
- [ ] 运行 `python scripts/test_pyqtgraph_canvas.py --size 42000` 或记录无法执行 GUI 压测的原因，manual 结果不得伪造。

### Task M2.2: 平台 ImageSource 抽象，不改默认画布渲染

**Owner:** E2  
**Review:** R2

**Files:**

- Create: `anylabeling/platform/infrastructure/image_sources/base.py`
- Create: `anylabeling/platform/infrastructure/image_sources/qt_image_source.py`
- Create: `anylabeling/platform/infrastructure/image_sources/memory_image_source.py`
- Create: `anylabeling/platform/infrastructure/image_sources/tiff_image_source.py`
- Create: `tests/platform/infrastructure/test_image_sources.py`

- [ ] 定义 `ImageMetadata`，包含 `width`、`height`、`channels`、`bit_depth`、`supports_roi`、`supports_pyramid`。
- [ ] 定义 `LargeImageSource.read_region(rect_l0, output_size, level_hint=None)`。
- [ ] `QtImageSource` 封装 `QImageReader.setClipRect()`。
- [ ] `MemoryImageSource` 用于普通图和测试。
- [ ] `TiffImageSource` 首版先声明 capability 并使用 Qt/Pillow 可用路径；不支持快速 ROI 时返回 `supports_roi=False`。
- [ ] `LargeImageSource` 首先服务 DatasetBuild、虚拟切片推理和评估；不得默认改动当前画布 paint path。
- [ ] 如需把 `QImageRegionProvider` 迁移到 `LargeImageSource`，必须放在独立 feature flag 后，并先通过 Task M2.1 的性能基线对比。
- [ ] 测试 metadata 不触发整图解码，`read_region()` 返回目标尺寸。

### Task M2.3: TilePlan 与 tile manifest

**Owner:** E2  
**Review:** R2

**Files:**

- Create: `anylabeling/platform/tiling/tile_planner.py`
- Create: `tests/platform/tiling/test_tile_planner.py`
- Modify: `anylabeling/views/labeling/viewport/tile_grid.py`

- [ ] `TilePlanner.plan(asset, tile_plan)` 生成确定顺序的 `TileRecord`。
- [ ] 支持 `edge_mode="crop"` 和 `edge_mode="pad"`。
- [ ] 重叠率在 UI 层输入百分比，在领域层存成像素 `overlap_x`、`overlap_y`。
- [ ] 每个 `TileRecord` 记录 `x0`、`y0`、`width`、`height`、`valid_width`、`valid_height`。
- [ ] 测试无重叠、20% 重叠、右下边缘 crop、pad 四种情况。
- [ ] 测试 tile 顺序稳定，重复运行结果一致。

### Task M2.4: AnnotationCodec 下沉

**Owner:** E1/E2  
**Review:** R1/R2

**Files:**

- Create: `anylabeling/platform/application/annotation_service.py`
- Create: `anylabeling/platform/application/ports.py`
- Create: `tests/platform/application/test_annotation_codec.py`
- Modify: `anylabeling/views/labeling/label_converter.py`
- Modify: `anylabeling/services/auto_training/ultralytics/general.py`

- [ ] 新建 `AnnotationCodec` port，负责 X-AnyLabeling JSON 到 `AnnotationDocument` 的转换。
- [ ] 领域层不导入 `views.*`。
- [ ] `LabelConverter` 保持兼容，但平台 DatasetBuild 不直接依赖它。
- [ ] 测试 rectangle、rotation、polygon、point/pose、flags 五类输入能转为统一对象。
- [ ] 测试未知 shape 类型进入 validation warning，不静默丢失。

### Task M2.5: LabelSplitter 五类任务

**Owner:** E2  
**Review:** R2

**Files:**

- Create: `anylabeling/platform/tiling/label_splitters/classify.py`
- Create: `anylabeling/platform/tiling/label_splitters/hbb.py`
- Create: `anylabeling/platform/tiling/label_splitters/obb.py`
- Create: `anylabeling/platform/tiling/label_splitters/polygon.py`
- Create: `anylabeling/platform/tiling/label_splitters/pose.py`
- Create: `tests/platform/tiling/test_label_splitters.py`

- [ ] HBB：裁剪到 tile，有效面积小于 `min_visibility_ratio` 时丢弃。
- [ ] OBB：先转 polygon，与 tile 相交后输出合法四边形或 polygon，禁止简单 clamp 产生自交。
- [ ] Polygon：使用 Shapely intersection，输出 tile-local polygon，并保留 `source_object_id`。
- [ ] Pose：关键点坐标转 tile-local，tile 外关键点标为不可见。
- [ ] Classify：默认不切图；若用户启用 tile classification，继承 image flags 并记录策略。
- [ ] 每类 splitter 都提供工程回并测试，回并后坐标误差满足 1 像素或浮点容差。

### Task M2.6: DatasetBuildService

**Owner:** E1/E2  
**Review:** R3

**Files:**

- Create: `anylabeling/platform/application/dataset_build_service.py`
- Create: `anylabeling/platform/tiling/tile_materializer.py`
- Create: `tests/platform/application/test_dataset_build_service.py`
- Modify: `anylabeling/services/auto_training/ultralytics/general.py`

- [ ] 输入为 `Project`、`TaskSpec`、`Asset`、`AnnotationDocument`、`TilePlan`、`split_seed`。
- [ ] 先按 `asset.group_id or asset.id` 划分 train/val/test，再生成 tile。
- [ ] 相同 seed、相同输入、相同配置生成字节一致的 `split_manifest.jsonl` 和 `tile_manifest.jsonl`。
- [ ] 输出目录为 `dataset_builds/<build_id>/`。
- [ ] 写入 `build.json`、`split_manifest.jsonl`、`tile_manifest.jsonl`、`data.yaml`。
- [ ] 物化图像到 `images/train|val|test`，标签到 `labels/train|val|test`。
- [ ] 完成后写 `_READY`。
- [ ] 测试同一原图 tile 不跨 split。
- [ ] 测试 Windows copy 与非 Windows symlink 行为记录进 manifest。

### Task M2.7: Data Workspace MVP

**Owner:** E3  
**Review:** R4

**Files:**

- Create: `anylabeling/views/platform/data_workspace.py`
- Create: `anylabeling/views/platform/view_models/dataset_vm.py`
- Create: `tests/views/platform/test_data_workspace.py`

- [ ] 显示资产列表、标注覆盖率、类别统计。
- [ ] 提供 tile width、tile height、overlap、split seed、train/val/test ratio 输入。
- [ ] DatasetBuild 创建按钮在缺少 TaskSpec、资产或标签时禁用。
- [ ] 创建 DatasetBuild 时走 `JobService`，UI 不直接写磁盘。
- [ ] 完成后显示 Build ID、样本数量、manifest 路径和 warning。

---

## 9. Milestone M3: 训练、Run 与 Train Workspace

### Task M3.1: TaskAlgorithmRegistry

**Owner:** E4  
**Review:** R1/R3

**Files:**

- Create: `anylabeling/platform/adapters/registry.py`
- Create: `anylabeling/platform/adapters/ultralytics/capabilities.py`
- Create: `tests/platform/adapters/test_algorithm_registry.py`

- [ ] 注册 `ultralytics_yolo_classify`、`ultralytics_yolo_detect`、`ultralytics_yolo_obb`、`ultralytics_yolo_segment`、`ultralytics_yolo_pose`。
- [ ] 每个算法声明 `train`、`infer`、`evaluate`、`export`、`sliced_inference` 能力。
- [ ] registry 按 `TaskSpec.family` 过滤算法。
- [ ] 测试 UI 不需要硬编码算法列表。

### Task M3.2: UltralyticsDatasetAdapter

**Owner:** E4  
**Review:** R3

**Files:**

- Create: `anylabeling/platform/adapters/ultralytics/dataset_adapter.py`
- Create: `tests/platform/adapters/ultralytics/test_dataset_adapter.py`

- [ ] 输入为 `_READY` 的 `DatasetBuild`。
- [ ] 生成 Ultralytics 需要的 `data.yaml`，但平台事实来源仍是 `build.json` 和 manifest。
- [ ] Classify 输出目录结构为 `train/<class>`、`val/<class>`。
- [ ] Detect/OBB/Segment/Pose 输出 YOLO label，class order 来自 `TaskSpec.labels`。
- [ ] 记录 warnings：未知类别、空标注、shape 不匹配、pose config 缺失。

### Task M3.3: TrainingService 与 Run

**Owner:** E1/E4  
**Review:** R3/R4

**Files:**

- Create: `anylabeling/platform/application/training_service.py`
- Create: `anylabeling/platform/adapters/ultralytics/train_adapter.py`
- Create: `anylabeling/platform/adapters/ultralytics/run_parser.py`
- Create: `tests/platform/application/test_training_service.py`
- Modify: `anylabeling/services/auto_training/ultralytics/trainer.py`

- [ ] `TrainingService.start_run()` 创建 `runs/<run_id>/run.json`。
- [ ] Run 引用 `DatasetBuild.id`、`TaskSpec.id`、base model 路径、train config、environment。
- [ ] 训练 worker 输出事件映射到 `metrics.jsonl`。
- [ ] 完成后解析 `results.csv`、`args.yaml`、`weights/best.pt`、`weights/last.pt`。
- [ ] 失败时记录 traceback、stdout、stderr，不导致主 UI 崩溃。
- [ ] 平台离线模式下 base model 必须是本地文件。
- [ ] 测试 run 可恢复查看。

### Task M3.4: Train Workspace MVP

**Owner:** E3  
**Review:** R4

**Files:**

- Create: `anylabeling/views/platform/train_workspace.py`
- Create: `anylabeling/views/platform/view_models/run_vm.py`
- Create: `tests/views/platform/test_train_workspace.py`

- [ ] 选择 Task、DatasetBuild、Algorithm、Base Model。
- [ ] 基础参数包括 epochs、imgsz、batch、device、workers、seed。
- [ ] 增强参数首版只映射 Ultralytics 在线增强，并保存到 train config。
- [ ] Start 通过 `TrainingService` 创建 job。
- [ ] 显示 progress、loss/metric 曲线、日志、best model。
- [ ] Stop 写 stop flag 并终止进程树。
- [ ] 训练未完成时禁用正式导出按钮。

---

## 10. Milestone M4: 验证、切片推理与 ONNX

### Task M4.1: Prediction DTO 与 Merger

**Owner:** E2/E4  
**Review:** R2

**Files:**

- Create: `anylabeling/platform/tiling/mergers/hbb.py`
- Create: `anylabeling/platform/tiling/mergers/obb.py`
- Create: `anylabeling/platform/tiling/mergers/polygon.py`
- Create: `anylabeling/platform/tiling/mergers/pose.py`
- Create: `anylabeling/platform/tiling/mergers/classify.py`
- Create: `tests/platform/tiling/test_prediction_mergers.py`

- [ ] 所有 tile-local prediction 恢复到原图坐标后再合并。
- [ ] HBB 使用 class-aware NMS，输入输出保留 `source_tile_ids`。
- [ ] OBB 使用 polygon IoU NMS。
- [ ] Polygon 使用 IoU/union 策略，首版记录跨 tile source，不做复杂 mask blend。
- [ ] Pose 使用 bbox 或 OKS 近似 merge，记录配置。
- [ ] Classify 使用 max/average/vote 三种策略。
- [ ] 测试重叠区域重复预测只保留一个主结果。

### Task M4.2: InferenceService

**Owner:** E4/E2  
**Review:** R2/R3

**Files:**

- Create: `anylabeling/platform/application/inference_service.py`
- Create: `anylabeling/platform/adapters/ultralytics/predict_adapter.py`
- Create: `tests/platform/application/test_inference_service.py`

- [ ] 支持当前图像、项目资产、目录三类输入。
- [ ] 大图默认虚拟切片推理，不物化切片图片。
- [ ] 调用 `LargeImageSource.read_region()` 读取 tile。
- [ ] 输出 `predictions.jsonl`，每条预测包含 `asset_id`、`model_id`、`source_tile_ids`、`elapsed_ms`。
- [ ] 用户选择“导出调试切片”时才写切片图。
- [ ] 测试 HBB 大图虚拟切片恢复原图坐标。

### Task M4.3: EvaluationService

**Owner:** E4/E2  
**Review:** R3/R5

**Files:**

- Create: `anylabeling/platform/application/evaluation_service.py`
- Create: `anylabeling/platform/adapters/ultralytics/evaluate_adapter.py`
- Create: `tests/platform/application/test_evaluation_service.py`

- [ ] 支持 Tile-native validation，读取 Ultralytics val 输出。
- [ ] 支持 Original-merged validation，调用 InferenceService、Merger、TaskEvaluator。
- [ ] HBB 输出 mAP50、Precision、Recall、FP/Image。
- [ ] Classify 输出 Accuracy、Macro Precision/Recall/F1、Confusion Matrix。
- [ ] OBB/Segment/Pose 输出基础任务指标和样本级 overlay，复杂指标按配置记录。
- [ ] Evaluation 引用 Run、DatasetBuild、TilePlan、ModelArtifact。
- [ ] 阈值只能从 validation 配置选择，test/holdout 不得反向修改阈值。

### Task M4.4: Evaluate 与 Infer Workspace

**Owner:** E3  
**Review:** R4/R5

**Files:**

- Create: `anylabeling/views/platform/evaluate_workspace.py`
- Create: `anylabeling/views/platform/infer_workspace.py`
- Create: `anylabeling/views/platform/view_models/evaluation_vm.py`
- Create: `tests/views/platform/test_evaluate_infer_workspace.py`

- [ ] Evaluate 页面提供 Tile-native 和 Original-merged 两种模式。
- [ ] 显示指标卡、类别表、错误样本画廊。
- [ ] 画廊支持 TP、FP、FN、低置信度、tile 边界、小目标筛选。
- [ ] 点击样本进入 Label Workspace，叠加 GT 和 Prediction。
- [ ] Infer 页面显示 tile grid、合并前预测、合并后预测、耗时分解。
- [ ] “复制预测为标注”通过 Application Service，不直接改 shape list。

### Task M4.5: ONNX Export 与一致性自检

**Owner:** E4  
**Review:** R3/R5

**Files:**

- Create: `anylabeling/platform/application/export_service.py`
- Create: `anylabeling/platform/adapters/ultralytics/onnx_exporter.py`
- Create: `anylabeling/platform/adapters/onnxruntime/predictor.py`
- Create: `anylabeling/views/platform/export_workspace.py`
- Create: `tests/platform/adapters/ultralytics/test_onnx_exporter.py`
- Modify: `anylabeling/services/auto_training/ultralytics/exporter.py`

- [ ] MVP 平台路径只暴露 ONNX。
- [ ] preflight 检查 `onnx`、`onnxruntime`、`onnxslim`，缺失时提示用户手工安装，不自动 pip install。
- [ ] 导出后运行 ONNX checker。
- [ ] 使用固定 5-20 个样本运行 PT 与 ONNX 推理。
- [ ] 输出 `models/<model_id>/onnx_check.json`，包含 `load_ok`、`output_schema_ok`、`samples`、`max_abs_error`、`prediction_match_rate`、`passed`。
- [ ] 生成 `model.json`、`labels.json`、`preprocess.json`、`postprocess.json`。
- [ ] Export 页面显示自检结果和输出目录。

---

## 11. Milestone M5: 稳定性、文档与发布验收

### Task M5.1: 端到端闭环测试

**Owner:** E5  
**Review:** R5

**Files:**

- Create: `tests/e2e/platform/test_hbb_mvp_loop.py`
- Create: `tests/e2e/platform/test_ultralytics_task_smoke.py`
- Create: `verification_output/platform_mvp/README.md`

- [ ] HBB 闭环：创建项目、导入数据、DatasetBuild、训练 dry-run 或 tiny run、Evaluation、Infer、ONNX preflight。
- [ ] 五类任务 smoke：Classify、Detect、OBB、Segment、Pose 能生成 DatasetBuild 并构造 train request。
- [ ] 所有端到端测试记录 artifacts 路径。
- [ ] 运行 `python -m pytest tests/e2e/platform -q --tb=short`。

### Task M5.2: 大图压力验证

**Owner:** E2/E5  
**Review:** R2/R5

**Files:**

- Create: `scripts/platform_huge_image_verification.py`
- Create: `verification_output/platform_mvp/huge_image_acceptance.md`

- [ ] 生成或加载 32000 x 32000 图像。
- [ ] 打开过程不构建完整 RGBA QImage。
- [ ] 记录打开耗时、缩放耗时、pan 耗时、最大内存。
- [ ] 验证标注保存、关闭、重开坐标不漂移。
- [ ] 验证 Cache 上限生效。
- [ ] 输出截图和日志路径。

### Task M5.3: 离线合规验证

**Owner:** E4/E5  
**Review:** R3/R5

**Files:**

- Create: `tests/platform/test_offline_compliance.py`
- Create: `verification_output/platform_mvp/offline_compliance.md`

- [ ] monkeypatch 网络下载和 pip 安装函数，平台路径不得调用。
- [ ] 裸 `.pt` 不存在时训练 preflight 失败。
- [ ] 缺 ONNX 依赖时导出 preflight 失败并显示手工安装提示。
- [ ] remote server 模型不出现在平台项目可选算法列表。
- [ ] 运行 `python -m pytest tests/platform/test_offline_compliance.py -q`。

### Task M5.4: 用户文档与实施验收

**Owner:** E5/E3  
**Review:** R5

**Files:**

- Create: `docs/zh_cn/vision_algorithm_platform_mvp.md`
- Create: `examples/platform/vision_algorithm_end_to_end/README.md`
- Create: `plans/AGENTS_vision_algorithm_platform_v4_mvp_acceptance.md`

- [ ] 文档覆盖：新建项目、导入图像、标注、切分、生成 DatasetBuild、训练、验证、推理、ONNX 导出。
- [ ] acceptance 文件记录每个 milestone 的测试命令、输出摘要、manual GUI 截图路径。
- [ ] 若某项 manual 验收未执行，必须标注 pending，不允许写成 complete。
- [ ] 运行 `git diff --check` 和 `git diff --cached --check`。

---

## 12. Review Agent 任务模板

### R1 架构边界 Review

- [ ] 搜索 `anylabeling/platform/domain` 是否导入 PyQt、Ultralytics、views。
- [ ] 搜索 `DatasetBuildService` 是否导入 `views.*`。
- [ ] 检查 ProjectFileStore 是否只通过 AtomicWriter 写权威 JSON。
- [ ] 检查所有 manifest 是否 UTF-8 JSONL，每行可独立解析。
- [ ] 运行 `python -m pytest tests/platform/domain tests/platform/infrastructure -q`。

### R2 几何坐标 Review

- [ ] 检查当前画布性能基线文件是否存在，并记录真实测试命令、尺寸、延迟、内存和截图路径。
- [ ] 检查本 milestone 是否修改了默认画布渲染路径；若修改，必须提供基线前后对比和回退开关。
- [ ] 检查 shape、tile、prediction 是否都以 L0 image coordinates 为权威。
- [ ] 检查 splitter 不修改原始 AnnotationDocument。
- [ ] 检查 HBB 回并误差不超过 1 像素。
- [ ] 检查 OBB 和 Polygon 不产生非法自交几何。
- [ ] 检查同一原图 tile 不跨 split。
- [ ] 运行 `python -m pytest tests/platform/tiling tests/views/labeling/viewport -q`。

### R3 训练复现与离线 Review

- [ ] 检查 DatasetBuild 同 seed 同输入 manifest 字节一致。
- [ ] 检查 Run 记录 DatasetBuild、TaskSpec、base model、train config、environment。
- [ ] 检查平台路径不调用 pip install。
- [ ] 检查平台路径不自动下载裸 `.pt`。
- [ ] 检查 threshold、postprocess、augmentation 选择只来自 validation 配置。
- [ ] 运行 `python -m pytest tests/platform/application tests/platform/adapters -q`。

### R4 UI/线程 Review

- [ ] 检查 UI 不直接写项目 JSON。
- [ ] 检查长任务只通过 JobService/TrainingService/InferenceService/ExportService。
- [ ] 检查页面切换不销毁运行中的 job。
- [ ] 检查未满足前置条件时按钮禁用。
- [ ] 检查错误提示包含用户说明、技术详情和日志路径。
- [ ] 运行 `python -m pytest tests/views/platform -q`。

### R5 发布验收 Review

- [ ] 检查 acceptance 文件是否记录真实命令输出。
- [ ] 检查 manual GUI 截图和日志路径存在。
- [ ] 检查 32k 大图验收未执行时标记 pending。
- [ ] 检查 ONNX 自检报告包含固定样本和阈值。
- [ ] 检查 GPLv3 商业分发风险已写入发布说明。
- [ ] 运行 `python -m pytest tests/e2e/platform -q --tb=short`。

---

## 13. Stop Conditions

遇到以下情况必须暂停实施并升级给技术负责人：

1. 任何实现需要修改 X-AnyLabeling JSON 中 shape 的原图坐标语义。
2. 任何 DatasetBuild 或 Evaluator 开始依赖 UI View 层对象。
3. 任何平台路径自动访问网络、下载模型或 pip install。
4. 任何 tile split 导致同一原图的 tile 跨 train/val/test。
5. 任何训练或验证使用 test/holdout 来调阈值、postprocess、augmentation 或模型选择。
6. 任何方案要求重写 `LabelingWidget` 或替换 Canvas 才能继续。
7. 任何改动导致当前已验证的超大图缩放流畅性退化，且没有回退开关和性能对比证据。
8. 任何人删除 `HugeImageCanvas`、pyqtgraph 相关测试或 provider paint path，而没有经过独立画布验收计划批准。
9. 任何 manual acceptance 未执行但计划文件被写成 complete。

---

## 14. 全局验证命令

每个 milestone 完成后运行：

```bash
python -m pytest tests/platform -q --tb=short
python -m pytest tests/views/platform -q --tb=short
python -m pytest tests/views/labeling -q --tb=short
python -m compileall anylabeling/platform
git diff --check
git diff --cached --check
```

M5 发布前增加：

```bash
python -m pytest tests/e2e/platform -q --tb=short
python scripts/platform_huge_image_verification.py
```

---

## 15. 首次执行建议

先并行启动三条线：

1. E1 执行 M1.1-M1.3，冻结 DTO、ProjectFileStore、OfflinePolicy。
2. E2 执行 M2.1-M2.3，先冻结画布性能基线，再建立 TilePlan；不得先改当前缩放渲染路径。
3. E5 执行 M0.2-M0.3，准备 fixture 和 review checklist。

在 R1/R2/R3 完成第一轮 review 前，不启动 Train Workspace UI 大改造。这样可以避免 UI 先行造成业务逻辑继续堆进 `ultralytics_dialog.py` 或 `label_widget.py`。
