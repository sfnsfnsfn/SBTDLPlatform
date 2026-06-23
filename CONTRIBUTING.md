# X-AnyLabeling 贡献指南

## 项目概述

X-AnyLabeling 是 **Windows/Linux/macOS 离线单机桌面深度学习标注平台**。Python 3.11+, PyQt6 GUI, ONNX Runtime 推理引擎。504 个源文件，87+ 种 AI 模型。

**架构特点：** 双 GUI 模式 (MainWindow 传统标注 + WorkbenchWindow V4 平台)，DDD 四层架构 (`platform/domain/application/infrastructure/adapters`)，子进程隔离训练/推理，不可变领域类型。

## 环境搭建

```bash
git clone https://github.com/CVHub520/X-AnyLabeling.git
cd X-AnyLabeling

# CPU 开发环境
pip install -e ".[cpu,dev]"

# GPU (CUDA 12.x) 开发环境
pip install -e ".[gpu,dev]"

# GPU (CUDA 11.x) 开发环境
pip install -e ".[gpu-cu11,dev]"
```

Python >=3.11 必须。

## 常用命令

| 命令 | 说明 |
|------|------|
| `xanylabeling` | 启动 GUI（传统标注模式） |
| `xanylabeling --platform` | 启动 V4 平台工作台模式 |
| `xanylabeling checks` | 系统诊断信息 |
| `python -m anylabeling.app` | 源码方式启动 |
| `pytest` | 运行全部测试 |
| `pytest -m "not slow"` | 跳过慢速测试 |
| `pytest tests/path/to/test_file.py` | 运行单个测试文件 |
| `black anylabeling/ tests/ tools/` | 代码格式化 |
| `flake8 anylabeling/` | Lint 检查 |
| `mypy anylabeling/` | 类型检查 |

## 编码规范

### 格式化
- **Black**：行长 79（`pyproject.toml` 中 `[tool.black] line-length = 79`）
- **Flake8**：最大复杂度 18，规则集 B/C/E/F/W/T4/B9

### 命名
- 遵循 PEP 8：变量/函数 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE_CASE`
- 布尔值：`is_`/`has_`/`should_`/`can_` 前缀

### 类型提示（必须）
所有新函数签名必须有类型提示：

```python
from typing import Protocol

class LargeImageSource(Protocol):
    def metadata(self) -> ImageMetadata: ...
    def read_region(
        self, rect_l0: RectF, output_size: tuple[int, int]
    ) -> np.ndarray: ...
```

### 不可变性（CRITICAL）
始终创建新对象，禁止原地修改：

```python
# 错误
def modify_shape(shape: Shape, field: str, value: Any) -> None:
    shape.__dict__[field] = value  # 就地修改

# 正确
def update_shape(shape: Shape, field: str, value: Any) -> Shape:
    return dataclasses.replace(shape, **{field: value})  # 新副本
```

### 文件组织
- 200–400 行（正常），800 行（上限）
- 按功能/领域组织，非按类型
- 从大模块提取工具函数

### 文档字符串（Google 风格）

```python
def predict_shapes(
    self, image: np.ndarray, filename: str | None = None
) -> AutoLabelingResult:
    """对输入图像执行模型推理并返回标注结果。

    Args:
        image: BGR 格式的 numpy 数组，shape (H, W, 3)。
        filename: 可选图像路径，用于元数据记录。

    Returns:
        包含检测到的形状列表的 AutoLabelingResult。

    Raises:
        ONNXInferenceError: ONNX 会话推理失败时。
    """
