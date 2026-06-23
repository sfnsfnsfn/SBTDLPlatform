# Plan: 统一图像 IO 接口

**Source**: 用户需求 — 工程中**全部**图像读取都必须使用统一接口
**Complexity**: Large（~100 处调用点，5 层架构，~60 个模型文件）
**Date**: 2026-06-22 | **Last Updated**: 2026-06-23

## Progress

| Task | 状态 | 说明 |
|------|------|------|
| Task 1: ImageReader 核心类 (TDD) | ✅ 完成 | `image_reader.py` (290L) + 29 tests GREEN |
| Task 2: 消除重复 `_read_image_props()` | ✅ 完成 | asset_repository.py + import_service.py 已统一 |
| Task 3: platform/ 应用层 | ✅ 完成 | annotation_adapter.py 3处 cv2→ImageReader |
| Task 4: views/platform/ | ✅ 完成 | 8 文件 (task_configurator, preprocess_workspace 等) |
| Task 4b: views/labeling/ | ⏭ 跳过 | PIL.Image.open 保留（模型预处理管线） |
| Task 5: services/ | ✅ 完成 | 6 文件 (remote_server, rtmo, sahi 等) |
| Task 6: tools/ | ✅ 完成 | label_drawer.py, label_converter.py |
| Task 7: tests/ | ✅ 完成 | E2E fixtures, dataset_build_service test |
| Task 8: ONNX exporters | ⏭ 跳过 | tools/onnx_exporter/ 为开发工具，低优先级 |
| 额外: pyproject.toml | ✅ 完成 | numpy>=1.24 提升到核心依赖 |
| 额外: codemaps | ✅ 完成 | 14 文件更新 (2026-06-22) |

**进度**: 8/10 tasks 完成 ✅  |  **30 文件变更**, 806 insertions, 580 deletions

## 硬性规则（实施后生效）

> **项目中禁止直接调用 `cv2.imread()`、`skimage.io.imread()` 读取图像文件。**
> 所有从磁盘读取图像像素/元数据必须通过 `ImageReader` 接口。
>
> 例外：`PIL.Image.open()` 在模型预处理管线中可保留（返回 PIL Image 对象给 torchvision transforms），
> 但应优先考虑 `ImageReader.read()` 返回 numpy 再传给模型。

## Summary

创建 `anylabeling/platform/infrastructure/image_reader.py` → `ImageReader` 类，
作为工程中**唯一的**图像文件读取入口。消除 5 种分散读取方式，
统一处理 TIFF/BGR/RGB/多页/超大/多 bit depth。

## 现状完整清单

### cv2.imread() — 53 处（全部需要迁移）

| 层级 | 文件 | 行号 | 用途 |
|------|------|------|------|
| **infra** | `platform/infrastructure/image_sources/file_source.py` | 23 | FileImageSource 全量读 |
| **app** | `platform/application/annotation_adapter.py` | 171,196,239 | 标注 → 像素渲染 |
| **views** | `views/platform/task_configurator.py` | 658,687 | 标签图预览 |
| **views** | `views/platform/preprocess_workspace.py` | 583,673,685 | 瓦片预览 |
| **views** | `views/platform/label_workspace.py` | 972 | 资产生命周期 |
| **views** | `views/platform/widgets/inference_viewer.py` | 103 | 推理预览 |
| **views** | `views/platform/workbench_window.py` | 1744 | 残留 cv2 调用 |
| **services** | `services/auto_labeling/remote_server.py` | 545 | 远程服务器输入 |
| **services** | `services/auto_labeling/pose/rtmo_onnx.py` | 143 | RTMO 姿态模型 |
| **services** | `services/auto_labeling/__base__/rtmdet.py` | 143 | RTMDet 基类 |
| **services** | `services/auto_labeling/__base__/clip.py` | 529 | CLIP 基类 |
| **services** | `services/auto_labeling/utils/sahi/utils/cv.py` | 118,132,154 | SAHI 读取工具 |
| **services** | `services/auto_labeling/visualgd/util/inference.py` | 171,213 | VisualGD 推理 |
| **tools** | `tools/label_drawer.py` | 67,79,151,289,430 | 标签绘制 (5处) |
| **tools** | `tools/label_converter.py` | 729 | 标签转换 |
| **tools** | `tools/onnx_exporter/*.py` | 10个文件 | ONNX 导出验证 |
| **tests** | `tests/e2e/platform/test_fixtures.py` | 65,483,540,561-563,580,602 | E2E 夹具 |
| **tests** | `tests/platform/application/test_dataset_build_service.py` | 509 | 构建验证 |

