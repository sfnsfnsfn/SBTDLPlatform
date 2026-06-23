<!-- Generated: 2026-06-23 | Files scanned: 504 | Token estimate: ~850 -->

# 标注 (Annotation)

## 数据模型 (`platform/domain/annotation.py`)

| 类型 | 字段 |
|------|------|
| `AnnotationObject` (dataclass) | id, label_id, geometry_type (bbox_xyxy\|polygon\|keypoints\|...), geometry, attributes, source_object_id |
| `AnnotationDocument` (dataclass) | asset_id, image_width, image_height, objects: list[AnnotationObject], image_labels: dict[str,bool] |

## 标注编解码器

`AnnotationCodec(Protocol)` (`platform/application/ports.py`):
- `load_annotations(file_path, image_width, image_height) → AnnotationDocument`
- `save_annotations(doc, file_path) → None`
- `validate_annotations(doc) → list[str]`

### 实现

| 编解码器 | 文件 | 格式 | 方向 | 几何类型 |
|----------|------|------|------|----------|
| `XLabelCodec` | `application/annotation_service.py` | X-AnyLabeling JSON | 双向 | 全部几何类型 |
| `COCOCodec` | `application/codecs/coco_codec.py` | COCO JSON | 双向 | bbox_xyxy |
| `VOCCodec` | `application/codecs/voc_codec.py` | Pascal VOC XML | 双向 | bbox_xyxy |
| `YOLOCodec` | `application/codecs/yolo_codec.py` | YOLO .txt | 双向 | bbox_xyxy, obb, pose, seg |

## AnnotationAdapter (`platform/application/annotation_adapter.py`, 333L)

Shape ↔ AnnotationDocument 功能桥接:

| 函数 | 功能 |
|------|------|
| `shapes_to_annotation_doc(shapes, asset_id, w, h, label_name_to_id)` | Shape 列表 → AnnotationDocument |
| `annotation_doc_to_shapes(doc)` | AnnotationDocument → Shape dict 列表 |
| `load_annotations_for_asset(asset_path, project_path)` | 从项目加载标注 |
| `save_annotations_for_asset(...)` | 原子保存: tmp → 验证 → replace |
| 崩溃恢复 | 检测 `.json.tmp` 文件 |

## 画布 (`views/labeling/widgets/canvas.py`)

`Canvas(QWidget)` — QPainter 绘制:
- 形状创建: rect, polygon, OBB, keypoints, line, point, circle, cuboid, quadrilateral, brush
- 模式: `CREATE` (0) 和 `EDIT` (1)
- 缩放/平移: Camera2D + CoordinateMap
- 撤销/重做: shape 备份
- 信号: `zoom_request`, `camera_view_changed`, `new_shape`, `selection_changed`, `shape_moved`, `auto_labeling_marks_updated`, `auto_decode_requested`, `edit_label_requested` 等

## LabelingWidget (`views/labeling/label_widget.py`)

中心控制器 (~2000+ 行):
- 文件: next/prev 图像导航
- 保存/加载: LabelFile JSON
- 形状 CRUD: 创建/编辑/删除/复制/粘贴
- 撤销/重做: shape 备份机制
- 标签管理: 列表/过滤/快捷键
- 自动标注: 连接 AutoLabelingWidget
- 对话框编排: 30+ 对话框
- 画笔/遮罩: brush 编辑支持
- 对比视图: 分屏比较模式

## 形状类型 (Shape, `labeling/shape.py`)

| 形状类型 | 说明 | 状态 |
|----------|------|------|
| `rectangle` | 轴对齐矩形 | ✅ |
| `rotation` | 旋转矩形 (带角度) | ✅ |
| `polygon` | 多边形 | ✅ |
| `line` | 线段 | ✅ |
| `point` | 点标注 | ✅ |
| `circle` | 圆形 | ✅ |
| `cuboid` | 长方体 | ✅ |
| `quadrilateral` | 四边形 | ✅ |
| `linestrip` | 折线 | ✅ |
| `brush` | 画笔/遮罩 | ✅ |

## AI 标注结果流

```
Canvas.auto_labeling_marks_updated (点/框提示)
  → AutoLabelingWidget.on_new_marks
  → ModelManager.predict_shapes_threading()
    → GenericWorker(QThread) → Model.predict_shapes() → AutoLabelingResult
      → ModelManager.new_auto_labeling_result.emit(result)
        → LabelingWidget.new_shapes_from_auto_labeling(result)
          → 清除/替换形状, set_dirty(), update UI
```

## 持久化 (`views/labeling/label_file.py`)

`LabelFile` — X-AnyLabeling JSON 格式:
- `LabelFileError` 用于损坏/无效文件
- 通过 `LabelConverter` 向后兼容转换
- Base64 图像数据编码/解码

## 标注服务 (`platform/application/annotation_service.py`, 521L)

- `load_annotations(asset_path) → AnnotationDocument`
- `save_annotations(doc, asset_path) → None`
- `validate_annotations(doc) → list[str]`
- `export_annotations(doc, format: str) → str` — 转换到 COCO/VOC/YOLO

## 设置系统集成

标注设置通过 `SettingsController` + `SettingsDialog` 管理:
- 防抖保存到 `~/.xanylabelingrc`
- `SettingsRuntimeApplier` 在运行时应用更改
- 设置页: 通用, 画布, 自动标注, 标注, 快捷键

## 实现状态

| 功能 | 状态 |
|------|------|
| 手动形状工具 (10 种) | ✅ |
| 撤销/重做 | ✅ |
| 缩放/平移 (Camera2D) | ✅ |
| 标签管理 (CRUD, 颜色, 快捷键, 过滤) | ✅ |
| AI 辅助标注 | ✅ |
| 自动保存 | ✅ |
| 遮罩画笔 | ✅ |
| AnnotationCodec 协议 + 4 种编解码器 | ✅ |
| 多格式标注导入 (COCO/VOC/YOLO) | ✅ |
| 多格式标注导出 | ✅ |
| BatchLabelingService | ⚠️ 部分 (缺少推理管线连接) |
| LabelConverter | 🗑️ 遗留 (用 XLabelCodec 替代) |
