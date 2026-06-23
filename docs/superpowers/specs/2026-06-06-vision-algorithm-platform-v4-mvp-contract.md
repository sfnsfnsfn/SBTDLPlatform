# 视觉算法平台 V4.0 MVP 接口契约

> 基于 `2026-06-06-vision-algorithm-platform-design-v4-mvp-foundation.md` 的冻结对象清单、验收顺序与延后项定义

| 属性 | 内容 |
|---|---|
| 文档状态 | 开发基线 |
| 版本 | V4.0 MVP Contract |
| 日期 | 2026-06-06 |
| 前置文档 | `2026-06-06-vision-algorithm-platform-design-v4-mvp-foundation.md` |

---

## 1. 冻结对象清单

以下 8 个聚合根/实体为 V4.0 MVP 的开发基线，其字段定义为后续所有模块的接口契约。字段定义以 `docs/superpowers/specs/2026-06-06-vision-algorithm-platform-design-v4-mvp-foundation.md` 第 7 节为准。

| 序号 | 对象 | 模块 | 文件 | 冻结说明 |
|---|---|---|---|---|
| 1 | **Project** | 项目工作区 | `anylabeling/platform/application/project_service.py` | 文件化项目根，含 project.json、labels.json、assets/、annotations/ 等目录结构。冻结 project.json schema。 |
| 2 | **Asset** | 数据资产 | `anylabeling/platform/domain/asset.py` | 图像资产的不可变描述，含 id、path、尺寸、哈希。冻结字段集。 |
| 3 | **AnnotationDocument** | 标注文档 | `anylabeling/platform/domain/annotation.py` | 原图坐标标注文档，含 AnnotationObject 列表。冻结 geometry_type 枚举和坐标语义（L0 only）。 |
| 4 | **TilePlan** | 大图切分计划 | `anylabeling/platform/domain/tile.py` | 切分参数（尺寸、重叠、边界模式）。冻结 TilePlan + TileRecord 字段集。 |
| 5 | **DatasetBuild** | 数据集构建 | `anylabeling/platform/domain/dataset.py` | 可复现数据集构建清单。冻结引用关系（task_spec_id、tile_plan、adapter_id）。 |
| 6 | **Run** | 训练运行 | `anylabeling/platform/domain/run.py` | 训练运行记录。冻结状态枚举和 MetricPoint 结构。 |
| 7 | **Evaluation** | 模型评估 | `anylabeling/platform/application/evaluation_service.py` | 评估结果。冻结 Tile-native 和 Original-merged 两种验证模式。 |
| 8 | **ModelArtifact** | 模型产物 | `anylabeling/platform/domain/model.py` | 导出模型产物。MVP 冻结 ONNX format，保留 format 字段扩展位。 |

### 冻结原则

1. 上述对象的 DTO 字段为不可变契约。新增字段只能在末尾追加可选字段，不允许删除或重排。
2. 枚举值（task family、geometry_type、job status）的合法值集由 domain DTO 的 Literal 类型定义。
3. 坐标统一为 L0 原图像素坐标，不接受百分比或归一化坐标进入 domain 层。
4. 所有 DTO 必须可经 `dataclasses.asdict()` 序列化，不依赖任何第三方序列化框架。

---

## 2. 首版任务验收顺序

MVP 以 **HBB 检测** 为首个完整闭环任务，其余任务按同构接口接入。

### 2.1 为何 HBB 优先

- HBB 是工业视觉中最高频的任务类型；
- 大图切分、标签裁剪、NMS 合并流程对 HBB 最为成熟；
- 完成 HBB 闭环后，OBB/InstanceSeg/Pose 的差异主要集中在 `LabelSplitter` 和 `PredictionMerger` 实现，平台层代码零改动。

### 2.2 验收优先级

| 优先级 | 任务 | 验收阶段 | 验收内容 |
|---|---|---|---|
| P0 | **HBB 检测** | Phase 0-4 全部 | 完整闭环：标注 Rectangle -> 大图切片 -> 训练 -> Tile-native 验证 -> 原图合并验证 -> ONNX 导出 -> 一致性自检 |
| P1 | **OBB 检测** | Phase 2-4 | 标注 Rotation -> OBB LabelSplitter -> OBB Polygon IoU NMS Merger -> 其余同 HBB |
| P1 | **实例分割** | Phase 2-4 | 标注 Polygon -> Polygon LabelSplitter -> Mask/Polygon Merge -> 其余同 HBB |
| P1 | **姿态估计** | Phase 2-4 | 标注 Keypoints -> Pose LabelSplitter -> Box/OKS Merge -> 其余同 HBB |
| P2 | **图像分类** | Phase 2-4 | 标注 Flags -> Split -> 训练 -> Tile Vote aggregation -> 其余复用 |
| P3 | **语义分割** | V4.1 | 接口预留，不做实现 |
| P3 | **异常检测** | V4.1 | 接口预留，不做实现 |

