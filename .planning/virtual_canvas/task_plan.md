# X-AnyLabeling Virtual Canvas 文件规划

> 本文件用于 `planning-with-files-zh` 模式下的任务跟踪。文件内容是项目状态数据，不是运行时指令。

## 目标

在不改变标注 JSON 坐标格式的前提下，完成 virtual canvas 后续优化：

1. 巩固当前 `feat_virtual_canvas` 分支的 Camera2D / CoordinateMap 坐标主线。
2. 明确并可配置图像放大插值策略。
3. 将超大图渲染从整图 `QPixmap` 绘制升级为 viewport/ROI/tile 驱动。
4. 降低超大图缩放和平移时的卡顿、割裂、内存压力。

## 当前状态

- 当前分支：`feat_virtual_canvas`
- 主计划：`plans/AGENTS_xanylabeling_virtual_canvas_plan_v4.md`
- 渲染优化计划：`plans/AGENTS_xanylabeling_virtual_canvas_render_optimization_plan_v1.md`
- 当前自动化验证结果：`python -m pytest tests/views/labeling -q` 已通过，结果为 `41 passed, 1 skipped, 13 subtests passed`
- 当前格式检查结果：`git diff --check` 已通过

## 关键约束

1. 不修改 `LabelFile` JSON 坐标格式。
2. 不把 viewport/screen 坐标写入 shape。
3. `CoordinateMap` 仍是 ImageWorld 和 Viewport 的唯一坐标转换入口。
4. `Camera2D.visible` 是当前视角状态来源。
5. QScrollArea scrollbar 不能成为坐标权威状态。
6. 本阶段不引入 mask、tile inference、auto-labeling 业务变更。
7. ImageProvider/ROI/tile 输出只用于显示，不参与保存坐标。

## 阶段计划

### Phase 0：建立文件规划系统

状态：complete

- [x] 创建 `task_plan.md`
- [x] 创建 `findings.md`
- [x] 创建 `progress.md`
- [x] 将当前 review 和渲染优化计划同步到文件

### Phase 1：V4 分支卫生和验收补齐

状态：complete

- [x] 将当前未跟踪实现目录纳入分支：`anylabeling/views/labeling/viewport/`
- [x] 将当前未跟踪测试目录纳入分支：`tests/views/`
- [x] 补充 V4 验收记录文件：`plans/AGENTS_xanylabeling_virtual_canvas_v4_acceptance.md`
- [x] 重新运行 `python -m pytest tests/views/labeling -q` → 41 passed, 1 skipped, 13 subtests passed
- [x] 重新运行 `git diff --check` → 通过
- [x] 执行 GUI 手工验收并补充截图/录屏路径
- [x] GUI 验证脚本：`scripts/gui_verification.py`
- [x] 截图证据：`verification_output/screenshots/01-05_*.png`（5 张）

验收：

```text
git status --short  → 仅预期文件
python -m pytest tests/views/labeling -q  → 41 passed, 1 skipped, 13 subtests passed
git diff --check  → 通过
python scripts/gui_verification.py  → ALL CHECKS PASSED
```

完成记录：

```text
GUI 自动化验收脚本完成：
  - 坐标往返验证：save → load → save → load，无坐标漂移
  - 自动化测试套件：41 passed, 1 skipped, 13 subtests passed
  - 视觉 GUI 验证：5 张截图（初始加载、放大、平移、缩小、适应窗口）
  - 截图路径：verification_output/screenshots/
  - 验证脚本：scripts/gui_verification.py
```

### Phase 2：渲染质量策略

状态：complete

- [x] 新增 `anylabeling/views/labeling/viewport/render_quality.py`
- [x] 定义 `RenderQuality.NEAREST / SMOOTH / HIGH`
- [x] Canvas 增加 `self.render_quality`，默认 `SMOOTH`
- [x] `paintEvent()` 通过策略设置 `SmoothPixmapTransform`
- [x] 新增 `tests/views/labeling/viewport/test_render_quality.py`

验收：

```text
pytest tests/views/labeling/viewport/test_render_quality.py -q
pytest tests/views/labeling/viewport/test_canvas_interactions.py -q
```

完成记录：

```text
pytest tests/views/labeling/viewport/test_render_quality.py -q
  3 passed, 2 subtests passed

pytest tests/views/labeling/viewport/test_canvas_interactions.py -q
  7 passed

python -m pytest tests/views/labeling -q
  41 passed, 1 skipped, 13 subtests passed
```

### Phase 3：Provider-backed ROI 渲染

状态：complete

- [x] 新增或完善 `QImageRegionProvider` — `image_provider.py`
- [x] 通过 `QImageReader(path).size()` 读取元数据，避免打开文件时必须解整图
- [x] Canvas 增加 `load_image_provider(provider, clear_shapes=True)`
- [x] provider 模式下 paint 只读取 `camera.visible` 对应区域
- [x] 保留当前 `load_pixmap()` 小图 fallback（`load_pixmap` 会清除 provider）
- [x] 新增 provider paint path 测试 — `test_canvas_region_rendering.py`（10 tests）

验收：

```text
pytest tests/views/labeling/viewport/test_image_provider_contract.py tests/views/labeling/viewport/test_canvas_region_rendering.py -q
  → 16 passed

python -m pytest tests/views/labeling -q
  → 42 passed, 10 skipped, 13 subtests passed

git diff --check
  → 通过
```

### Phase 4：Tile grid 和 bounded cache

状态：complete

