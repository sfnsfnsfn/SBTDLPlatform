---
paths:
  - "**/*.py"
  - "**/*.pyi"
---

# Python 编码风格

> 适配自 ECC python/coding-style.md，针对 X-AnyLabeling 项目调整。

## 标准

- 遵循 **PEP 8** 规范
- 所有函数签名使用 **类型注解**
- 项目最低要求 Python 3.11

## 不可变性

优先使用不可变数据结构：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelConfig:
    name: str
    input_size: tuple[int, int]

from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float
```

## 格式化

- **black** 用于代码格式化（行长 79）
- **flake8** 用于 lint（最大复杂度 18）
- 导入顺序：标准库 → 第三方 → 本地模块

```bash
black anylabeling/ tests/ tools/
flake8 anylabeling/
```

## 命名规范

| 类型 | 规范 | 示例 |
|------|--------|--------|
| 变量/函数 | `snake_case` | `load_model()`, `image_path` |
| 类/异常 | `PascalCase` | `AlgorithmRegistry`, `ModelLoader` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_CONFIDENCE`, `MAX_BATCH_SIZE` |
| 布尔值 | `is_`/`has_`/`should_` 前缀 | `is_loaded`, `has_gpu` |
| 私有成员 | 前导下划线 | `_internal_cache` |
| 模块 | 小写 + 下划线 | `auto_labeling`, `model_manager` |

## 项目特定规范

- GUI 代码 (`views/`)：将业务逻辑与 PyQt6 组件分离
- 服务 (`services/`)：ONNX 推理会话应是可重入且线程安全的
- 平台 (`platform/`)：遵循 DDD 分层；适配器依赖领域接口
- 配置 (`configs/`)：使用 dataclass 作为配置对象，避免使用字典

## 避免的反模式

```python
# 错误：可变默认参数
def predict(inputs, cache={}):
    ...

# 正确：使用 None 并创建新对象
def predict(inputs, cache=None):
    if cache is None:
        cache = {}
    ...

# 错误：裸 except
try:
    model.infer(data)
except:
    pass

# 正确：具体异常
try:
    model.infer(data)
except ONNXInferenceError as e:
    logger.error(f"Inference failed: {e}")
    raise

# 错误：用 == 与 None 比较
if value == None:
    ...

# 正确：使用 is
if value is None:
    ...
```