```

## 架构分层

修改代码前确认工作在正确的层：

| 层 | 目录 | 职责 | 规则 |
|------|------|------|------|
| 领域 | `platform/domain/` | 不可变 dataclass DTO | 无 I/O，无 Qt 导入 |
| 应用 | `platform/application/` | 用例服务 | 只依赖领域层 |
| 基础设施 | `platform/infrastructure/` | 图像 I/O，存储，子进程 | 只依赖领域层 |
| 适配器 | `platform/adapters/` | 第三方框架集成 | 依赖应用层接口 |
| 推理服务 | `services/auto_labeling/` | 87+ 种模型推理 | 独立于平台层 |
| 训练服务 | `services/auto_training/` | YOLO 训练管线 | 独立于平台层 |
| 视图 | `views/` | PyQt6 GUI | 依赖应用服务 |

分层依赖：`adapters → application → domain`；`infrastructure → domain`；`views → application/services`

## 测试

框架：**pytest**。配置：`pyproject.toml` 中 `[tool.pytest.ini_options]`。

```toml
addopts = "--doctest-modules --durations=30 --color=yes"
markers = ["slow: skip slow tests unless --slow is set"]
```

测试目录镜像源码结构，覆盖率目标 **>=80%**：

| 目录 | 覆盖内容 |
|------|----------|
| `tests/platform/` | 领域合约、应用服务、基础设施、适配器 |
| `tests/views/` | GUI 组件（画布、工作区、视口） |
| `tests/e2e/` | 端到端夹具 |
| `tests/test_models/` | 模型检查、ONNX 导出验证 |

## 关键模式

| 模式 | 用途 | 位置 |
|------|------|------|
| Protocol 抽象 | 无运行时成本的接口契约 | `platform/infrastructure/image_sources/base.py` |
| frozen dataclass | 不可变领域对象 | `platform/domain/` |
| AlgorithmRegistry | 可插拔模型适配器注册 | `platform/adapters/registry.py` |
| ProcessJobRunner | 子进程隔离长耗时操作 | `platform/infrastructure/process_job_runner.py` |
| AtomicWriter | 原子文件写入防损坏 | `platform/infrastructure/atomic_writer.py` |
| ModelManager if-elif | 87 种模型类型分发 | `services/auto_labeling/model_manager.py` |

## 新增模型

在 `services/auto_labeling/` 下添加新文件，继承 `Model`：

```python
class MyNewModel(Model):
    class Meta:
        required_config_names = ["model_path", "conf_threshold"]
        widgets = ["button_run", "slider_conf"]
        output_modes = {"rectangle": "Rectangle"}

    def predict_shapes(
        self, image: np.ndarray, filename: str | None = None
    ) -> AutoLabelingResult:
        blob = self.preprocess(image)
        outputs = self.net.get_ort_inference(blob)
        shapes = self.postprocess(outputs)
        return AutoLabelingResult(shapes=shapes, replace=True)

    def unload(self):
        del self.net
```

然后在 `model_manager.py` 的 if-elif 链中添加分支，并在 `configs/models.yaml` 注册。

## PR 检查清单

- [ ] `black` 格式化通过（行长 79）
- [ ] `flake8` 无新增违规
- [ ] 新函数有类型提示和文档字符串
- [ ] 新增行为有对应测试
- [ ] 无硬编码密钥/密码/token
- [ ] 无 `print`/`console.log` 调试语句
- [ ] 领域类型使用 frozen dataclass
- [ ] 文件 <800 行，函数 <50 行
- [ ] 未引入新第三方依赖（未经讨论）
- [ ] `xanylabeling checks` 通过

## 更多资源

| 资源 | 位置 |
|------|------|
| AI 编码指南 | `CLAUDE.md` |
| 编码原则 | `.claude/rules/coding-principles.md` |
| Python 风格 | `.claude/rules/python-coding-style.md` |
| Python 模式 | `.claude/rules/python-patterns.md` |
| Python 测试 | `.claude/rules/python-testing.md` |
| 架构 Codemaps | `docs/CODEMAPS/` (11 个文件) |
| 新人代码导览 | `.tours/new-joiner-xanylabeling.tour` |
| 用户手册 (中文) | `docs/zh_cn/user_guide.md` |
| 快速入门 (中文) | `docs/zh_cn/get_started.md` |
