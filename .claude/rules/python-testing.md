---
paths:
  - "**/test_*.py"
  - "**/tests/**/*.py"
---

# Python 测试规范

> 适配自 ECC python/testing.md。项目使用 pytest，配置位于 `pyproject.toml` 的 `[tool.pytest.ini_options]`。

## 框架

使用 **pytest** 作为测试框架。

## 测试结构（AAA 模式）

```python
def test_inference_with_empty_input():
    # Arrange
    model = load_test_model()
    empty_input = np.array([])

    # Act & Assert
    with pytest.raises(ValueError, match="empty input"):
        model.infer(empty_input)
```

## 测试命名

使用描述性名称，解释被测行为：

```python
def test_algorithm_registry_returns_none_for_unknown_key(): ...
def test_tile_planner_splits_large_image_into_correct_grid(): ...
def test_export_adapter_raises_on_missing_model_file(): ...
```

## 项目标记

```bash
# 排除慢速测试
pytest -m "not slow"

# 仅运行单元测试
pytest tests/platform/ tests/test_utils/

# 运行并显示持续时间（慢速排序）
pytest --durations=30
```

## 覆盖率

```bash
pytest --cov=anylabeling --cov-report=term-missing
```

## 临时文件使用 tmp_path

```python
def test_export_writes_valid_format(tmp_path):
    output = tmp_path / "export.onnx"
    service.export(model, output)
    assert output.exists()
    assert output.stat().st_size > 0
```

## 模拟外部依赖

```python
from unittest.mock import patch

@patch("anylabeling.services.auto_labeling.engines.build_onnx_engine.onnxruntime.InferenceSession")
def test_onnx_engine_creation(mock_session):
    mock_session.return_value.run.return_value = [np.array([[0, 0, 10, 10]])]
    engine = ONNXEngine("model.onnx")
    result = engine.run(input_data)
    assert result is not None
```

## 测试组织

测试镜像 `anylabeling/` 源树结构：

```
tests/
├── platform/
│   ├── domain/          # 领域模型合约
│   ├── application/     # 服务测试
│   ├── infrastructure/  # 文件存储、图像源
│   ├── adapters/        # 提供商适配器
│   └── views/           # 平台工作区
├── views/
│   ├── labeling/        # 标注画布、视口
│   └── platform/        # GUI 工作区
├── e2e/                  # 端到端
├── test_models/          # 模型检查、ONNX 验证
└── test_utils/           # 工具函数
```

## 最佳实践

### 应做
- **每个测试验证一个行为**
- **使用夹具消除重复**
- **mock 外部依赖**（无需真实 ONNX 模型）
- **测试边界情况**：空输入、None 值、超大图像
- **保持测试快速**：使用标记分离慢速测试

### 不应做
- **不要测试实现细节**：验证行为而非内部状态
- **不要在测试中使用复杂条件**
- **不要忽略测试失败**：所有测试必须通过
- **不要测试第三方代码**：信任 onnxruntime、numpy、cv2
- **不要在测试间共享可变状态**
