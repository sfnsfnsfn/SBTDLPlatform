# X-AnyLabeling 设计决策文档 (DESIGN)

## 项目定位

**离线单机桌面深度学习标注平台**。不依赖云服务、数据库或外部 API。
版本: 4.0.0-beta.7 | Python >=3.11 | 504 源文件

## 架构决策

### 1. DDD 四层架构 (`platform/`)

**决策**: 采用领域驱动设计分层: `adapters → application → domain`; `infrastructure → domain`; `views → application/services`

**理由**: 桌面应用复杂度不亚于后端服务。领域逻辑纯粹可测试(无 I/O/Qt)，应用服务可独立演进，第三方框架通过适配器隔离。

**替代方案**: 扁平 MVC — 被否决，platform/ 需要更强领域建模能力管理项目/数据集/训练运行的完整生命周期。

### 2. 不可变领域类型

**决策**: `platform/domain/` 所有 DTO 使用 `@dataclass(frozen=True)`

**理由**: 防止隐蔽副作用(多工作区共享), 与原子写入天然配合, 使 WorkflowState 状态计算可预测。

### 3. 子进程隔离长耗时操作

**决策**: 训练/评估/导出/批量推理通过 `ProcessJobRunner` 在独立子进程运行。

**理由**: PyQt6 事件循环不可阻塞, GPU 内存生命周期隔离, 训练崩溃不影响 GUI, 跨平台进程树终止(taskkill/SIGKILL)。

**替代方案**: QThread — 被否决(GIL 限制, CUDA 隔离问题, 无法强制终止卡死线程)。

### 4. 双 GUI 模式共存

**决策**: `MainWindow`(传统标注) + `WorkbenchWindow`(V4 平台), `--platform` 切换。

**理由**: 快速标注不需要完整项目流水线; 渐进式迁移不破坏现有工作流。WorkbenchWindow 是新功能唯一目标。

### 5. if-elif 模型注册

**决策**: 87+ 种模型通过 `model_manager.py` if-elif 链分发, 非插件装饰器。

**理由**: 离线应用不需要动态发现; 显式导入使依赖透明; PyInstaller tree-shaking 更可靠。

**代价**: 新增模型需改 model_manager.py + `__init__.py` + `models.yaml` 三处。

### 6. 统一 ImageReader

**决策**: 所有图像读取通过 `ImageReader` (PIL → Qt → OpenCV 自动回退)。

**理由**: 消除 ~100 处 cv2/skimage/PIL 不一致调用; Qt ROI 无全解码读取; 统一错误处理。

### 7. 原子写入 + 崩溃恢复

**决策**: `AtomicWriter`: tmp → validate → os.replace(); `.json.tmp` 崩溃恢复。

### 8. Protocol 替代 ABC

**决策**: 基础设施接口使用 `typing.Protocol` 而非 `abc.ABC`。

**理由**: 无运行时继承开销; numpy 数组可直接满足协议; `LargeImageSource(Protocol)` 更灵活。

## 技术栈选择

| 技术 | 理由 | 替代方案 |
|------|------|----------|
| PyQt6 | 最成熟 Python GUI, QPainter 高性能 | Tkinter (不足) |
| ONNX Runtime | 跨平台 CPU/CUDA 推理 | TensorRT (仅 NVIDIA) |
| Shapely | OBB/Polygon 几何操作 | 手写 (易错) |
| YAML | 人类可读模型配置 | JSON (无注释) |

## 已知限制

| 限制 | 缓解 |
|------|------|
| 仅 Ultralytics YOLO 训练 | tools/onnx_exporter/ 提供预训练导出 |
| QThreadPool 未使用 | threading.Lock 门控并发 |
| QtImageSource ROI 每调用创建新 QImageReader | FileImageSource 用于大量切片 |
| 数据增强仅 UI 占位 | Phase 5 规划 |
| workers/handlers/ 空目录 | ProcessJobRunner 内联脚本替代 |

## 变更历史

| 日期 | 变更 |
|------|------|
| 2026-06-06 | V4 平台 MVP 架构设计 |
| 2026-06-07 | Phase 2a Shell 骨架 + Phase 2b WorkflowState/ProjectSession |
| 2026-06-08 | Phase 3a/3b/3c 数据与标注工业级落地 |
| 2026-06-09 | Phase 3 补充 + Phase 4 训练闭环 |
| 2026-06-22 | Unify ImageReader (6 commits) |
| 2026-06-24 | 文档同步: Codemaps + CodeTour + CONTRIBUTING + DESIGN |
