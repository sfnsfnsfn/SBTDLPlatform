<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~750 -->

# 任务执行 — 作业系统 (Task Execution)

## 作业状态机 (`platform/workers/protocol.py`)

`JobState(Enum)` — 7 个状态:
```
QUEUED → STARTING → RUNNING → COMPLETED | FAILED
                    ↓
               CANCELLING → CANCELLED
```

`VALID_TRANSITIONS` dict。`TERMINAL_STATES = {COMPLETED, FAILED, CANCELLED}`。
`InvalidStateTransition(ValueError)` 用于非法转换。

## 持久化布局

```
jobs/{job_id}/
├── request.json      ← JobRequest (job_kind, params, job_id)
├── state.json        ← JobState (原子 tmp→replace)
├── events.jsonl      ← JobEvent 追加行 (JSONL)
├── stdout.log        ← 进程 stdout
├── stderr.log        ← 进程 stderr
└── stop.flag         ← 取消信号
```

## 关键类型

| 类型 | 字段 | 说明 |
|------|------|------|
| `JobRequest` (dataclass) | job_kind, params, job_id (自动生成) | 作业创建请求 |
| `JobEvent` (dataclass) | seq, type, payload, timestamp | 事件类型: started/progress/metric/artifact/completed/failed/log |
| `CancellationToken` (dataclass) | flag_path → `stop.flag` | `is_cancelled` 每次访问重新检查; `cancel()` 创建 stop.flag |

### 协议辅助函数

`write_state(job_dir, state)` / `read_state(job_dir)` — 原子状态持久化。
`read_events(job_dir)` / `append_event(job_dir, event)` — JSONL 事件日志。
`try_transition_state(job_dir, from_state, to_state)` / `transition_state(...)` — 状态转换验证。

## JobService (`platform/application/job_service.py`, 192L)

| 方法 | 功能 |
|------|------|
| `create_job(request, command) → job_id` | 创建并启动作业 |
| `cancel_job(id)` | 取消作业 |
| `wait_job(id, timeout) → exit_code` | 等待作业完成 |
| `get_job_state/events/logs(id)` | 查询作业状态 |
| `list_jobs()` | 列出所有作业 |
| `is_terminal(id)` | 检查是否终止状态 |

## ProcessJobRunner (`platform/infrastructure/process_job_runner.py`, 403L)

```
start(request, command)
  → 创建作业目录, 写入 request.json
  → subprocess.Popen(command, cwd=job_dir, stdout/err=日志文件)
  → 状态: QUEUED → STARTING → RUNNING

cancel(job_id)
  → 状态 → CANCELLING, 写入 stop.flag
  → proc.wait(2s) → 超时 → _terminate_process_tree()
    → Windows: taskkill /F /T /PID
    → POSIX: os.killpg(SIGKILL)
  → 状态 → CANCELLED
```

## 线程与进程模型

| 机制 | 用途 | 位置 |
|------|------|------|
| `GenericWorker + QThread` | 模型加载, 推理 | `services/auto_labeling/model_manager.py` |
| `subprocess.Popen` | 训练, 评估, 导出, CLI 推理 | `infrastructure/process_job_runner.py` |
| `threading.Thread` | 训练 stdout 读取循环 | `services/auto_training/ultralytics/trainer.py` |
| `threading.Event` | 训练取消 | `services/auto_training/ultralytics/trainer.py` |
| `threading.Lock` | 推理并发门控 | `services/auto_labeling/model_manager.py` |

**注意:** QThreadPool **未在代码库任何位置使用**。每次调用创建临时线程。

## 训练事件协议

```
父进程读取子进程 stdout 逐行解析:
__XANYLABELING_TRAIN_EVENT__={"event": "training_log", "data": {...}}
```

`TrainingManager` 使用回调模式 (`notify_callbacks`)，非 pyqtSignal。
`TrainingEventRedirector(QObject)` 已定义但未使用。

## WorkflowState (`platform/application/workflow_state.py`, 463L)

跨工作区状态机:
- 跟踪: import_done, config_done, labeling_done, preprocess_done, training_done, evaluation_done, export_done
- 持久化到 `{project_root}/workflow_state.json`
- 自动推进: TRAIN→EVALUATE→EXPORT→MODELS
- 门控: 阻止跳过未完成步骤 (可随时回退)

5 个域状态:
`Domain`: PROJECT / DATA_PREP / TRAIN / EVALUATION_VALIDATION / EXPORT
`DomainState`: domain + status (not_started/ready/in_progress/completed/needs_attention/expired) + reason + prerequisites

## JobConsole (`views/platform/job_console.py`)

底部停靠控件: 作业 ID, 类型, 状态图标, 进度条, 耗时。活跃作业取消按钮。点击展开: stdout/stderr 日志查看器, 事件时间线。

## TaskCenterDrawer (`views/platform/shell/task_center_drawer.py`)

滑出面板: 任务族, 标签, 配置摘要。作业进度列表。

## 实现状态

| 功能 | 状态 |
|------|------|
| 作业状态机 (7 状态) | ✅ |
| JobRequest/JobEvent/CancellationToken | ✅ |
| ProcessJobRunner (子进程) | ✅ |
| JobService (CRUD, 等待, 取消) | ✅ |
| JobConsole UI | ✅ |
| TaskCenterDrawer | ✅ |
| 训练事件协议 | ✅ |
| 进程树终止 (taskkill/killpg) | ✅ |
| WorkflowState 跨步骤状态机 | ✅ |
| 队列 / 优先级 / 调度 | ❌ |
| 重试逻辑 | ❌ |
| 持久化作业历史 | ❌ |
| workers/handlers/ | ❌ 空目录 |
| QThreadPool | ❌ 代码库中未使用 |
