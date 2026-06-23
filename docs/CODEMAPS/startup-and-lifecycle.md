<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~800 -->

# 启动与生命周期 (Startup & Lifecycle)

## main() 启动序列 (`anylabeling/app.py:47`)

```
 1. multiprocessing.freeze_support()           ← PyInstaller 必需
 2. 环境固化                                   ← MKL/OMP 线程=1, 抑制 Qt ICC 警告
 3. 修复 sys.path[0]                           ← 防止 platform 模块遮蔽 stdlib platform
 4. argparse (5 个子命令)                      ← help|checks|version|config|train-worker|convert
 5. set_work_directory(args.work_dir)          ← 默认 ~/
 6. 子命令分发 → 若匹配则早返回 (不启动 GUI)
 7. 延迟导入                                   ← MainWindow, logger, theme, translations, resources
 8. 3 层配置合并                               ← defaults → ~/.xanylabelingrc → CLI
 9. 日志级别, Qt 平台, 图像内存限制
10. 输出文件/目录解析, 翻译加载
11. OpenGL 共享上下文, QApplication 创建
12. 主题: palette → stylesheet
13. 模式分支:
    ├── --platform → WorkbenchWindow(config)
    │   └── 若 --filename 是有效 V4 目录 → set_project()
    └── 否则 → MainWindow(app, config, filename, output)
14. QTimer.singleShot(2000ms) → 更新检查 (除非 --no-auto-update-check)
15. win.showMaximized() → app.exec()
```

## CLI 参数 (`app.py:47-222`)

| 参数 | 说明 |
|------|------|
| `--filename` / `-f` | 打开图像/目录/项目文件 |
| `--output` / `-O` | 标注输出文件路径 |
| `--config` / `-c` | 自定义配置文件路径 |
| `--reset-config` | 清除 QSettings 重置窗口几何 |
| `--no-auto-update-check` | 跳过启动时更新检查 |
| `--work-dir` / `-w` | 工作目录 (模型缓存路径) |
| `--platform` / `-p` | 启动 V4 平台工作台模式 |
| `--logger-level` | 日志级别: debug/info/warning/error/critical |

## 子命令

| 子命令 | 处理函数 | 说明 |
|--------|---------|------|
| `help` | `_subcommand_help()` | 显示帮助信息 |
| `checks` | `run_checks()` | 系统诊断 (Python/PyTorch/ONNX/CUDA) |
| `version` | 打印 `__version__` | 显示版本号 |
| `config` | `_subcommand_config()` | 管理配置文件 |
| `train-worker` | `run_training_worker_command()` | 训练子进程入口 |
| `convert` | 标签格式转换 | YOLO/VOC/COCO/DOTA/MOT ↔ X-AnyLabeling |

## 配置系统 (`anylabeling/config.py`)

| 层级 | 来源 | 键数 |
|------|------|------|
| 默认值 | `configs/xanylabeling_config.yaml` (内置资源) | ~60 |
| 用户 | `~/.xanylabelingrc` (YAML) | 覆盖 |
| CLI | argparse 覆写 | 最终覆盖 |

配置键迁移: `epsilon` → `canvas.epsilon`, `show_cross_line` → `canvas.crosshair.show`。
验证: `validate_label` (None|"exact"), `qt_allocation_limit`, `shape_color`, 重复标签。

## 设备检测 (`views/labeling/utils/device_manager.py`)

单例 DeviceManager, 3 层优先级:
1. 环境变量 `X_ANYLABELING_DEVICE` (如 `CPU`, `CUDA:0`)
2. 配置文件 `device` 键
3. `onnxruntime.get_available_providers()` 自动检测

结果缓存整个会话。

## 主题 (`views/labeling/utils/theme.py`)

`init_theme("auto")`:
- WSL → 通过 `reg.exe` 从 Windows 宿主机查询
- 否则 → `darkdetect` 库
- 默认 `"light"`
- 38 个颜色令牌, 430 行暗色 QSS 样式表
- Windows 上通过 QPalette 回退原生样式

## 窗口生命周期

| 窗口 | 类 | 创建时机 |
|------|-----|---------|
| MainWindow | `views/mainwindow.py` | `--platform` 未设置时 |
| WorkbenchWindow | `views/platform/workbench_window.py` | `--platform` 设置时 |

### MainWindow 生命周期
1. `__init__`: 创建 LabelingWrapper → LabelingWidget, 设置 statusBar
2. `showMaximized()` → `raise_()` → `app.exec()`
3. `closeEvent()` → 委托给 `LabelingWrapper.closeEvent()`, 保存窗口几何到 QSettings

### WorkbenchWindow 生命周期
1. `__init__`: 创建 ProjectSession, Shell 组件, 9 个工作区页面
2. `set_project(path)` → `ProjectSession.open_project()` 初始化所有服务
3. 服务列表: AssetRepository, ImportService, TrainingService, EvaluationService, ExportService, InferenceService, DatasetBuildService, ModelRegistryService
4. 域导航通过 `WorkflowState` 自动管理: 完成训练 → 自动跳到评估

## 关闭

无显式 GPU 内存清理、模型卸载或临时文件清理。Window 级别 closeEvent 保存几何状态。

## 资源加载

`anylabeling/resources/__init__.py` — 包标记 (空文件)。实际资源在 `resources.py` (~43K 行, pyrcc6 编译), 在 `app.py:262` 通过副作用导入加载。