### PIL.Image.open() — 43 处（元数据类需迁移，模型预处理类可保留）

| 层级 | 文件 | 处理方式 |
|------|------|----------|
| **infra** | `tiff_image_source.py`, `memory_image_source.py` | → ImageReader |
| **app** | `import_service.py::_read_image_props()` | → `ImageReader.metadata()` |
| **app** | `asset_repository.py::_read_image_props()` | → `ImageReader.metadata()` |
| **views** | `label_widget.py`, `canvas.py`, `image_provider.py` 等 QImageReader 场景 | 保留 QImageReader（Qt 渲染管线专用） |
| **views** | `labeling/utils/image.py` (工具函数) | → ImageReader |
| **views** | `labeling/utils/visualization.py:701` | → ImageReader |
| **views** | `labeling/utils/batch.py:141` | → ImageReader |
| **views** | `labeling/label_converter.py:346` | → ImageReader |
| **views** | `labeling/widgets/chatbot_dialog.py:1986` | → ImageReader |
| **views** | `labeling/widgets/ppocr_dialog.py:1533,1671` | → ImageReader |
| **views** | `labeling/ppocr/*.py` (3处) | → ImageReader |
| **services** | `florence2.py`, `deimv2.py`, `dfine.py`, `rmbg.py`, `rfdetr.py`, `yoloe.py` 等 ~15 模型 | 保留 PIL（模型预处理需要 PIL Image） |
| **tools** | `label_converter.py:56` | → ImageReader |
| **tools** | `onnx_exporter/` (4处) | → ImageReader |

### skimage.io.imread() — 4 处（全部替换）

| 文件 | 行号 |
|------|------|
| `services/auto_labeling/utils/sahi/utils/cv.py` | 142,191 |
| `services/auto_labeling/utils/sahi/utils/cv.py` | 177 (read with PIL) |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      ImageReader                             │
│  "工程唯一图像文件读取入口"                                      │
│                                                               │
│  ── 像素读取 ──                                                │
│  read(path, *, output_color="RGB", page=0) → np.ndarray       │
│  read_region(path, rect_l0, output_size) → np.ndarray         │
│  read_pages(path) → list[np.ndarray]    # 多页 TIFF 全部页     │
│                                                               │
│  ── 元数据读取（无像素解码）───────────────────────────────────│
│  metadata(path) → ImageMetadata                               │
│  pages(path) → int                                            │
│                                                               │
│  ── 控制参数 ──                                                │
│  output_color: "RGB" | "BGR" | "AS_IS"  默认 RGB              │
│  page: int = 0                           多页图像页索引        │
│  backend: "auto" | "pil" | "qt" | "cv2" 默认 auto             │
└────────────────────┬─────────────────────────────────────────┘
                     │ auto 路由
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌──────────┐
    │ PIL      │ │ Qt      │ │ OpenCV   │
    │ (默认)   │ │ (超大)  │ │ (fallback)│
    └─────────┘ └─────────┘ └──────────┘
