<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~950 -->

# 架构总览 (Architecture)

## 工程定位

Windows/Linux/macOS 离线单机桌面深度学习标注平台。Python 3.11+, PyQt6 GUI, ONNX Runtime 推理。504 个源文件。

## 顶层分层

```
anylabeling/
├── app.py                         # 入口 (421L), main() → arg解析 → QApplication
├── app_info.py                    # 版本 4.0.0-beta.7
├── config.py                      # 3 层配置合并: defaults → ~/.xanylabelingrc → CLI
├── platform/                      # DDD 分层架构 (核心平台)
│   ├── domain/                    # 14 个 frozen dataclass DTO
│   ├── application/               # 18 个服务类 + 3 个格式编解码器
│   ├── infrastructure/            # 图像I/O, 项目存储, 子进程管理, 原子写入
│   ├── adapters/                  # AlgorithmProvider ABC + registry + UltralyticsProvider
│   ├── tiling/                    # TilePlanner + TileMaterializer + 5 个标签分割器
│   └── workers/                   # 作业状态机协议 + handlers/ (空目录)
├── services/
│   ├── auto_labeling/             # 87+ 种模型 + ModelManager + 3 个推理引擎
│   └── auto_training/             # Ultralytics YOLO 训练管线
├── views/
│   ├── labeling/                  # 标注 UI: Canvas, viewport, 30+ 对话框
│   ├── platform/                  # V4 平台工作台: Shell + 9 个工作区页面
│   ├── training/                  # 独立训练对话框 (历史遗留)
│   └── common/                    # 公共组件: checks, converter, device_manager, toaster
├── configs/                       # 模型 YAML 注册表 (~365 条目) + models.yaml 索引
└── tools/                         # 标签转换器、ONNX 导出器
```

## 双模式架构

```
用户启动 xanylabeling
  ├── 普通模式: MainWindow → LabelingWrapper → LabelingWidget
  │   └── 核心标注功能 (画布/形状/自动标注/保存)
  │
  └── --platform 模式: WorkbenchWindow → QStackedWidget
      └── 5 域流水线: Project → Data Prep → Train → Eval → Export
          ├── 嵌入 LabelingWidget 作为标注页
          └── ProjectSession 管理所有服务生命周期
```

## 关键类与入口

| 入口 | 文件 | 类/函数 | 说明 |
|------|------|---------|------|
| CLI 启动 | `app.py:47` | `main()` | argparse → QApplication → 选择窗口 |
| 传统 GUI | `views/mainwindow.py` | `MainWindow(QMainWindow)` | 标注为中心的窗口 |
| V4 平台 GUI | `views/platform/workbench_window.py` | `WorkbenchWindow(QMainWindow)` | 流水线工作台 |
| 训练子进程 | `app.py` | `train-worker` 子命令 | `YOLO(model).train()` 独立进程 |
| 配置 | `config.py` | `get_config()`, `validate_config_item()` | default → user → CLI 三层合并 |
| 设备 | `views/labeling/utils/device_manager.py` | `DeviceManager` | 单例, env → config → auto-detect |

## 数据流 (核心标注)

```
用户操作 (鼠标/键盘)
  → Canvas (QWidget) ──读取视口──→ Camera2D + CoordinateMap
  → Shape 对象 (数据模型)
  → LabelFile.save() → .json (X-AnyLabeling 格式)

自动标注:
  用户点击 "Run"
  → AutoLabelingWidget 信号
  → ModelManager.predict_shapes_threading()
  → QThread → Model.predict_shapes() → ONNX 推理
  → AutoLabelingResult → Canvas 更新形状
```

## 数据流 (V4 平台流水线)

```
ProjectHome → 创建/打开项目 → ProjectSession 初始化
  → ImportWorkspace → ImportService → 复制资产 → assets/
  → TaskConfigurator → 任务族 + 标签选择
  → LabelWorkspace → 嵌入 LabelingWidget → 标注
  → PreprocessWorkspace → DatasetBuildService → YOLO 数据集
  → TrainWorkspace → TrainingService → 子进程训练 → runs/
  → EvaluateWorkspace → EvaluationService → 混淆矩阵
  → ExportWorkspace → ExportService → ONNX → models/
  → ModelLibrary → 模型注册浏览
```

## 关键设计决策

| 决策 | 位置 | 说明 |
|------|------|------|
| DDD 分层 | `platform/` | domain/application/infrastructure/adapters 四层 |
| 不可变领域类型 | `platform/domain/` | 全部 `@dataclass(frozen=True)` |
| 协议抽象 | `platform/infrastructure/image_sources/` | `LargeImageSource(Protocol)` |
| 子进程隔离 | `platform/infrastructure/process_job_runner.py` | 训练/评估/导出独立进程 |
| 原子写入 | `platform/infrastructure/atomic_writer.py` | tmp → validate → os.replace |
| if-elif 注册 | `services/auto_labeling/model_manager.py` | 87 种模型类型通过 if-elif 链分发 |
| 双 GUI 共存 | `views/mainwindow.py` + `views/platform/` | 共享 LabelingWidget |
| ImageReader 统一 I/O | `platform/infrastructure/image_reader.py` | PIL → Qt → OpenCV 自动回退 |

## 实现状态

| 层/模块 | 状态 |
|----------|------|
| 领域模型 (14 DTO) | ✅ 完成 |
| 应用服务 (18) | ✅ 完成 |
| 基础设施 (I/O, ImageSource, Manifest) | ✅ 完成 |
| 适配器 (Ultralytics + 3 codec) | ✅ 完成 |
| 标注 UI | ✅ 完成 |
| 平台工作台 9/9 步骤 | ✅ 全部实现 |
| V4 Shell 组件 (AppBar/PrimaryNav/SubNav/etc.) | ✅ 完成 |
| BatchLabelingService | ⚠️ 缺少推理管线连接 |
| InferWorkspace | ⚠️ 已实现但未实例化 (死代码) |
| workers/handlers/ | ❌ 空目录 |
| 非 YOLO 训练适配器 | ❌ 未实现 |
| TileCache / tiles_for_rect | ⚠️ 已实现但无消费者 |
| HugeImageCanvas | ⚠️ pyqtgraph 实现，未接入 |

## 新人阅读顺序

1. `architecture.md` (本文) — 全局视图
2. `startup-and-lifecycle.md` — 启动流程
3. `ui.md` — 界面层
4. `annotation.md` — 标注核心
5. `inference.md` — 自动标注推理
6. `training.md` — 训练管线
7. `model-export.md` — 模型导出
8. `dataset.md` — 数据集构建
9. `large-image.md` — 大图切分
10. `task-execution.md` — 后台作业系统
11. `dependencies.md` — 外部依赖