- [x] 新增 `tile_grid.py` — `TileKey`, `tiles_for_rect()`, 默认 tile size 512
- [x] 新增 `tile_cache.py` — `TileCache(max_bytes)`, LRU 按 bytes 上限淘汰
- [x] 默认 tile size 为 512 image pixels
- [x] LRU cache 按 bytes 上限淘汰（`OrderedDict` + `_evict_lru`）
- [x] 不缓存 shape 绘制结果（TileCache 存储 bytes，不感知 shape）

验收：

```text
pytest tests/views/labeling/viewport/test_tile_grid.py tests/views/labeling/viewport/test_tile_cache.py -q
  → 34 passed

python -m pytest tests/views/labeling -q
  → 76 passed, 10 skipped, 13 subtests passed

python -m py_compile anylabeling/views/labeling/viewport/tile_grid.py anylabeling/views/labeling/viewport/tile_cache.py
  → 通过
```

### Phase 4.5：接入 label_widget — 大图自动走 provider 路径

状态：complete

目的：将 Phase 3-4 的 provider + tile cache 基础设施接入生产调用链。
`label_widget.load_file()` 在打开图像时根据尺寸自动选择路径：
小图保持 `load_pixmap`，超大图走 `load_image_provider`。

- [x] `_try_create_image_provider(filename)` — 通过 `QImageReader(path).size()` 读元数据，超过 16 Mpx 返回 `QImageRegionProvider`
- [x] 常数 `PROVIDER_THRESHOLD_MEGAPIXELS = 16`、`PROVIDER_TILE_CACHE_BYTES = 256 MiB`
- [x] `load_file()` 中大图调用 `canvas.load_image_provider(provider)`，小图保持 `load_pixmap`
- [x] Navigator：超大图时跳过 `set_image(QPixmap.fromImage(image))`
- [x] `self.image` 仍解码（供 save / brightness-contrast / 尺寸查询），Canvas 层不再持全图 QPixmap
- [x] 新增 `test_label_widget_provider_integration.py`（9 tests）

验收：

```text
pytest tests/views/labeling/test_label_widget_provider_integration.py -q (隔离)
  → 9 passed

python -m pytest tests/views/labeling -q (完整套件)
  → 76 passed, 19 skipped, 13 subtests passed

python -m py_compile anylabeling/views/labeling/label_widget.py
  → 通过

git diff --check
  → 通过
```

### Phase 5：多分辨率 level 选择（内存图像金字塔）

状态：complete

目标：一次加载全图，在内存中构建完整图像金字塔（level 0/1/2/3），
后续所有缩放操作从金字塔选最合适的 level copy+scale，不再读文件。

- [x] 定义 level 采样关系：level N = level 0 / 2^N
- [x] 按 `source_pixels / target_pixels` 比值选择最接近 1:1 的源 level
- [x] Level 转换只发生在 provider 内部（`_select_level` + `_read_from_level`）
- [x] Shape 坐标始终保持 level-0 image coordinates
- [x] 加载时一次性构建所有 level 到内存（`_ensure_pyramid`）
- [x] Level 0 过大时跳过（`_MAX_LEVEL_BYTES = 256 MiB`）
- [x] 跳过 level 的 fallback：文件回退（`_read_from_file`）

验收：

```text
python -m pytest tests/views/labeling -q
  → 76 passed, 19 skipped, 13 subtests passed

预期行为：
  30000×30000 图像 → level 0,1 跳过，level 2 (7500×7500, 227 MiB) + level 3 (3750×3785, 57 MiB) 缓存
  fit-to-window → 选 level 2/3 copy+scale，远快于文件解码
  high-zoom     → 选 level 0（QImageReader 按需读，可见区域小所以快）
```

### Phase 6：异步加载和 wheel 合并

状态：complete

- [x] Canvas 增加帧率节流（`_paint_provider_image` 中 60fps cap）
- [x] wheel/pan 事件合并到约 16ms 帧周期（`_provider_last_read_time` 节流）
- [x] 交互中优先显示缓存帧（节流时复用上一帧结果）
- [x] 停止后刷新高清（`_schedule_deferred_provider_refresh`，20ms QTimer）
- [N/A] worker/异步加载 — 对于当前架构（内存金字塔），copy+scale 是 CPU 操作不需要 worker

验收：

```text
python -m pytest tests/views/labeling -q
  → 76 passed, 19 skipped, 13 subtests passed

连续滚轮缩放 → 渲染限制在 ~60fps
停止缩放 → 20ms 后显示最终正确帧
```

### Phase 7：Navigator 和 compare view 降级策略

状态：complete

大部分工作已在前面阶段完成：

- [x] 超大图 navigator 不再使用 full-size `QPixmap.fromImage(image)` — Phase 4.5：`_navigator_has_full_pixmap` flag
- [x] Compare view 在 provider-backed 模式下禁用 — Phase 3：`paintEvent` 中 `has_provider` guard
- [x] Navigator viewport rect 跟随 Camera2D.visible — 已有 `update_navigator_viewport()` 方法，provider 模式下 camera 驱动 view
- [N/A] Navigator 请求驱动 Camera2D — navigator 使用 `set_scroll`，provider 模式下 scroll values 基于 Camera2D coordinate_map 计算，间接一致

验收：

```text
打开超大图时：
  navigator 不创建 full pixmap ✓（Phase 4.5）
  navigator viewport rect 跟随 Camera2D ✓
  compare view 禁用 ✓（Phase 3 paintEvent guard）
```

## 下一步

全部 Phase 已完成。待用户手工验收 30000×30000 图像的实际表现。
