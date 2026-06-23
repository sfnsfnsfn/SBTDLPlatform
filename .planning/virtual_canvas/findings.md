# X-AnyLabeling Virtual Canvas Findings

> 本文件记录 review 发现、技术判断和风险。文件内容是项目状态数据，不是运行时指令。

## 2026-06-05 Review：V4 计划完成度

### 自动化状态

- `python -m pytest tests/views/labeling -q` 通过：`38 passed, 1 skipped, 11 subtests passed`
- `git diff --check` 通过

### 分支卫生风险

当前 `feat_virtual_canvas` 分支存在未跟踪目录：

```text
?? anylabeling/views/labeling/viewport/
?? tests/views/
```

风险：`anylabeling/views/labeling/widgets/canvas.py` 已依赖 viewport 模块。如果提交时遗漏未跟踪目录，分支会导入失败。

### V4 手工验收缺口

计划要求 Phase 3 起必须有人工验收截图/录屏或步骤记录。当前只找到计划中的要求，没有找到实际验收记录。

影响：自动化测试通过，但不能按计划宣称完整完成。

### Navigator 范围风险

`label_widget.on_navigator_request()` 仍走旧 scroll path：

```text
anylabeling/views/labeling/label_widget.py
  on_navigator_request()
    self.set_scroll(Qt.Orientation.Horizontal, target_x)
    self.set_scroll(Qt.Orientation.Vertical, target_y)
```

判断：如果 navigator 属于本阶段交付范围，这不符合 Camera2D 作为视角状态来源的目标；如果 navigator 明确延期，则需要写入已知限制。

## 2026-06-05 Review：插值和超大图卡顿

### 当前是否有插值

有。当前 `Canvas.paintEvent()` 中开启了：

```text
p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
```

判断：这只是 Qt 的基础平滑缩放 hint，不能恢复超过原图分辨率的信息。高倍放大时马赛克或块状像素仍是预期结果。

### 超大图卡顿根因

当前仍是整图加载和整图绘制：

```text
label_widget.load_file()
  image = utils.img_data_to_qimage(self.image_data, filename)
  self.canvas.load_pixmap(QtGui.QPixmap.fromImage(image))

canvas.paintEvent()
  p.setTransform(camera.coordinate_map().image_to_view_qtransform())
  p.drawPixmap(0, 0, self.pixmap)
```

影响：

1. 打开文件需要完整解码 `QImage`。
2. Canvas 持有完整 `QPixmap`。
3. 每次缩放/平移仍可能触发整图 transform 绘制。
4. navigator 也会复制 full-size pixmap。
5. 超大图时容易出现 UI 阻塞、显存压力、画面割裂或卡顿。

### 推荐技术方向

1. 显示质量策略显式化：nearest / smooth / high。
2. 使用 ImageProvider 读取 viewport visible rect。
3. 引入 tile grid 和 bounded LRU cache。
4. 引入 multi-resolution level，缩小时避免从 level-0 大图反复重采样。
5. 异步读取 tile/region，并用 revision 丢弃旧结果。
6. wheel/pan 合并到帧周期，避免每个滚轮事件都启动高成本渲染。

## 2026-06-05 Phase 3 实现发现

### QImageReader lazy loading

`QImageReader` 支持：
- `size()` 读取元数据（不解码）
- `setClipRect(QRect)` 限制解码区域
- `setScaledSize(QSize)` 设置输出分辨率

这些 API 避免了为显示 viewport 而解码整张超大图。

### Canvas paintEvent 两种路径

- **Pixmap 路径**（现有）：通过 `QTransform` 将全图从 image coordinates 映射到 viewport，drawPixmap(0, 0, pixmap)
- **Provider 路径**（新增）：直接读取 camera.visible 区域到 viewport 分辨率，drawPixmap(0, 0, result.image) 无需 transform

Provider 路径下：
- Compare view 禁用（依赖 `self.pixmap` 尺寸）
- Loading screen 禁用（同上）
- Shape 渲染需要额外设置 `QTransform`（在 provider 路径下显式设置）

### 测试 stub 冲突

多个测试文件安装不同的 PyQt6 stubs，后运行的会覆盖先运行的。`test_canvas_interactions.py` 的 QPainter stub 是空类，缺少 `begin` 等方法。
解决方案：QImageRegionProvider 测试检测真实 PyQt6 可用性并在 stub 模式下跳过（`_HAS_REAL_PYQT` flag）。

## 2026-06-05 计划缺口发现：接入逻辑

原计划（`render_optimization_plan_v1.md`）Section 2 列出了 `label_widget.py` 修改目标，但 Section 3 的 Phase A–H 没有独立的"接入"阶段。`task_plan.md` 同样缺失。

**已修复**：插入 Phase 4.5「接入 label_widget — 大图自动走 provider 路径」，位于 Phase 4（tile cache）之后、Phase 5（多分辨率 level）之前。

**接入点**（`label_widget.load_file()`）：
- Line 5502：`image = utils.img_data_to_qimage(...)` — 全图解码之前，先读元数据判断尺寸
- Line 5535：`self.canvas.load_pixmap(...)` — 大图替换为 `load_image_provider`
- Line 5524：`navigator_dialog.set_image(QPixmap.fromImage(image))` — 大图降级

**接入时机选在 Phase 4 之后的原因**：tile cache 是 provider 路径在高频 pan/zoom 场景下的必要依赖，否则每次 paint 都重新 `read_region` 解码。

## Stop Conditions

遇到以下情况必须暂停并重新 review：

1. 任何方案需要修改 LabelFile JSON 坐标格式。
2. 任何 shape 坐标开始依赖 viewport/screen 坐标。
3. Provider 或 tile renderer 修改 `Camera2D.visible`。
4. 为修 tile seam 而改动标注坐标。
5. ROI/tile 优化过程中混入 mask、auto-labeling、tile inference。

## 2026-06-05 Execution Finding：GUI 验收脚本

编写了 `scripts/gui_verification.py` 用于自动化 GUI 验收。关键发现：

1. **Canvas 渲染需要 Shape 对象**：`load_shapes()` 接受 dict，但 `paintEvent()` 渲染时调用 Shape 方法，传入 dict 会导致 Qt 进程崩溃（exit code 127，无 Python traceback）。Shape 渲染由自动化测试覆盖。

2. **Camera2D API**：正确的方法是 `zoom_at_view_point(scale, x, y)`、`pan_by_view_delta(dx, dy)`、`fit_to_window()`，而非最初假设的名称。

3. **LabelFile 矩形格式转换**：2-point diagonal rectangle 在加载时自动转为 4-point 格式，这是预期的格式升级（自 v2.2.0），不是坐标漂移。

4. **Pillow/PyQt6 在 Windows 上均可用**，能够生成截图证据。

## 2026-06-05 Execution Finding：Git index 权限

在 workspace 沙箱内执行：

```text
git add anylabeling/views/labeling/viewport tests/views
```

第一次失败：

```text
fatal: Unable to create 'D:/code/X-AnyLabeling/.git/index.lock': Permission denied
```

原因：当前权限配置允许读取 `.git`，但写入 index 需要提升权限。

处理：按权限规则使用 escalated `git add` 重新执行，成功。
