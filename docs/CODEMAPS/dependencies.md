<!-- Generated: 2026-06-25 | Files scanned: 523 | Token estimate: ~600 | Updated: dead code cleanup -->

# 依赖 (Dependencies)

## Python >=3.11

## 核心运行时

| 包 | 版本 | 用途 |
|----|------|------|
| `PyQt6` | >=6.6.0 | GUI 框架 |
| `opencv-contrib-python-headless` | >=4.7.0 | 图像 I/O, DNN 推理 |
| `onnxruntime` / `onnxruntime-gpu` | >=1.15.0 / >=1.18.1 | ONNX 推理引擎 |
| `onnx` | >=1.15.0 | ONNX 模型构建/检查 |
| `pillow` | >=7.1.2 | PIL 图像处理 |
| `numpy` | >=2.0 (CPU) / <2.0 (CUDA 11) | 张量运算 |
| `scipy` | >=1.4.1 | 科学计算 |
| `lapx` | >=0.5.5 | 线性分配 (跟踪器) |
| `qimage2ndarray` | >=1.10.0 | QImage ↔ numpy 桥接 |
| `PyYAML` | — | YAML 配置 |
| `matplotlib` | — | 训练/评估图表 |
| `tqdm` | >=4.64.0 | 进度条 |
| `shapely` | — | 几何操作 (OBB/Polygon 分割) |
| `pyclipper` | — | 多边形裁剪 (PaddleOCR) |
| `darkdetect` | >=0.8.0 | OS 暗色模式检测 |
| `tokenizers` | — | BERT 分词器 (Grounding DINO) |
| `pillow-heif` | >=0.18.0 | HEIF 图像支持 |
| `psutil` | — | 系统资源监控 |
| `openai` | — | API 客户端 (仅远程模型) |
| `requests` | — | HTTP (仅远程模型代理) |
| `natsort` | >=8.1.0 | 自然排序 |
| `json_repair` | — | JSON 修复 |
| `jsonlines` | — | JSONL 读写 |
| `markdown` | — | Markdown 渲染 (Chatbot) |
| `importlib_metadata` | — | 包元数据 |
| `six` | — | Python 2/3 兼容 |
| `termcolor` | — | 终端颜色 |

## 开发依赖

| 包 | 用途 |
|----|------|
| `pytest` | 测试 (~111 测试文件) |
| `black` | 代码格式化 (行宽 79) |
| `flake8` | Linting (复杂度 18) |
| `build` | 构建前端 |
| `pyinstaller` | 可执行文件打包 |
| `PySide6` | 替代 Qt 绑定 (dev 环境) |
| `twine` | PyPI 发布 |

## GPU 后端可选

| Extra | 内容 |
|-------|------|
| `[cpu]` | onnxruntime, numpy >=2.0 |
| `[gpu]` | onnxruntime-gpu >=1.18.1, numpy >=2.0 (CUDA 12.x) |
| `[gpu-cu11]` | onnxruntime-gpu >=1.15.0,<1.19.0, numpy <2.0 (CUDA 11.x) |

uv 互斥: `[tool.uv].conflicts` 防止同时安装 cpu+gpu。

## 构建系统

- `setuptools>=70.0.0` + `wheel`
- 单一 `pyproject.toml` with `[tool.setuptools.packages.find]`
- 包名: `x-anylabeling-cvhub`
- CLI 入口: `xanylabeling` → `anylabeling.app:main`

## 可选推理后端

| 后端 | 所需包 | 用途 |
|------|--------|------|
| ONNX Runtime | `onnxruntime` / `onnxruntime-gpu` | 主要推理引擎 |
| TensorRT | `tensorrt` + `cuda-python` | NVIDIA GPU 推理 |
| OpenCV DNN | `opencv-contrib-python-headless` | CPU/GPU 推理 |

## 离线桌面应用

本项目为离线桌面应用。无数据库、云 API 或外部服务依赖。仅有的网络操作:
- `update_checker.py` — 可选启动时更新检查 (`--no-auto-update-check` 禁用)
- `remote_server.py` — 可选远程模型 API 代理 (需要用户配置)
- 模型下载 — 从 GitHub Releases / ModelScope 镜像下载 ONNX 模型文件 (缓存到本地)

## 硬编码路径

| 路径 | 说明 |
|------|------|
| `~/.xanylabelingrc` | 用户配置文件 |
| `~/.xanylabeling_data/models/` | 模型下载缓存 |
| `{work_dir}/xanylabeling_data/models/` | 自定义工作目录下的模型缓存 |

## 平台支持

| 平台 | 状态 |
|------|------|
| Windows | ✅ 完整支持 |
| Linux | ✅ 完整支持 |
| macOS | ✅ 支持 (M1 有已知 bus error 修复) |
| WSL | ✅ 部分支持 (窗口几何恢复禁用) |
