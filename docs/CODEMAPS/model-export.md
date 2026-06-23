<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~800 -->

# 模型导出 (Model Export)

## ExportService (`platform/application/export_service.py`, 817L)

| 方法 | 功能 |
|------|------|
| `start_export(run, export_config=None, labels=None, formats=None) → job_id` | 启动导出作业 |
| `get_exported_models() → list[ModelArtifact]` | 列出已导出模型 |
| `save_export_artifacts(export_path, model_path, model_id, labels, run_id) → ModelArtifact` | 保存产物 |
| `_resolve_best_pt(run) → str` | 从训练输出找到最佳权重 |
| `self_test_onnx(onnx_path, pt_model_path=None) → dict` | ONNX 自检 |

## 导出格式 (14 种)

| 格式 | 扩展名 | 必选包 |
|------|--------|--------|
| ONNX | `.onnx` | onnx, onnxslim, onnxruntime |
| TensorRT | `.engine` | tensorrt |
| TorchScript | `.torchscript` | (内置 PyTorch) |
| OpenVINO | `.xml` | openvino |
| CoreML | `.mlmodel` | coremltools |
| TensorFlow SavedModel | `/saved_model` | tensorflow |
| TFLite | `.tflite` | tensorflow |
| Edge TPU | `_edgetpu.tflite` | tensorflow |
| TF.js | `_tfjs` | tensorflow |
| PaddlePaddle | `_paddle` | paddlepaddle, x2paddle |
| MNN | `.mnn` | MNN |
| NCNN | `_ncnn` | ncnn |
| IMX500 | `.imx` | imx500-converter |
| RKNN | `.rknn` | rknn-toolkit2 |

## 导出流程

```
ExportWorkspace → export_requested 信号
  → ExportService.start_export(run, formats=["onnx","tensorrt"])
    → UltralyticsExportAdapter.build_export_kwargs() × N 格式
    → 逐格式 → JobService.create_job() → subprocess.Popen (YOLO CLI)
    → save_export_artifacts() → ModelArtifact
    → auto: ModelRegistryService.register()
    → ModelLibrary.refresh()

导出产物:
  models/<model_id>/
  ├── best.onnx           # ONNX 模型
  ├── best.pt             # PyTorch 权重
  ├── model.json          # 模型描述
  ├── labels.json         # 类别标签
  ├── preprocess.json     # 预处理参数
  ├── postprocess.json    # 后处理参数
  ├── onnx_check.json     # ONNX 自检结果
  └── _READY              # 完成标记
```

## ONNX 自检 (`ExportService.self_test_onnx()`)

- 环境验证: onnxruntime 导入, 文件扩展名, 路径安全 (必须在项目根内)
- 运行 `onnx.checker.check_model()` (尽力而为)
- 生成 `sample_count` 个确定性输入
- 推理并检查 NaN/Inf 和输出形状
- 若提供 `pt_model_path`: ONNX vs PyTorch 输出比较 (容忍度 1e-3)
- `torch.load` 使用 `weights_only=True`, 回退到 `weights_only=False`

## 导出适配器 (`platform/adapters/ultralytics/`)

| 文件 | 说明 |
|------|------|
| `export_adapter.py` | `ExportCapability` 接口: 格式列表, 构建 kwargs, 生成命令, 保存产物 |
| `export_validators.py` | 14 种格式环境验证器: `validate_export_environment(format) → list[str]` |

## ModelArtifact (`platform/domain/model.py`)

dataclass: id, run_id, format, path, labels, preprocess: dict, postprocess: dict, onnx_check: dict | None

## ModelRegistryService (`platform/application/model_registry_service.py`, 145L)

`register(artifact)`, `list_models()`, `unregister(model_id)`, `get_model(id)`。
持久化到 `{project_root}/models/registry.json`。

## ExportWorkspace (`views/platform/export_workspace.py`, 383L)

- 运行选择, 动态格式复选框 (通过 AlgorithmRegistry)
- 部署预览树, 导出选项 (size/FP16/batch/simplify/dynamic)
- 模型加密 (含密码), 自动注册复选框
- 导出后自动导航到 ModelLibrary (Models 步骤)

## ModelLibrary (`views/platform/widgets/model_library.py`, 305L)

- 网格 `_ModelCard` 控件: 缩略图, 格式徽章, 指标摘要, 大小
- 排序: date, mAP, size, format
- 对比模式: 并排模型比较
- 操作: deploy (复制到应用配置), delete, export info
- 新导出完成时自动刷新

## 历史遗留导出路径 (`services/auto_training/ultralytics/exporter.py`)

`ExportManager.start_export()` — 在**线程** (非子进程) 中运行导出:
- 查找 `weights/best.pt`
- 自动安装缺失包 (除非离线模式, 通过 OfflinePolicy)
- 重定向 stdout/stderr, 调用 `YOLO(weights.pt).export(format=export_format)`
- 通过回调/信号报告进度

## 实现状态

| 功能 | 状态 |
|------|------|
| ExportService | ✅ |
| 14 种导出格式 | ✅ |
| ExportWorkspace UI | ✅ |
| ModelRegistryService | ✅ |
| ModelLibrary (MODELS 步骤) | ✅ |
| 模型对比 | ✅ |
| ExportConfig 领域模型 | ✅ |
| 导出后自动注册 | ✅ |
| ONNX 自检 (含 PyTorch 对比) | ✅ |
| 格式环境验证 | ✅ |
| 模型加密后端 | ❌ 仅 UI 占位 |
| TensorRT 导出 | ⚠️ 仅 Windows |
| 导出后自动流转 → Models | ✅ |
