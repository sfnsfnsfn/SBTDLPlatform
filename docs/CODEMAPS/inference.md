<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~900 -->

# 推理 — 自动标注引擎 (Inference)

## ModelManager (`services/auto_labeling/model_manager.py`)

中央模型注册管理器，使用 `GenericWorker + QThread` (无线程池)。

### 信号 (11 个 pyqtSignal)

`new_auto_labeling_result`, `prediction_started/finished`, `model_loaded`, `new_model_status`, `model_configs_changed`, `auto_segmentation_model_selected/unselected`, `request_next_files_requested`, `download_progress`, `download_finished`

### 模型加载 (`load_model()`, line 293)

创建 QThread → GenericWorker → if-elif 链 (87 分支) 按 `model_config["type"]` 分发:
```python
if model_config["type"] == "yolov5":
    from .yolov5 import YOLOv5
    model_config["model"] = YOLOv5(model_config, on_message=...)
elif model_config["type"] == "segment_anything":
    from .segment_anything import SegmentAnything
    # ... 87 个分支
```

### 推理执行 (`predict_shapes_threading()`, line 2297)

获取线程锁 → QThread → `Model.predict_shapes()` → ONNX 推理 → `AutoLabelingResult` → 信号发射

## Model 基类 (`services/auto_labeling/model.py`)

```python
class Model(QObject):
    class Meta:
        required_config_names = []    # 必需 YAML 键
        widgets = ["button_run"]      # UI 控件
        output_modes = {"rectangle": "Rectangle"}
        default_output_mode = "rectangle"

    def predict_shapes(self, image, filename=None) → AutoLabelingResult: ...
    def unload(self): ...
    def get_model_abs_path(self, model_config, model_path_field_name): ...  # 下载/缓存/验证
```

## 推理引擎 (`services/auto_labeling/engines/`)

| 引擎 | 类 | 后端 |
|------|-----|------|
| ONNX | `OnnxBaseModel` | `onnxruntime.InferenceSession` (CPU/CUDA) |
| TensorRT | `TrtBaseModel` | `tensorrt` + `cuda-python` |
| DNN | `DnnBaseModel` | `cv2.dnn.readNet()` |

## 87+ 种模型类型

### YOLO 系列
| 类型 | 任务 |
|------|------|
| `yolov5` ~ `yolo12`, `yolo26` | 目标检测 |
| `yolov5_seg`, `yolov8_seg`, `yolo11_seg`, `yolo26_seg` | 实例分割 |
| `yolov5_obb`, `yolov8_obb`, `yolo11_obb`, `yolo26_obb` | 定向边界框 |
| `yolov8_pose`, `yolo11_pose`, `yolo26_pose` | 姿态估计 |
| `yolov5_cls`, `yolov8_cls`, `yolo11_cls` | 图像分类 |
| `yolov5_sahi` ~ `yolo26_sahi` | SAHI 切片推理 |
| `yolov5_det_track` ~ `yolo26_det_track` | 检测+跟踪 |

### SAM 系列
| 类型 | 说明 |
|------|------|
| `segment_anything` | SAM v1 (点/框提示) |
| `segment_anything_2` | SAM v2 (高分辨率特征) |
| `segment_anything_3` | SAM v3 (语言引导) |
| `segment_anything_2_video` | SAM2 视频跟踪 |
| `sam_hq`, `sam_med2d`, `edge_sam`, `efficientvit_sam` | SAM 变体 |

### Transformer/DETR 系列
| 类型 | 说明 |
|------|------|
| `rtdetr`, `rtdetrv2`, `u_rtdetr` | RT-DETR 系列 |
| `deimv2`, `dfine` | DEIM / D-FINE |
| `rfdetr`, `rfdetr_seg` | RF-DETR |
| `grounding_dino`, `grounding_dino_api` | 开集检测 |

### 其他模型
| 类型 | 任务 |
|------|------|
| `ppocr_v4`, `ppocr_v5` | PaddleOCR |
| `florence2` | Florence-2 VLM |
| `ram`, `yolov5_ram`, `yolow_ram` | 识别万物 |
| `depth_anything`, `depth_anything_v2` | 单目深度估计 |
| `rmbg` | 背景移除 |
| `doclayout_yolo` | 文档布局分析 |
| `pulc_attribute`, `internimage_cls` | 属性/分类 |
| `clrnet` | 车道线检测 |
| `yolox_dwpose`, `rtmdet_pose` | 姿态 |
| `open_vision`, `geco`, `upn` | 组合模型 |
| `remote_server` | 远程 API 代理 |

### 组合模型 (tracker-integrated)
`yolov5_sam`, `yolov8_sam2`, `grounding_sam`, `grounding_sam2`

### SAHI 切片推理 (`utils/sahi/`)
捆绑 SAHI v0.11.14 库: 大图 → 切片 → 逐片推理 → NMS/NMM 合并

## 功能分类列表 (`__init__.py`)

| 列表 | 模型数 | 说明 |
|------|--------|------|
| `_AUTO_LABELING_MARKS_MODELS` | 15 | SAM 系列 (交互式提示) |
| `_AUTO_LABELING_CONF_MODELS` | ~55 | 置信度阈值滑块 |
| `_AUTO_LABELING_IOU_MODELS` | ~35 | IoU 阈值滑块 |
| `_ON_NEXT_FILES_CHANGED_MODELS` | 13 | 预取编码加速 |
| `_CACHED_AUTO_LABELING_MODELS` | 2 | 缓存标签输出 |
| `_BATCH_PROCESSING_INVALID_MODELS` | 8 | 批量处理排除 |

## 模型下载/缓存

`Model.get_model_abs_path()`:
1. 路径解析: 本地路径或 URL
2. URL 下载: 缓存到 `{work_dir}/xanylabeling_data/models/{model_name}/{filename}`
3. ONNX 验证: 子进程 `safe_check_model()` (onnx.checker)
4. 损坏检测: 自动重新下载
5. 镜像支持: ModelScope (zh_CN) / GitHub Releases
6. 重试: 最多 2 次, 3 秒间隔, 支持取消

## 配置模型注册

`configs/models.yaml` — ~365 条目索引:
```yaml
- model_name: "yolov5s-r20230520"
  config_file: ":/yolov5s.yaml"
- model_name: "sam2_hiera_large-r20240801"
  config_file: ":/sam2_hiera_large.yaml"
```
每个 YAML 文件定义: `type`, `name`, `display_name`, `model_path`, 阈值, 类别列表。

## InferenceService (`platform/application/inference_service.py`, 156L)

独立于 ModelManager — CLI 驱动:
- `infer_image(run, image_path) → job_id`
- `infer_batch(run, image_dir) → job_id`
- 通过 `AlgorithmProvider.inference_adapter` 生成子进程命令

## 实现状态

| 功能 | 状态 |
|------|------|
| ModelManager + 87 种模型 | ✅ |
| ONNX / TensorRT / DNN 引擎 | ✅ |
| 异步加载 & 推理 (QThread) | ✅ |
| 信号驱动结果传递 | ✅ |
| 并发门控 (锁) | ✅ |
| InferenceService (CLI) | ✅ |
| InferenceViewerWidget | ✅ |
| InferWorkspace UI | ⚠️ 已实现但未接入 (死代码) |
| 批量处理 (BatchLabelingService) | ⚠️ 部分 |
| 线程池 | ❌ 每次调用的临时 QThread |
