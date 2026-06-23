---
paths:
  - "**/*.py"
  - "**/*.pyi"
---

# 编码原则

> 适配自 ECC common/coding-style.md，适用于 Python / X-AnyLabeling 项目。

## 不可变性（关键）

始终创建新对象，永远不要修改现有对象：

```
错误:  modify(original, field, value) → 就地修改 original
正确: update(original, field, value) → 返回带有更改的新副本
```

理由：不可变数据防止隐藏的副作用，使调试更容易，并启用安全的并发。

## 核心准则

### KISS（保持简单）

- 优先选择有效的最简解决方案
- 避免过早优化
- 追求清晰而非巧妙

### DRY（不要重复自己）

- 将重复逻辑提取到共享函数或工具中
- 避免复制粘贴导致的实现偏差
- 在重复真正出现时引入抽象，而非推测性抽象

### YAGNI（你不会需要它）

- 不要在需要之前构建功能或抽象
- 避免推测性泛化
- 从简单开始，在压力真正到来时重构

## 文件组织

多个小文件 > 少量大文件：
- 高内聚，低耦合
- 典型 200–400 行，最多 800 行
- 从大型模块中提取工具函数
- 按功能/领域组织，而非按类型

## 错误处理

始终全面处理错误：
- 在每一层显式处理错误
- 在 GUI 代码中提供用户友好的错误消息（`views/`）
- 在服务层记录详细上下文（`services/`）
- 永远不要静默吞掉错误

```python
# 错误：静默失败
try:
    result = model.infer(data)
except Exception:
    result = None  # 用户不知道为什么失败

# 正确：显式并记录
try:
    result = model.infer(data)
except ONNXInferenceError as e:
    logger.error(f"Inference failed for model {model.name}: {e}")
    raise InferenceFailedError(f"推理失败: {e}") from e
```

## 输入验证

始终在系统边界进行验证：
- 在推理前验证所有模型输入维度
- 在读取配置前验证 `pyproject.toml` 或 YAML
- 快速失败并给出清晰的错误消息
- 永远不要信任外部数据（用户上传的文件、ONNX 模型输入）

```python
def validate_input(image: np.ndarray, expected_shape: tuple) -> None:
    if image.ndim not in (2, 3):
        raise ValueError(f"Expected 2D or 3D image, got {image.ndim}D")
    if image.shape[:2] != expected_shape[:2]:
        raise ValueError(
            f"Image shape {image.shape[:2]} != expected {expected_shape[:2]}"
        )
```

## 避免的代码异味

### 深层嵌套
一旦逻辑开始叠加，优先使用提前返回而非嵌套条件。

### 魔法数字
对阈值、延迟和限制使用命名常量：

```python
# 错误
if score > 0.45:
    ...

# 正确
CONFIDENCE_THRESHOLD = 0.45
if score > CONFIDENCE_THRESHOLD:
    ...
```

### 长函数
将大型函数拆分为具有清晰职责的有重点的小函数。

## 代码质量检查清单

标记工作完成前：
- [ ] 代码可读且命名良好
- [ ] 函数很小（<50 行）
- [ ] 文件聚焦（<800 行）
- [ ] 没有深层嵌套（>4 级）
- [ ] 正确的错误处理（无裸 except）
- [ ] 没有硬编码值（使用常量或配置）
- [ ] 没有就地变更（使用不可变模式）
- [ ] 类型注解已存在
- [ ] 未引入新的第三方依赖（未经评审）