```

### 后端自动选择逻辑

```
metadata() → 优先 Qt (QImageReader, 零像素解码), fallback PIL → cv2
read()     → 优先 PIL (RGB原生, 无转换开销), fallback Qt → cv2
read_region() → Qt (支持 ROI 无需全量解码), fallback PIL crop
read_pages() → 仅 PIL (唯一支持多页 TIFF 的后端)
```

## 完整文件变更清单

### Task 1: 创建 ImageReader 核心类

| File | Action |
|------|--------|
| `anylabeling/platform/infrastructure/image_reader.py` | **CREATE** (~250L) |
| `tests/platform/infrastructure/test_image_reader.py` | **CREATE** (~300L) |

### Task 2: 消除重复代码 + 平台基础设施层

| File | Action | 变更点 |
|------|--------|--------|
| `platform/application/asset_repository.py` | UPDATE | 删除 `_read_image_props()`，改用 `ImageReader.metadata()` |
| `platform/application/import_service.py` | UPDATE | 删除 `_read_image_props()`，改用 `ImageReader.metadata()` |
| `platform/infrastructure/image_sources/file_source.py` | UPDATE | `cv2.imread` → `ImageReader.read()` |

### Task 3: 平台应用层

| File | Action | 变更点 |
|------|--------|--------|
| `platform/application/annotation_adapter.py` | UPDATE | 3处 `cv2.imread` → `ImageReader.read()` |

### Task 4: 视图层（views/platform/）

| File | Action | 变更点 |
|------|--------|--------|
| `views/platform/task_configurator.py` | UPDATE | 2处 `cv2.imread` → `ImageReader.read()` |
| `views/platform/preprocess_workspace.py` | UPDATE | 3处 `cv2.imread` → `ImageReader.read()` |
| `views/platform/label_workspace.py` | UPDATE | 1处 `cv2.imread` → `ImageReader.read()` |
| `views/platform/widgets/inference_viewer.py` | UPDATE | 1处 `cv2.imread` → `ImageReader.read()` |
| `views/platform/workbench_window.py` | UPDATE | 1处残留 `cv2.imread` → `ImageReader.read()` |

### Task 4b: 视图层（views/labeling/）

| File | Action | 变更点 |
|------|--------|--------|
| `views/labeling/utils/image.py` | UPDATE | `PIL.Image.open()` → `ImageReader` |
| `views/labeling/utils/visualization.py` | UPDATE | `Image.open(image_file)` → `ImageReader.read()` |
| `views/labeling/utils/batch.py` | UPDATE | `Image.open(image_path)` → `ImageReader.read()` |
| `views/labeling/label_converter.py` | UPDATE | `Image.open(image_file)` → `ImageReader.read()` |
| `views/labeling/widgets/chatbot_dialog.py` | UPDATE | `Image.open(local_image_path)` → `ImageReader.read()` |
| `views/labeling/widgets/ppocr_dialog.py` | UPDATE | 2处 `Image.open()` → `ImageReader.read()` |
| `views/labeling/ppocr/data_manager.py` | UPDATE | `Image.open(image_path)` → `ImageReader.read()` |
| `views/labeling/ppocr/pipeline.py` | UPDATE | 2处 `Image.open()` → `ImageReader.read()` |

### Task 5: 服务层

| File | Action | 变更点 |
|------|--------|--------|
| `services/auto_labeling/remote_server.py` | UPDATE | `cv2.imread` → `ImageReader.read()` |
| `services/auto_labeling/pose/rtmo_onnx.py` | UPDATE | `cv2.imread` → `ImageReader.read()` |
| `services/auto_labeling/__base__/rtmdet.py` | UPDATE | `cv2.imread` → `ImageReader.read()` |
| `services/auto_labeling/__base__/clip.py` | UPDATE | `cv2.imread` → `ImageReader.read()` |
| `services/auto_labeling/utils/sahi/utils/cv.py` | UPDATE | `cv2.imread` + `skimage.io.imread` → `ImageReader.read()` |
| `services/auto_labeling/visualgd/util/inference.py` | UPDATE | 2处 `cv2.imread` → `ImageReader.read()` |

### Task 6: 工具层

| File | Action | 变更点 |
|------|--------|--------|
| `tools/label_drawer.py` | UPDATE | 5处 `cv2.imread` → `ImageReader.read()` |
| `tools/label_converter.py` | UPDATE | 2处 `cv2.imread` + `Image.open` → `ImageReader` |

### Task 7: 测试层

| File | Action | 变更点 |
|------|--------|--------|
| `tests/e2e/platform/test_fixtures.py` | UPDATE | 8处 `cv2.imread` → `ImageReader.read()` |
| `tests/platform/application/test_dataset_build_service.py` | UPDATE | 1处 `cv2.imread` → `ImageReader.read()` |

### Task 8: ONNX 导出工具（低优先级）

| File | Action |
|------|--------|
| `tools/onnx_exporter/export_yolow_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_yolov8_obb_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_yolov10_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_u_rtdetr_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_rfdetr_seg_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_rfdetr_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_recognize_anything_model_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_pulc_attribute_model_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_internimage_model_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_deimv2_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_grounding_dino_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_geco_onnx.py` | UPDATE |
| `tools/onnx_exporter/export_dfine_onnx.py` | UPDATE |

## 保留不动的场景

| 场景 | 文件 | 原因 |
|------|------|------|
| Qt 渲染管线 | `canvas.py`, `label_widget.py`, `image_provider.py`, `qt_image_source.py` | QImageReader/QImage 是 Qt 原生渲染所需，不能绕开 |
| 模型 PIL 预处理 | `florence2.py`, `deimv2.py`, `dfine.py`, `rfdetr.py`, `yoloe.py`, `rmbg.py` 等 | torchvision transforms 需要 PIL Image 对象 |
| 非文件读取 | `QImage(data)`, `Image.open(io.BytesIO(...))` | 不是从磁盘路径读取 |
| PIL 写回 | `Image.save()`, `cv2.imwrite()` | ImageReader 只负责**读**，写入保持不变 |

## ImageReader API 设计

```python
class ImageReader:
    """Unified image file reader — the single entry point for all image I/O."""

    @staticmethod
    def read(
        path: str | Path,
        *,
        output_color: str = "RGB",       # "RGB" | "BGR" | "AS_IS"
        page: int = 0,                    # 多页图像页索引
    ) -> np.ndarray:
        """Read the full image into a numpy array (H, W, C)."""

    @staticmethod
    def read_region(
        path: str | Path,
        rect_l0: tuple[int,int,int,int],      # (x0, y0, w, h)
        output_size: tuple[int,int],           # (w, h)
    ) -> np.ndarray:
        """Read a rectangular ROI without decoding the full image."""

    @staticmethod
    def read_pages(path: str | Path) -> list[np.ndarray]:
        """Read all pages of a multi-page image (TIFF stack)."""

    @staticmethod
    def metadata(path: str | Path) -> ImageMetadata:
        """Return image metadata WITHOUT pixel decoding."""

    @staticmethod
    def pages(path: str | Path) -> int:
        """Return the number of pages in a multi-page image."""