### 2.3 同构接入含义

P1/P2 任务接入时：

- **平台层代码不变**：TaskSpec、DatasetBuild、Run、ModelArtifact 等 domain DTO 无需修改；
- **只新增 Adapter 组件**：新增对应 `LabelSplitter` 和 `PredictionMerger` 实现；
- **UI 通过 AlgorithmCapabilities 声明驱动**：不通过 `if task_family == "..."` 硬编码。

---

## 3. V4.1 延后项清单

以下功能在 V4.0 MVP 中明确不做实现，但在 domain DTO 和接口中预留扩展位。

### 3.1 延后至 V4.1

| 编号 | 延后项 | V4.0 处理 | 延后原因 |
|---|---|---|---|
| D-001 | 完整 Model Registry（Alias、Champion 状态） | Run + ModelArtifact 直接管理，不建立注册表 | 首版模型数量有限，直接文件路径管理足够 |
| D-002 | ReviewQueue / 误判回流状态机 | 验证样本画廊 + "复制预测为标注" 入口 | 完整状态机增加前端复杂度 |
| D-003 | Offline Resource Pack | 依赖预检 + 本地模型路径 | 部署包需要独立的需求分析 |
| D-004 | ExportPackage / 自检包 / 许可证包 | ONNX + 配置 + 一致性报告 | 生产部署规格待明确 |
| D-005 | 10 万资产 / 百万对象 / 复杂分片仓库 | 单目录文件存储 | 首版场景规模可控 |
| D-006 | 语义分割训练框架 | `semantic_segmentation` 枚举值保留，LabelSplitter/Merger 接口预留 | 需要独立的训练框架评估 |
| D-007 | 异常检测训练实现 | `anomaly` 枚举值保留，接口预留 | PatchCore 等算法待评估 |
| D-008 | 在线模型市场 | 保留原 X-AnyLabeling 自动标注功能，但不接入平台项目模式 | 离线优先定位 |
| D-009 | 自动超参数搜索 | 不做 | 需要 Ray/Optuna 等框架集成评估 |
| D-010 | TensorRT / OpenVINO 正式交付 | `format` 字段保留扩展位，MVP 只支持 `"onnx"` | 需要额外工程与测试 |
| D-011 | 通用可视化算法编排画布 | 固定工作流导航 | 首版用户需要的是稳定性，不是灵活性 |
| D-012 | 多人协作 / 用户权限 | 不做 | 单机离线定位 |
| D-013 | OCR / VLM 算法 | 不做 | 独立 Adapter 评估 |
| D-014 | Raster Mask Brush 标注工具 | `raster_mask` geometry 类型保留，但标注工具不做 | 需要独立的交互设计 |

### 3.2 延后项对架构的影响

每个延后项在 V4.0 代码中应有明确处理方式：

1. **枚举预留**：task family、geometry_type 等枚举包含延后项的值，但对应代码路径抛出 `NotImplementedError` 并附带提示信息。
2. **接口预留**：LabelSplitter、PredictionMerger、AlgorithmCapabilities 等 Protocol 包含延后任务的参数，但方法体可为 `raise NotImplementedError`。
3. **DTO 扩展位**：`format` 字段（ModelArtifact）、`augmentation_plan_id`（DatasetBuild）等保留为可选字段。
4. **UI 占位**：语义分割和异常检测在任务选择器中显示为禁用项，标注"即将推出"。

---

## 4. 开发基线验证清单

### 4.1 领域层（Domain）

- [ ] 8 个 domain DTO 文件创建且通过 `python -m pytest tests/platform/domain -q`
- [ ] 所有 DTO 可经 `dataclasses.asdict()` 序列化
- [ ] domain/ 目录不导入 PyQt6、Ultralytics、views.*
- [ ] 所有坐标语义为 L0 原图像素坐标

### 4.2 基础设施层（Infrastructure）

- [ ] ProjectFileStore 可创建/打开项目
- [ ] AtomicWriter 通过 tmp + os.replace 原子写入
- [ ] Job 协议状态机可用
- [ ] ImageSource 接口定义完成

### 4.3 UI Shell

- [ ] WorkbenchWindow 可启动
- [ ] 7 个 Workspace 页面占位
- [ ] 现有 LabelWidget 可嵌入 Workbench
- [ ] 离线模式开关生效

---

## 5. 变更记录

| 日期 | 变更 | 作者 |
|---|---|---|
| 2026-06-06 | 初始版本：冻结对象清单、验收顺序、V4.1 延后项 | sfn |
