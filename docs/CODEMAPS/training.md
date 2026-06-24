<!-- Generated: 2026-06-25 | Files scanned: 523 | Token estimate: ~850 | Updated: dead code cleanup -->

# 训练 (Training)

## 框架支持

**唯一支持: Ultralytics YOLO** (PyTorch 后端)。
其他架构 (DETR, SAM, GroundingDINO 等) 仅支持推理，无训练适配器。

## 5 种任务类型

| 算法 ID | 任务族 | Ultralytics 任务 |
|----------|--------|-------------------|
| `ultralytics_yolo_classify` | classification | classify |
| `ultralytics_yolo_detect` | detection_hbb | detect |
| `ultralytics_yolo_obb` | detection_obb | OBB |
| `ultralytics_yolo_segment` | instance_segmentation | segment |
| `ultralytics_yolo_pose` | pose | pose |

## 训练管线 (两条路径)

### 路径 A: 历史遗留对话框 (`views/training/` + `services/auto_training/`)

**流程**: 数据准备 → 配置 → 启动 → 监控 → 输出

| 步骤 | 文件 | 说明 |
|------|------|------|
| 数据标签页 | `views/training/ultralytics_dialog.py` | 任务类型选择, 扫描 image_list, 标注摘要表, ≥20 张验证 |
| 配置标签页 | 同上 | 基本/训练/高级/学习率/增强/正则化/检查点 |
| 数据集创建 | `services/auto_training/ultralytics/general.py:create_yolo_dataset()` | 标签验证, 分割, YOLO .txt 写入, data.yaml |
| 训练启动 | `services/auto_training/ultralytics/trainer.py:TrainingManager.start_training()` | JSON payload → subprocess.Popen |
| 进度监控 | 同上 | QTimer 轮询 results.csv + 训练图像 |
| 输出 | `<project>/<name>/weights/best.pt` | 标准 Ultralytics 布局 |

**子进程通信协议:**
```
父进程 → subprocess.Popen(python -m anylabeling.app train-worker --payload <json>)
子进程 stdout → 解析 __XANYLABELING_TRAIN_EVENT__={"event":"training_log","data":{...}}
事件: training_started, training_log, training_completed, training_error
```

**停止:** process.terminate() → 5s 超时 → taskkill /F /T /PID (Win) / os.killpg(SIGKILL) (POSIX)

### 路径 B: V4 平台适配器 (`platform/adapters/ultralytics/`)

| 适配器 | 文件 | 说明 |
|--------|------|------|
| `TrainAdapter` | `train_adapter.py` | TrainRequest → YOLO train() kwargs |
| `ValAdapter` | `val_adapter.py` | YOLO val() |
| `ExportAdapter` | `export_adapter.py` | YOLO export() + 产物保存 |
| `InferenceAdapter` | `inference_adapter.py` | YOLO 推理命令 |
| `DatasetAdapter` | `dataset_adapter.py` | DatasetBuild → data.yaml 桥接 |
| `RunParser` | `run_parser.py` | results.csv / args.yaml 解析 |

全部 6 个能力通过 `AlgorithmRegistry` 注册，按 `adapter_id` 或 `task_family` 查询。

## TrainingService (`platform/application/training_service.py`, 639L)

| 方法 | 功能 |
|------|------|
| `create_run_record(TrainRequest) → Run` | 创建 Run 记录 |
| `start_training(TrainRequest, adapter_id=None) → run_id` | 启动训练 |
| `parse_and_update_run(run_id) → Run` | 训练后指标解析 |
| `validate_training_readiness(run_id) → TrainingReadiness` | 训练前检查 |
| 构建训练命令 | 内联 Python 脚本 → `[sys.executable, "-c", script]` |

## 训练就绪检查 (`platform/domain/training_readiness.py`)

Pre-flight 验证:
- 资产数量 ≥ 最低阈值
- 标注覆盖率 ≥ 50%
- 数据集构建完整性
- 磁盘空间 ≥ 1GB
- GPU 可用 (若请求)
- 模型兼容任务族

## TrainRequest (`platform/adapters/ultralytics/train_adapter.py`)

37 字段 dataclass: task_spec, dataset_build, base_model, epochs, batch, imgsz, device, seed, optimizer (lr0/lrf/momentum/weight_decay/warmup_epochs/cos_lr/amp), augmentation (hsv/degrees/translate/scale/shear/perspective/fliplr/mosaic/mixup/copy_paste/close_mosaic), loss (box/cls/dfl/pose/kobj)

## TrainWorkspace (`views/platform/train_workspace.py`, 1174L)

模式选择 (Quick/High-Accuracy/Custom)。任务/数据集/算法下拉框。超参数表单。可折叠组: Optimizer (8), Augmentation (12), Loss (5)。TrainingMonitor 实时 matplotlib。QTimer 轮询状态。

## TrainReadinessWidget (`views/platform/widgets/train_readiness_widget.py`, 246L)

红绿灯检查卡片: 数据集有效, 标签一致, GPU 可用, 磁盘空间, 模型兼容。全部绿灯才启用 "开始训练"。

## 信号/回调链

```
TrainWorkspace._on_start() → TrainingService.start_training(request)
  → TrainReadinessWidget.validate() → TrainingReadiness checks
  → JobService.create_job() → job ID
  → UltralyticsTrainAdapter.build_train_kwargs()
  → _build_train_command() → 内联 Python 脚本
  → TrainingManager.start_training() → subprocess.Popen
    → thread 读取 stdout → callbacks → UI 更新
  → QTimer 轮询 → parse_and_update_run() → TrainingMonitor + 标签更新
```

## 训后自动流转

训练完成 → WorkflowState 转换到 EVALUATE → 自动导航到 EvaluateWorkspace → 自动对 best.pt 触发评估

## 进程模型

| 操作 | 机制 | 来源 |
|------|------|------|
| 训练 (历史遗留) | subprocess.Popen + JSONL 事件 | `trainer.py:TrainingManager` |
| 训练 (平台) | ProcessJobRunner → subprocess.Popen 内联脚本 | `process_job_runner.py` |
| 进度监控 | QTimer 轮询 + 信号转发 | `ultralytics_dialog.py` |

## 实现状态

| 功能 | 状态 |
|------|------|
| TrainingService | ✅ |
| TrainRequest (37 参数) | ✅ |
| UltralyticsTrainAdapter | ✅ |
| 子进程训练执行 | ✅ |
| 事件协议 (log/complete/error) | ✅ |
| 取消 (优雅 + 强制) | ✅ |
| TrainingMonitor (matplotlib) | ✅ |
| TrainWorkspace UI | ✅ |
| 训练就绪检查 (Pre-flight) | ✅ |
| TrainReadinessWidget | ✅ |
| 训后自动流转 → Eval | ✅ |
| 多 GPU 训练 | ❌ |
| 恢复训练 | ⚠️ 仅 UI 复选框 |
| 非 YOLO 训练 (SAM/DETR/...) | ❌ |
| QThreadPool | ❌ 代码库中未使用 |
