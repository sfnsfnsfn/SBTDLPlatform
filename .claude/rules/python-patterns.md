---
paths:
  - "**/*.py"
  - "**/*.pyi"
---

# Python 设计模式

> 适配自 ECC python/patterns.md。完整模式请参见技能：`python-patterns`。

## Protocol（鸭子类型）

使用 Protocol 为领域接口定义合约——适用于 `platform/adapters/`：

```python
from typing import Protocol

class AlgorithmProvider(Protocol):
    def load_model(self, path: str) -> object: ...
    def infer(self, input_data: object) -> object: ...
```

## Dataclass 作为值对象

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class InferenceResult:
    boxes: list[list[float]]
    scores: list[float]
    labels: list[str]
    latency_ms: float = 0.0

@dataclass
class ModelConfig:
    path: str
    confidence: float = 0.5
    device: str = "CPU"
```

## 上下文管理器 —— 资源

使用 `with` 进行 GPU 内存管理、文件 I/O、推理会话：

```python
# 正确：自动清理
with open(path, "r") as f:
    config = f.read()

# 正确：ONNX 会话管理
with ONNXSession(model_path) as session:
    result = session.run(inputs)

# 错误：手动资源管理
f = open(path, "r")
config = f.read()
f.close()
```

## 生成器 —— 内存效率

适用于大型图像数据集：

```python
def iter_images(paths: list[str]) -> Iterator[np.ndarray]:
    """逐个加载图像，避免一次性全部加载到内存。"""
    for path in paths:
        yield cv2.imread(path)

# 使用示例
for img in iter_images(large_dataset):
    result = model.infer(img)
```

## 异常层次结构

```python
class AppError(Exception):
    """应用级异常基类。"""

class ModelLoadError(AppError):
    """模型加载失败。"""

class InferenceError(AppError):
    """推理执行失败。"""

class ConfigError(AppError):
    """配置无效。"""
```

## 导入规范

```python
# 1. 标准库
import os
from pathlib import Path

# 2. 第三方
import numpy as np
import cv2

# 3. 项目内部
from anylabeling.services.auto_labeling.model import Model
from anylabeling.platform.domain import Project
```
