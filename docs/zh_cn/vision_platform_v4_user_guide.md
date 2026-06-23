# X-AnyLabeling V4 视觉算法平台 — 用户指南

> 分支: `vision_platfrom` | 版本: 4.0.0-beta.7 | 日期: 2026-06-06

---

## 目录

1. [启动方式](#1-启动方式)
2. [CLI 子命令（无 GUI）](#2-cli-子命令无-gui)
3. [启动参数（GUI 模式）](#3-启动参数gui-模式)
4. [V4 平台工作台（--platform）](#4-v4-平台工作台--platform)
5. [配置文件（.xanylabelingrc）](#5-配置文件xanylabelingrc)
6. [环境变量](#6-环境变量)
7. [快捷键](#7-快捷键)
8. [模型中心切换](#8-模型中心切换)
9. [远程推理服务](#9-远程推理服务)
10. [训练 Worker（内部）](#10-训练-worker内部)

---

## 1. 启动方式

### GUI 标准模式（标注工具）

```powershell
python anylabeling/app.py
# 或
python anylabeling/app.py --filename D:\images\photo.jpg
```

启动传统 X-AnyLabeling 标注界面（MainWindow）。

### GUI 平台模式（V4 工作台）⚠️ vision_platfrom 新增

```powershell
python anylabeling/app.py --platform
```

启动 V4 视觉算法平台工作台（WorkbenchWindow），包含项目管理、数据工作区、训练、评估、导出等完整流水线。

### 直接打开 V4 项目

```powershell
python anylabeling/app.py --platform --filename D:\my_project\
```

如果 `D:\my_project\` 是有效的 V4 项目目录，工作台启动后会自动加载该项目。

---

## 2. CLI 子命令（无 GUI）

这些子命令不启动图形界面，在终端直接输出结果后退出。

| 命令 | 用途 | 示例 |
|------|------|------|
| `help` | 显示帮助信息 | `python anylabeling/app.py help` |
| `checks` | 显示系统信息、Python 版本、依赖包版本 | `python anylabeling/app.py checks` |
| `version` | 显示版本号 | `python anylabeling/app.py version` |
| `config` | 显示当前配置文件路径 | `python anylabeling/app.py config` |
| `convert` | 运行标签格式转换（无 GUI） | 见下方详细说明 |

### convert 子命令详细参数

```powershell
# 列出所有支持的转换任务
python anylabeling/app.py convert

# 查看某个任务的帮助
python anylabeling/app.py convert --task yolo2xlabel

# 执行转换
python anylabeling/app.py convert \
    --task yolo2xlabel \
    --mode detect \
    --images ./images \
    --labels ./labels \
    --output ./output \
    --classes classes.txt \
    --skip-empty-files
```

支持的转换任务包括：`yolo2xlabel`, `xlabel2yolo`, `xlabel2voc`, `xlabel2coco`, `xlabel2dota`, `xlabel2mask`, `xlabel2mot`, `xlabel2odvg`, `xlabel2pporc`, `xlabel2vlm_r1_ovd` 及其反向转换。

**convert 子命令参数：**

| 参数 | 说明 |
|------|------|
| `--task <name>` | 转换任务名称 |
| `--images <path>` | 图片目录路径 |
| `--labels <path>` | 标签目录路径 |
| `--output <path>` | 输出目录路径 |
| `--classes <path>` | 类别文件路径 |
| `--pose-cfg <path>` | 姿态估计配置文件路径 |
| `--mode <mode>` | 转换模式（如 detect, segment, pose 等） |
| `--mapping <path>` | 标签映射表文件路径 |
| `--skip-empty-files` | 跳过空输出文件（仅支持 xlabel2yolo / xlabel2voc） |

---

## 3. 启动参数（GUI 模式）

以下参数在启动 GUI 时生效。

### 文件和输出

| 参数 | 简写 | 说明 |
|------|------|------|
| `--filename [PATH]` | — | 启动时打开指定图片或目录 |
| `--output PATH` | `-O`, `-o` | 输出文件（.json）或输出目录 |
| `--config PATH/YAML` | — | 自定义配置文件路径或 YAML 字符串 |

### V4 平台 ⚠️ vision_platfrom 新增

| 参数 | 说明 |
|------|------|
| `--platform` | 启动 V4 视觉算法平台工作台（项目流水线模式） |

### 调试与诊断

| 参数 | 说明 |
|------|------|
| `--reset-config` | 重置 Qt 配置（清除窗口位置/大小等状态）。执行后立即退出 |
| `--logger-level LEVEL` | 日志级别：`debug`, `info`(默认), `warning`, `error`, `fatal` |
| `--no-auto-update-check` | 禁用启动时的自动更新检查 |

### Qt 平台与性能

| 参数 | 说明 |
|------|------|
| `--qt-platform PLUGIN` | 强制 Qt 平台插件，如 `xcb`, `wayland`（Linux 下有用） |
| `--qt-image-allocation-limit MB` | 覆盖 Qt 图片分配内存上限（默认 256 MB）。设为 `0` 禁用限制 |

### 标注行为

| 参数 | 说明 |
|------|------|
| `--nodata` | 不在 JSON 中存储图片 base64 数据（减小文件体积） |
| `--autosave` | 切换图片时自动保存标注 |
| `--nosortlabels` | 不按字母排序标签列表 |
| `--flags FLAGS` | 逗号分隔的 flag 列表，或包含 flags 的文件路径 |
| `--labelflags YAML` | 标签级 flag 的 YAML 字符串或 JSON 文件路径 |
| `--labels LABELS` | 逗号分隔的标签列表，或包含 labels 的文件路径 |
| `--validatelabel exact` | 启用标签校验（仅支持 `exact` 模式） |
| `--keep-prev` | 保留上一帧的标注（视频标注时使用） |
| `--work-dir PATH` | 工作目录（存放配置和数据文件），默认为 `~` |

### 使用示例

```powershell
# 启用调试日志
python anylabeling/app.py --logger-level debug

# 打开图片并禁用图片数据存储
python anylabeling/app.py --filename D:\img.jpg --nodata

# 加载自定义配置文件
python anylabeling/app.py --config D:\my_config.yaml

# 设置 Qt 图片分配上限为 1GB
python anylabeling/app.py --qt-image-allocation-limit 1024

# 完整：平台模式 + 调试日志 + 自动打开项目
python anylabeling/app.py --platform --logger-level debug --filename D:\my_project\
```

---

## 4. V4 平台工作台（--platform）⚠️ vision_platfrom 新增

V4 平台工作台是一个全新的项目流水线 UI，与传统标注界面完全独立。

### 4.1 界面布局

```
┌──────────────────────────────────────────────────────────────┐
│ Menu bar: File / Project / Help                             │
├──────────────────────────────────────────────────────────────┤
│ Navigation: Data → Label → Train → Evaluate → Infer → Export │
├──────────┬────────────────────────┬─────────────────────────┤
│ Project  │  QStackedWidget        │  Inspector              │
│ Explorer │  (工作区页面)           │  (属性查看器)            │
│ (左侧)   │                        │                         │
├──────────┴────────────────────────┴─────────────────────────┤
│ Job Console (底部任务控制台)                                  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 六步流水线导航

| 步骤 | 页面 | 功能 |
|------|------|------|
| **Data** | DataWorkspace | 数据集管理、导入图片、配置切分参数 |
| **Label** | 内嵌 LabelingWidget | 标注画布（复用现有标注工具全部功能） |
| **Train** | TrainWorkspace | 配置训练参数、选择算法、启动训练 |
| **Evaluate** | EvaluateWorkspace | 选择运行记录、执行评估、查看指标 |
| **Infer** | （开发中） | 推理验证 |
| **Export** | ExportWorkspace | 导出 ONNX 模型、查看导出产物 |

### 4.3 项目首页

启动平台后首先看到 ProjectHomeWidget：
- **New Project** — 创建新的 V4 项目（选择目录，自动生成项目骨架）
- **Open Project** — 打开已有 V4 项目
- **Recent Projects** — 最近打开的项目列表（最多 10 个）

### 4.4 项目浏览器

左侧树形控件显示项目结构：
```
Project Name/
├── images/          # 图片目录
├── annotations/     # 标注文件
├── builds/          # 数据集构建记录
├── runs/            # 训练运行记录
├── exports/         # 导出模型
└── jobs/            # 后台任务日志
```

### 4.5 任务控制台（Job Console）

底部面板显示所有后台任务的实时状态：
- 任务名称、状态（pending/running/completed/failed/cancelled）
- 进度信息和日志输出
- 支持取消运行中的任务

### 4.6 检查器（Inspector）

右侧面板用于查看选中标注形状的详细属性（坐标、标签、置信度等）。

---

## 5. 配置文件（.xanylabelingrc）

配置文件默认位于工作目录下的 `.xanylabelingrc`（YAML 格式）。

### 5.1 基本设置

```yaml
language: en_US          # 界面语言
theme: auto              # 主题: auto, light, dark
model_hub: github        # 模型下载源: github, modelscope
device: null             # 设备: null(自动), CPU, GPU
auto_save: true          # 切换图片时自动保存
store_data: false        # 是否在 JSON 中存储图片 base64 数据
```

### 5.2 显示控制

```yaml
show_masks: true         # 显示 mask
show_texts: true         # 显示文本
show_labels: true        # 显示标签
show_scores: true        # 显示分数
show_degrees: false      # 显示角度
show_shapes: true        # 显示形状
show_linking: true       # 显示关联线
show_attributes: true    # 显示属性
```

### 5.3 画布设置

```yaml
canvas:
  epsilon: 10.0                    # 吸附容差（像素）
  double_click: close              # 双击行为: close(闭合多边形) / None
  double_click_edit_label: true    # 双击已编辑形状打开标签编辑器
  num_backups: 10                  # 最大撤销次数
  crosshair:
    show: true                     # 显示十字准线
    width: 2.0                     # 线宽
    color: "#00FF00"               # 颜色
    opacity: 0.5                   # 透明度
  rotation:
    large_increment: 1.0           # Z/V 键旋转步长（度）
    small_increment: 0.1           # X/C 键旋转步长（度）
  brush:
    point_distance: 25.0           # 笔刷绘制模式最小点距
  cuboid:
    default_depth_vector: [24.0, -24.0]
    min_depth: 5.0
  mask:
    opacity: 80                    # mask 透明度 (0-255)
```

### 5.4 形状样式

```yaml
shape:
  line_color: [0, 255, 0, 128]
  fill_color: [220, 220, 220, 150]
  fill_opacity: 128
  vertex_fill_color: [0, 255, 0, 255]
  select_line_color: [255, 255, 255, 255]
  select_fill_color: [0, 255, 0, 155]
  hvertex_fill_color: [255, 255, 255, 255]
  point_size: 10
  line_width: 4
```

### 5.5 Dock 窗口

```yaml
flag_dock:       { show: true, closable: false, movable: false, floatable: false }
label_dock:      { show: true, closable: false, movable: false, floatable: false }
shape_dock:      { show: true, closable: false, movable: false, floatable: false }
description_dock:{ show: true, closable: false, movable: false, floatable: false }
file_dock:       { show: true, closable: false, movable: false, floatable: false }
```

### 5.6 标注自动行为

```yaml
display_label_popup: true       # 显示标签弹窗
keep_prev: false                # 保留上一帧标注
keep_prev_scale: false          # 保留上一帧缩放
keep_prev_brightness: false     # 保留上一帧亮度
keep_prev_contrast: false       # 保留上一帧对比度
auto_use_last_label: false      # 自动使用上次标签
auto_use_last_gid: false        # 自动使用上次组 ID
auto_highlight_shape: true      # 自动高亮形状
auto_switch_to_edit_mode: true  # 自动切换到编辑模式
```

### 5.7 训练设置

```yaml
training:
  ultralytics:
    project_readonly: true   # 训练项目只读模式
```

### 5.8 远程推理服务

```yaml
remote_server_settings:
  server_url: http://127.0.0.1:8000
  api_key: null
  timeout: 180
```

### 5.9 自定义模型与快捷键

```yaml
custom_models: []       # 自定义模型列表
digit_shortcuts: null   # 数字快捷键
```

配置文件可覆盖所有快捷键（见第 7 节默认值）。

---

## 6. 环境变量

X-AnyLabeling 在启动时自动设置以下环境变量：

| 变量 | 值 | 说明 |
|------|-----|------|
| `MKL_NUM_THREADS` | `1` | 限制 Intel MKL 线程数，防止 Mac M1 上的 bus error |
| `NUMEXPR_NUM_THREADS` | `1` | 限制 NumExpr 线程数 |
| `OMP_NUM_THREADS` | `1` | 限制 OpenMP 线程数 |
| `QT_LOGGING_RULES` | `*.debug=false;qt.gui.icc=false` | 禁用 Qt 调试日志和 ICC 配置文件警告 |
| `QT_QPA_PLATFORM` | 由 `--qt-platform` 设置 | 强制 Qt 平台插件 |

---

## 7. 快捷键

以下为默认快捷键（可在 `.xanylabelingrc` → `shortcuts` 中覆盖）。

### 文件操作

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+W` | 关闭当前文件 |
| `Ctrl+I` | 打开图片 |
| `Ctrl+O` | 打开视频 |
| `Ctrl+U` | 打开目录 |
| `Ctrl+S` | 保存 |
| `Ctrl+Shift+S` | 另存为 |
| `Ctrl+Delete` | 删除当前文件 |
| `Ctrl+Shift+Delete` | 删除图片文件 |
| `Ctrl+Q` | 退出 |

### 导航

| 快捷键 | 功能 |
|--------|------|
| `D` | 下一张 |
| `A` | 上一张 |
| `Ctrl+Shift+D` | 下一个未审核 |
| `Ctrl+Shift+A` | 上一个未审核 |
| `Ctrl+Alt+K` | 切换审核状态 |

### 视图

| 快捷键 | 功能 |
|--------|------|
| `Ctrl++` | 放大 |
| `Ctrl+-` | 缩小 |
| `Ctrl+=` | 原始大小 |
| `Ctrl+F` | 适应窗口 |
| `Ctrl+Shift+F` | 适应宽度 |
| `F9` | 显示导航器 |
| `Ctrl+G` | 显示总览 |
| `Ctrl+M` | 切换 mask 显示 |
| `Ctrl+T` | 切换文本显示 |
| `Ctrl+L` | 切换标签显示 |
| `Ctrl+H` | 切换形状可见性 |
| `Ctrl+Alt+C` | 切换对比视图 |

### 标注工具

| 快捷键 | 功能 |
|--------|------|
| `P` | 创建多边形 |
| `Ctrl+N` | 笔刷多边形 |
| `R` | 创建矩形 |
| `Ctrl+R` | 创建立方体 |
| `O` | 创建旋转框 |
| `T` | 创建四边形 |
| `Ctrl+J` | 编辑多边形 |
| `Delete` | 删除多边形 |
| `Ctrl+D` | 复制多边形 |
| `Ctrl+C` | 复制 |
| `Ctrl+V` | 粘贴 |
| `Ctrl+Z` | 撤销 |
| `Ctrl+E` | 编辑标签 |
| `Backspace` | 删除选中点 |
| `Ctrl+Shift+P` | 在边上添加点 |

### 组与选择

| 快捷键 | 功能 |
|--------|------|
| `G` | 组合选中形状 |
| `U` | 取消组合 |
| `S` | 隐藏选中多边形 |
| `W` | 显示隐藏多边形 |
| `Ctrl+Shift+M` | 合并选中形状 |

### 自动标注（SAM 等）

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+A` | 自动标注（单张） |
| `Ctrl+B` | 自动运行（批量） |
| `Q` | 添加点（SAM 模式） |
| `E` | 删除点（SAM 模式） |
| `I` | 运行 SAM |
| `B` | 清除 SAM 提示 |
| `F` | 完成对象（SAM 模式） |

### AI 工具

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+1` | 打开 Chatbot |
| `Ctrl+2` | 打开 VQA |
| `Ctrl+3` | 打开分类器 |
| `Ctrl+4` | 打开 PPOCR |

### 标签操作

| 快捷键 | 功能 |
|--------|------|
| `Alt+L` | 编辑标签列表 |
| `Alt+S` | 编辑形状 |
| `Alt+D` | 数字快捷键 |
| `Alt+G` | 编辑组 ID |
| `Ctrl+Y` | 切换自动使用上次标签 |
| `Ctrl+Shift+G` | 切换自动使用上次组 ID |
| `Ctrl+Shift+N` | 循环浏览标签 |
| `Ctrl+Shift+C` | 循环选择标签 |

---

## 8. 模型中心切换

配置文件中的 `model_hub` 选项控制模型下载源：

```yaml
model_hub: github      # 从 GitHub 下载（国际用户）
# model_hub: modelscope  # 从 ModelScope 下载（国内用户）
```

可通过 CLI 设置：
```powershell
python anylabeling/app.py --config "model_hub: modelscope"
```

---

## 9. 远程推理服务

支持将自动标注请求发送到远程推理服务器：

```yaml
remote_server_settings:
  server_url: http://127.0.0.1:8000
  api_key: null           # API 密钥
  timeout: 180            # 请求超时时间（秒）
```

---

## 10. 训练 Worker（内部）

```powershell
python anylabeling/app.py train-worker --payload '<JSON>'
```

这是一个**隐藏的内部命令**（`argparse.SUPPRESS`），由 V4 平台的 `JobService` 通过子进程调用。普通用户不需要直接使用。

`--payload` 参数是一个 JSON 字符串，包含训练任务所需的全部配置信息（任务类型、数据路径、模型参数、训练参数等）。

---

## 附录 A：V4 平台与旧版对比

| 功能 | 旧版 MainWindow | V4 平台（--platform） |
|------|----------------|---------------------|
| 标注画布 | ✅ 完整 | ✅ 内嵌复用 |
| 标签格式转换 | ✅ | ✅ |
| 自动标注 | ✅ 多模型 | ✅ 复用 |
| 训练 | 对话框模式 | 工作区页面 |
| 评估 | ❌ | ✅ EvaluateWorkspace |
| 数据集构建 | ❌ | ✅ DataWorkspace |
| ONNX 导出 | 部分支持 | ✅ ExportWorkspace |
| 项目化管理 | ❌ | ✅ 文件化项目 |
| 后台任务控制台 | ❌ | ✅ JobConsole |
| 项目浏览器 | ❌ | ✅ 树形结构 |
| 属性检查器 | ❌ | ✅ Inspector |
| 超大图支持 | ❌ | ✅ 切分/合并 |

---

## 附录 B：V4 平台项目目录结构

```
my_project/
├── project.json          # 项目元数据
├── labels.json           # 标签定义
├── split_manifest.jsonl  # 数据切分清单
├── images/               # 原始图片
├── annotations/          # 标注 JSON 文件
├── builds/               # 数据集构建输出
│   └── <build_id>/
│       ├── build.json    # 构建元数据（原子写入）
│       ├── data.yaml     # YOLO 数据配置
│       └── ...           # 训练就绪的数据集
├── runs/                 # 训练运行输出
│   └── <run_id>/
│       ├── run.json      # 运行元数据（原子写入）
│       ├── request.json  # 训练请求参数
│       └── ...           # 模型权重、日志等
├── exports/              # 导出模型
│   └── <model_id>/
│       ├── model.json    # 模型元数据（原子写入）
│       ├── _READY        # 导出完成标记
│       └── *.onnx        # ONNX 模型文件
└── jobs/                 # 后台任务
    └── <job_id>/
        ├── request.json  # 任务请求
        ├── events.jsonl  # 任务事件日志
        ├── stdout.log    # 标准输出
        └── stderr.log    # 标准错误
```
