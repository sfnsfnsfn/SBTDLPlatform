<!-- Generated: 2026-06-25 | Files scanned: 523 | Token estimate: ~800 | Updated: dead code cleanup -->

# 大图 — 切分与视口 (Large Image)

## 两个独立子系统

| 子系统 | 位置 | 用途 | 状态 |
|--------|------|------|------|
| **平台切分** | `platform/tiling/` | 离线数据集创建 | ✅ 已接入 |
| **视口渲染** | `views/labeling/viewport/` | 在线绘制 | ✅ 已接入 (QPainter 路径) |

## 子系统 1: 平台切分 (离线)

### 切分架构

```
TilePlanner.plan(asset, tile_plan)
  → 计算 grid: stride = tile_size - overlap
  → 行优先遍历 (top-left → bottom-right)
  → 生成 TileRecord (tile_id, x0, y0, width, height, valid_width, valid_height, split)
  → 两种边缘模式:
    "crop" — 边缘切片截断到剩余区域
    "pad" — 边缘切片保持完整大小, valid_width/height 指示真实像素区域

TileMaterializer(output_dir)
  → source.read_region(rect_l0, output_size) → numpy 数组
  → RGB→BGR 转换 → cv2.imwrite() → PNG
  ⚠️ pad 填充逻辑未实现
```

### TilePlan (`platform/domain/tile.py`)

```python
@dataclass(frozen=True)
class TilePlan:
    tile_width: int
    tile_height: int
    overlap_x: int           # 像素 (非百分比)
    overlap_y: int
    edge_mode: Literal["crop", "pad"]
    padding_value: int | tuple[int, ...]
    min_object_pixels: int
    min_visibility_ratio: float
```

### 标签分割器 (`platform/tiling/label_splitters/`)

5 个分割器，统一接口: `task_family` 属性 + `split(annotations, tile, plan)`。

坐标转换: L0 (全图) → 切片局部 = 减去 `(tile.x0, tile.y0)`

| 分割器 | 文件 | 几何方法 | 过滤条件 |
|--------|------|----------|----------|
| `HBBSplitter` | `hbb.py` | bbox ∩ tile 裁剪 | visibility_ratio ≥ 阈值, inter_area ≥ min_pixels |
| `OBBSplitter` | `obb.py` | Shapely polygon 交集 → minimum_rotated_rectangle | 退化标记 |
| `PolygonSplitter` | `polygon.py` | Shapely 交集 → MultiPolygon 碎片 | 碎片各自独立标注对象 |
| `PoseSplitter` | `pose.py` | 关键点可见性掩码 | min_visible_keypoints (默认 1) |
| `ClassifySplitter` | `classify.py` | 默认无切片对象 | "inherit" 模式: 每切片一个合成对象 |

## 子系统 2: 视口渲染 (在线)

### Camera2D (`views/labeling/viewport/camera.py`)

HALCON 风格 DisplayPart 相机:
- 缩放: `min_width = max(viewport_w/max_zoom, 2.0)`
- 平移: 防止滚出边界
- `zoom_at_view_point(x, y, factor)`

### QImageRegionProvider (`views/labeling/viewport/image_provider.py`)

4 层金字塔 (全分辨率 → 1/8):
- 256 MB 预算每层
- 惰性构建 (QImageReader)
- GPU 驻留 QPixmap
- `_select_level()` — 最近 1:1 密度比

### 渲染流程

```
Canvas.paintEvent()
  → Camera2D.visible (图像坐标下的 RectF)
  → QImageRegionProvider.read_region(rect_l0, target_size)
    → _ensure_pyramid()    ← 惰性构建
    → _select_level()      ← 选择最佳金字塔层
    → _read_from_level()   ← 从 QPixmap 复制 + 缩放
  → QPainter.drawPixmap(viewport_rect, pixmap)
```

## 图像源 (`platform/infrastructure/image_sources/`)

`LargeImageSource(Protocol)`:
- `metadata() → ImageMetadata`
- `read_region(rect_l0, output_size, level_hint=None) → np.ndarray`
- `read_pixel(x, y) → tuple[int, ...]`

| 实现 | 文件 | 后端 | ROI | 金字塔 |
|------|------|------|-----|--------|
| `FileImageSource` | `file_source.py` | ImageReader (PIL) → 内存数组 | ✅ (数组切片) | ❌ |
| `QtImageSource` | `qt_image_source.py` | QImageReader | ✅ (setClipRect) | ❌ |
| `TiffImageSource` | `tiff_image_source.py` | PIL (惰性打开) | 有条件 (仅分块 TIFF) | 检测子 IFD |
| `MemoryImageSource` | `memory_image_source.py` | numpy 数组 | ✅ | ❌ |

⚠️ `QtImageSource`: 每次 `read_region()` 创建新 QImageReader 实例，导致完整的 文件打开+头部解码+解码 周期。对大量切片访问有性能影响。

## ImageReader 统一 I/O (`platform/infrastructure/image_reader.py`)

| 方法 | 后端优先级 | 说明 |
|------|-----------|------|
| `read()` | PIL → Qt → OpenCV | 完整图像解码 |
| `read_region()` | Qt → 回退完整读取+裁剪 | ROI 无完整解码 |
| `metadata()` | Qt → PIL → OpenCV | 零像素解码元数据 |
| `read_pages()` | PIL | 多页 TIFF |
| `pages()` | PIL | 多页帧计数 |

## 未接入/死代码

| 组件 | 文件 | 备注 |
|------|------|------|
| `HugeImageCanvas` | `views/labeling/widgets/huge_image_canvas.py` | pyqtgraph 实现, 3 级 LOD, 有测试, 从未导入 |
| `TileCache` | `views/labeling/viewport/tile_cache.py` | LRU 字节淘汰, 零消费者 |
| `tiles_for_rect()`, `TileKey` | `views/labeling/viewport/tile_grid.py` | 零消费者 |

## 实现状态

| 功能 | 状态 |
|------|------|
| TilePlanner (规则网格) | ✅ |
| TileMaterializer (PNG) | ✅ |
| 5 个标签分割器 | ✅ |
| LargeImageSource 协议 + 4 个实现 | ✅ |
| Camera2D 缩放/平移 | ✅ |
| QImageRegionProvider 金字塔 | ✅ |
| Canvas QPainter 渲染 | ✅ |
| ImageReader 统一 I/O | ✅ |
| QtImageSource ROI 性能 | ⚠️ 每次创建新实例, 文档已标记 |
| HugeImageCanvas (pyqtgraph) | ⚠️ 已实现, 未接入 |
| TileCache (在线切片) | ⚠️ 已实现, 未使用 |
| pad 边缘填充 | ❌ |
| 在线切片渲染 (TileGrid) | ❌ |
| 自适应/语义切片 | ❌ 仅规则网格策略 |
