# CLAUDE.md

X-AnyLabeling — 高级自动标注解决方案，集成计算机视觉与多模态 AI。

## 环境搭建

```bash
# CPU 开发环境
pip install -e ".[cpu,dev]"

# GPU (CUDA 12.x) 开发环境
pip install -e ".[gpu,dev]"

# GPU (CUDA 11.x) 开发环境
pip install -e ".[gpu-cu11,dev]"
```

需要 Python >=3.11。

## 常用命令

```bash
# 启动 GUI 应用
xanylabeling
# 或：python -m anylabeling.app

# 运行完整测试套件
pytest

# 运行单个测试文件
pytest tests/path/to/test_file.py

# 使用特定标记运行（排除慢速测试）
pytest -m "not slow"

# Lint 检查
flake8 anylabeling/

# 格式化
black anylabeling/ tests/ tools/

# 类型检查（如已安装 mypy）
mypy anylabeling/
```

## 架构

```
anylabeling/
├── app.py                      # 应用入口点
├── app_info.py                 # 版本信息
├── platform/                   # 平台层（DDD：领域 + 应用 + 基础设施 + 适配器）
│   ├── domain/                 # 领域模型与合约
│   ├── application/            # 用例服务（训练、导出、评估、导入、数据集）
│   ├── infrastructure/         # 项目文件存储、图像源、平铺
│   └── adapters/               # 提供商适配器（Ultralytics 等）
├── services/auto_labeling/     # 自动标注引擎（YOLO、SAM、Grounding-DINO、OCR 等）
├── views/                      # PyQt6 GUI 层
│   ├── labeling/               # 标注画布与视口（支持超大图像平铺）
│   └── platform/               # 平台工作区（训练、导出、评估、数据、标签）
├── configs/                    # 模型与标注配置
├── resources/                  # 静态资源（图像、字体、样式）
├── tools/                      # CLI 工具（标签转换器等）
├── scripts/                    # 构建与开发
└── tests/                      # 镜像源树（~70+ 个测试文件）
```

**分层依赖：** `adapters → application → domain`；`infrastructure → domain`；`views → application/services`。

**关键模式：**
- `AlgorithmRegistry` + `AlgorithmProvider` ABC 用于可插拔模型适配器
- 超大图像的平铺视口（分块渲染、延迟加载）
- ONNX 推理引擎，支持 CPU / CUDA 11.x / CUDA 12.x
- DDD 风格的分层架构，位于 `platform/` 下

## 测试

框架：`pytest`（通过 `pyproject.toml` 下的 `[tool.pytest.ini_options]` 配置）

```toml
# 关键 pytest 配置
addopts = "--doctest-modules --durations=30 --color=yes"
markers = ["slow: skip slow tests unless --slow is set"]
```

测试镜像 `anylabeling/` 源树结构，高覆盖率覆盖：
- `tests/platform/` — 领域合约、应用服务、基础设施、适配器
- `tests/views/` — GUI 组件（标注画布、工作区、视口）
- `tests/e2e/` — 端到端夹具
- `tests/test_models/` — 模型检查、ONNX 导出验证

## 代码风格

- **格式化：** Black，行长 79（`[tool.black] line-length = 79`）
- **Lint：** Flake8（最大复杂度 18，选定的规则：B、C、E、F、W、T4、B9）
- **提交前检查：** 预提交钩子强制 black、flake8、codespell、rstcheck
- **命名：** 遵循 PEP 8；包名称为 `anylabeling`
- **类型提示：** 项目使用 Python 3.11+ 语法；在所有新签名上使用类型提示

## 平台支持

- Windows、Linux、macOS
- CPU 推理（onnxruntime）或 GPU（onnxruntime-gpu，CUDA 11.x / 12.x）
- PyQt6 >=6.6.0（Linux 上 <6.10.0）

## 编码规则

项目级规则位于 `.claude/rules/`，由 Claude Code 自动加载：

| 规则文件 | 内容 |
|-----------|---------|
| `coding-principles.md` | 不可变性、KISS、DRY、YAGNI、错误处理、输入验证 |
| `python-coding-style.md` | PEP 8、black（行长 79）、flake8、命名规范、反模式 |
| `python-patterns.md` | Protocol、dataclass、context manager、生成器、异常层次结构 |
| `python-testing.md` | pytest 规范、AAA 模式、mock、夹具、标记 |

## 代码清理记录

2026-06-25 执行了全面的死代码清理：
- 移除了 57 个未使用的导入（跨 57 个源文件）
- 移除了注释掉的代码块（canvas.py, label_widget.py）
- 移除了 Python <3.8 兼容性分支（sahi/versions.py）
- 保留了有意的副作用导入和第三方代码

## 推荐技能

以下 ECC 技能对本项目有价值（已全局安装）：

| 技能 | 用途 |
|-------|---------|
| `python-patterns` | Python 惯用法：类型提示、dataclass、context manager、生成器 |
| `python-testing` | pytest 夹具、参数化、mock、覆盖率（80%+） |
| `tdd-workflow` | 红-绿-重构循环 — 在实现前编写测试 |
| `verification-loop` | 构建→类型检查→lint→测试→安全检查门控 |
| `coding-standards` | 通用跨语言编码标准 |
| `error-handling` | 检测静默失败和已吞掉的错误 |

> **约束：** 本项目为离线桌面应用。不使用数据库、云服务或需要网络的技能。