```

## Backward Compatibility 速查表

| 旧代码 | 新代码 |
|--------|--------|
| `cv2.imread(p)` | `ImageReader.read(p, output_color="BGR")` |
| `cv2.imread(p, cv2.IMREAD_UNCHANGED)` | `ImageReader.read(p, output_color="AS_IS")` |
| `cv2.imread(p, cv2.IMREAD_COLOR)` | `ImageReader.read(p, output_color="BGR")` |
| `PIL.Image.open(p)` for dims | `ImageReader.metadata(p)` |
| `QImageReader(p).size()` for dims | `ImageReader.metadata(p)` |
| `skimage.io.imread(p)` | `ImageReader.read(p)` (both default RGB) |

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| BGR/RGB 转换破坏推理 | High | 默认 RGB；逐一审查每个模型的色彩空间期望 |
| PIL 不支持某些 TIFF 变体 | Medium | 多后端 fallback (PIL → Qt → cv2) |
| 超大图像 OOM | Medium | `read_region()` 强制 ROI 模式 |
| 性能退化 | Low | metadata 走 Qt 最快路径；read 以 PIL 为主 |
| 遗漏调用点 | Low | Grep 全量扫描已验证所有调用点 |

## Validation

```bash
# 核心测试
pytest tests/platform/infrastructure/test_image_reader.py -v

# 平台层回归
pytest tests/platform/application/ -v --timeout=120

# E2E 回归
pytest tests/e2e/ -v --timeout=120

# 全量回归
pytest -x --timeout=120 --ignore=tests/test_models
```

## Acceptance

- [ ] `ImageReader` 类创建完毕并通过全部单元测试
- [ ] 53 处 `cv2.imread()` 全部替换为 `ImageReader.read()`
- [ ] 4 处 `skimage.io.imread()` 全部替换为 `ImageReader.read()`
- [ ] 2 份重复 `_read_image_props()` 已消除
- [ ] 多页 TIFF 读取测试通过
- [ ] 8-bit / 16-bit / float32 测试通过
- [ ] RGB / BGR 输出切换测试通过
- [ ] 全量测试套件通过
- [ ] 启动时无 `cv::findDecoder imread_` 警告
- [ ] `views/labeling/utils/image.py` 底层工具函数统一走 ImageReader
