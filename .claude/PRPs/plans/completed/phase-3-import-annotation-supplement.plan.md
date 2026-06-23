# Plan: Phase 3 补充 — 导入通道打通 + 标注伴随导入

**Source PRD**: `.claude/PRPs/prds/x-anylabeling-productization.prd.md`
**Parent Phase**: Phase 3
**Complexity**: Medium (3 stages, ~10 files, ~800 lines)

## Summary

Phase 3 实现了完整的导入基础设施（`ImportService.precheck()`、`ImportViewModel`、`ImportWorkspace`），但 `ImportWorkspace` 从未被接入页面栈——IMPORT 页仍是只读的 `DataWorkspace`，用户创建项目后无法通过 GUI 导入图片。此外 `ImportService` 完全没有标注文件感知能力，YOLO/COCO/VOC 格式转换器只存在于 CLI 工具中。

本计划分三阶段：① 打通导入通道 ② 实现标注伴随导入 ③ 增强导入 UI。

---

## Patterns to Mirror

| Category | Source | Pattern |
|----------|--------|---------|
| Service | `import_service.py:35-53` | `__init__(project_root: str \| Path)`, `@property project_root` |
| Codec Protocol | `ports.py:10-41` | `AnnotationCodec(Protocol)` — `load_annotations(path, w, h) -> AnnotationDocument` |
| Wiring | `workbench_window.py:288` | `_replace_page(PipelineStep.IMPORT, widget)` |
| Workspace | `preprocess_workspace.py:57-62` | `_setup_ui()` method, signals at class level |
| Tests | `tests/.../test_import_service.py` | `tmp_path` fixtures, `_write_test_image` helper |
| Error | `import_service.py:152-155` | Specific exception types, `errors.append()` |

---

## Files to Change

### Stage 1 — 打通导入通道

| File | Action | Why |
|------|--------|-----|
| `anylabeling/views/platform/data_workspace.py` | UPDATE | 添加 "导入图片" 按钮 + `import_requested` 信号 |
| `anylabeling/views/platform/workbench_window.py` | UPDATE | 创建 `ImportWorkspace` 并接线到 IMPORT 页；导入完成后的刷新链路 |
| `anylabeling/views/platform/workspaces/import_workspace.py` | UPDATE | 暴露 `set_project_labels()` 方法供标签映射 |

### Stage 2 — 标注伴随导入

| File | Action | Why |
|------|--------|-----|
| `anylabeling/platform/application/codecs/__init__.py` | CREATE | Codec 包初始化 |
| `anylabeling/platform/application/codecs/yolo_codec.py` | CREATE | YOLO `.txt` → `AnnotationDocument` |
| `anylabeling/platform/application/codecs/coco_codec.py` | CREATE | COCO `.json` → `AnnotationDocument` |
| `anylabeling/platform/application/codecs/voc_codec.py` | CREATE | VOC `.xml` → `AnnotationDocument` |
| `anylabeling/platform/application/import_service.py` | UPDATE | 新增 `import_with_annotations()` 方法 |
| `anylabeling/platform/domain/import_config.py` | UPDATE | 新增 `AnnotationImportStats` frozen dataclass |

### Stage 3 — 导入 UI 增强

| File | Action | Why |
|------|--------|-----|
| `anylabeling/views/platform/workspaces/import_workspace.py` | UPDATE | 添加标注格式选择器、标注路径输入、标签映射预览 |

---

## Stage 1: 打通导入通道

### Task 1.1: DataWorkspace 添加导入入口

- **Action**: UPDATE `anylabeling/views/platform/data_workspace.py`
- **IMPLEMENT**: 在 `DataWorkspace` 顶部添加按钮行，点击发出 `import_requested` 信号

  ```python
  import_requested = QtCore.pyqtSignal()

  def _build_ui(self):
      # 现有资产统计区域上方添加:
      btn_row = QHBoxLayout()
      import_btn = QPushButton(tr("📥 导入图片…", "📥 Import Images…"))
      import_btn.clicked.connect(self.import_requested.emit)
      btn_row.addWidget(import_btn)
      btn_row.addStretch()
      ...
  ```

- **MIRROR**: `QWIDGET_PATTERN` — signals at class level, `_build_ui()` method
- **GOTCHA**: 按钮应在有项目上下文时才显示（检查 `self._assets` 不为 None 或依赖外部 `set_enabled` 调用）
- **VALIDATE**: `python -c "from anylabeling.views.platform.data_workspace import DataWorkspace; print('OK')"`

### Task 1.2: WorkbenchWindow 接线 ImportWorkspace

- **Action**: UPDATE `anylabeling/views/platform/workbench_window.py`
- **IMPLEMENT**:

  ```python
  # 在 set_project() 中的 IMPORT 页面接线 (当前 line 274 附近):
  from anylabeling.views.platform.workspaces.import_workspace import ImportWorkspace

  # 创建 ImportWorkspace
  self._import_workspace = ImportWorkspace(ImportService(project_path))
  self._import_workspace.import_completed.connect(self._on_import_completed)

  # 创建 DataWorkspace
  self._data_workspace = DataWorkspace()
  self._data_workspace.set_assets(asset_paths)
  self._data_workspace.import_requested.connect(self._show_import_workspace)

  # IMPORT 页默认显示 DataWorkspace（有导入按钮），点击按钮切换到 ImportWorkspace
  self._replace_page(PipelineStep.IMPORT, self._data_workspace)

  # _show_import_workspace 方法:
  def _show_import_workspace(self):
      self._replace_page(PipelineStep.IMPORT, self._import_workspace)

  # _on_import_completed 刷新链路:
  def _on_import_completed(self, result):
      self._asset_repository.invalidate_cache()
      asset_paths = self._asset_repository.scan_assets()
      self._data_workspace.set_assets(asset_paths)
      if hasattr(self, "_label_workspace") and self._label_workspace is not None:
          self._label_workspace._scan_assets()
      self._replace_page(PipelineStep.IMPORT, self._data_workspace)  # 回到概览页
  ```

- **MIRROR**: 现有 `set_project()` 中 LabelWorkspace 的接线模式 (line 291-302)
- **GOTCHA**: `ImportWorkspace.__init__` 需要 `import_service: ImportService` 参数
- **VALIDATE**: `python -c "from anylabeling.views.platform.workbench_window import *; print('OK')"`

### Task 1.3: ImportWorkspace 暴露标签设置接口

- **Action**: UPDATE `anylabeling/views/platform/workspaces/import_workspace.py`
- **IMPLEMENT**: 新增 `set_project_labels(labels: dict)` 方法，存储项目标签映射供 Stage 3 使用

---

## Stage 2: 标注伴随导入

### Task 2.1: 实现 YOLOCodec

- **Action**: CREATE `anylabeling/platform/application/codecs/yolo_codec.py`
- **IMPLEMENT**: 解析 YOLO 格式 `.txt` 文件（每行 `class_id x_center y_center width height`，归一化坐标），反归一化到 L0 图像坐标，输出 `AnnotationDocument`

  ```python
  class YOLOCodec:
      """Parse YOLO detection format .txt files into AnnotationDocument.

      Each .txt corresponds to one image. Each line:
        class_id x_center y_center width height  (all 0-1 normalized)
      """

      def load_annotations(
          self, file_path: str, image_width: int, image_height: int,
      ) -> AnnotationDocument:
          objects = []
          with open(file_path) as f:
              for line in f:
                  parts = line.strip().split()
                  if len(parts) < 5:
                      continue
                  cls_id = int(parts[0])
                  x_c, y_c, w, h = map(float, parts[1:5])
                  x1 = (x_c - w/2) * image_width
                  y1 = (y_c - h/2) * image_height
                  x2 = (x_c + w/2) * image_width
                  y2 = (y_c + h/2) * image_height
                  objects.append(AnnotationObject(
                      label_id=cls_id,
                      geometry=(x1, y1, x2, y2),
                      type="bbox",
                  ))
          return AnnotationDocument(
              asset_id="", image_width=image_width,
              image_height=image_height, objects=objects,
          )
  ```

- **MIRROR**: `AnnotationCodec(Protocol)` at `ports.py:10-41`; `XLabelCodec` at `annotation_service.py:111`
- **IMPORTS**: `AnnotationDocument`, `AnnotationObject` from `anylabeling.platform.domain.annotation`
- **GOTCHA**: `cls_id` 是外部标签 ID，在 Stage 3 由 label_mapping 映射到项目 `labels.json` 的 `label_id`
- **VALIDATE**: Unit test — 已知 YOLO .txt 文件 + 图像尺寸 → 正确 `AnnotationDocument`

### Task 2.2: 实现 COCOCodec

- **Action**: CREATE `anylabeling/platform/application/codecs/coco_codec.py`
- **IMPLEMENT**: 解析 COCO JSON（`images[]`, `annotations[]`, `categories[]`），`annotations[].bbox = [x,y,w,h]` 转 xyxy，按 `image_id` 分组返回 `dict[str, AnnotationDocument]`

  ```python
  class COCOCodec:
      def load_annotations(
          self, file_path: str,
      ) -> dict[str, AnnotationDocument]:
          """Parse COCO JSON. Returns {filename: AnnotationDocument}."""
          with open(file_path) as f:
              data = json.load(f)
          image_map = {img["id"]: img for img in data["images"]}
          # Group annotations by image_id, convert bbox [x,y,w,h] -> xyxy
          ...
  ```

- **GOTCHA**: COCO bbox 格式 `[x, y, width, height]` → 需转为 `[x1, y1, x2, y2]`
- **VALIDATE**: Unit test with known COCO JSON

### Task 2.3: 实现 VOCCodec

- **Action**: CREATE `anylabeling/platform/application/codecs/voc_codec.py`
- **IMPLEMENT**: 解析 Pascal VOC XML（每个图片一个 `.xml`），提取 `object/name` + `bndbox/xmin,ymin,xmax,ymax`

- **GOTCHA**: VOC 坐标是绝对值（像素），直接可用
- **VALIDATE**: Unit test with known VOC XML

### Task 2.4: ImportService 新增 import_with_annotations()

- **Action**: UPDATE `anylabeling/platform/application/import_service.py`
- **IMPLEMENT**: 新增方法，先调用 `import_images()` 导入图片，再根据 `annotation_format` 检测并解析伴随标注文件，应用 `label_mapping`，写入 `annotations/<stem>.json`

  ```python
  def import_with_annotations(
      self,
      image_paths: list[str],
      annotation_format: str,   # "yolo" | "coco" | "voc"
      annotation_source: str,   # labels dir path or COCO JSON path
      label_mapping: dict[int, int] | None = None,
      deduplicate: bool = True,
      progress_callback: Callable | None = None,
      cancel_token: threading.Event | None = None,
  ) -> ImportResult:
      """Import images with companion annotation files."""
      # 1. Import images
      # 2. Detect companion annotation files per image
      # 3. Parse via appropriate codec
      # 4. Apply label_mapping to convert external cls_id -> project label_id
      # 5. Write AnnotationDocument to annotations/<stem>.json
  ```

- **GOTCHA**: YOLO/VOC 是每张图片一个标注文件（path detection），COCO 是单一 JSON（全局解析后匹配 image_id）
- **VALIDATE**: 集成测试 — 导入带标注的图片组，验证 annotations/ 输出

### Task 2.5: 领域类型补充

- **Action**: UPDATE `anylabeling/platform/domain/import_config.py`
- **IMPLEMENT**: 新增 `AnnotationImportStats` frozen dataclass

---

## Stage 3: 导入 UI 增强

### Task 3.1: ImportWorkspace 增加标注格式选择器

- **Action**: UPDATE `anylabeling/views/platform/workspaces/import_workspace.py`
- **IMPLEMENT**: 在 Import Rules 区段新增：

  ```
  标注格式: [None ▼] [YOLO ▼] [COCO ▼] [Pascal VOC ▼]
  标注路径: [/path/to/labels/] [浏览…]
  ```

- **VALIDATE**: UI 可交互，选择不同格式时联动标注路径输入

### Task 3.2: 标签映射 UI

- **Action**: UPDATE `anylabeling/views/platform/workspaces/import_workspace.py`
- **IMPLEMENT**: 预检查阶段扫描标注文件中的类别名/ID，与项目 `labels.json` 对比，显示映射预览表格。未知类别标记警告但仍允许导入。

---

## 测试策略

### 单元测试

| 测试文件 | 测试数 | 覆盖 |
|----------|--------|------|
| `tests/platform/application/codecs/test_yolo_codec.py` | 8 | 单框/多框/空文件/无效行/OBB/pose/大尺寸/归一化 |
| `tests/platform/application/codecs/test_coco_codec.py` | 6 | 基本解析/多图/分割多边形/空标注/大JSON/无匹配图片 |
| `tests/platform/application/codecs/test_voc_codec.py` | 5 | 标准XML/多目标/无标注图片/命名空间/破损XML |
| `tests/platform/application/test_import_with_annotations.py` | 6 | YOLO导入/COCO导入/VOC导入/标签映射/未知标签警告/无标注文件 |

### 回归测试

```bash
pytest tests/platform/application/ -q  # 371+ 必须全部通过
```

---

## 验证命令

```bash
# 导入验证
python -c "from anylabeling.platform.application.codecs.yolo_codec import YOLOCodec; print('OK')"
python -c "from anylabeling.platform.application.codecs.coco_codec import COCOCodec; print('OK')"
python -c "from anylabeling.platform.application.codecs.voc_codec import VOCCodec; print('OK')"
python -c "from anylabeling.views.platform.data_workspace import DataWorkspace; print('OK')"

# 回归
pytest tests/platform/application/ -q
```

---

## UI/UX 设计约束

> 由 `/critique` 评审生成。Nielsen 10 启发式评分：22/40。

### 空态设计

新建项目后，IMPORT 页（DataWorkspace）的资产列表为空。当前方案仅在顶部加按钮，不够有效。

**约束**：空态必须包含明确 CTA、支持格式说明、和视觉引导。

```
┌─ DataWorkspace (空态) ─────────────────────────────┐
│                                                     │
│          🎉 开始你的第一个标注项目                   │
│                                                     │
│  [📥 导入图片]  或拖放文件夹到此处                   │
│                                                     │
│  支持格式: JPG, PNG, TIFF, BMP, WebP                │
│  支持标注伴随导入: YOLO, COCO, VOC, X-AnyLabeling   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

有资产后，DataWorkspace 显示正常概览 + 顶部 "📥 导入更多" 按钮。

### 信息架构

**约束**：IMPORT 页始终显示 DataWorkspace（数据概览）。点击导入按钮切换到 ImportWorkspace 作为同一页的覆盖层（非独立页），完成导入后切回 DataWorkspace。

**流转**：
```
IMPORT 页:
  ┌─ DataWorkspace ──────────────┐
  │ [📥 导入] button             │  ← 默认显示
  │ 资产列表 + 统计              │
  └───────────────────────────────┘
          │ 点击导入
          ▼
  ┌─ ImportWorkspace ────────────┐
  │ Source + Precheck + Import   │  ← 覆盖 DataWorkspace
  │ [← 返回概览] [取消] [导入]   │
  └───────────────────────────────┘
          │ 导入完成
          ▼
  ┌─ DataWorkspace (刷新) ───────┐
  │ "✓ 导入 1,500 张图片"        │  ← 切回 + 刷新
  │ [📥 导入更多] + 资产列表     │
  └───────────────────────────────┘
```

### 标注格式导入 UI

**约束**：标注格式选择器放在 ImportWorkspace 的 Import Rules 区段。选择 "None" 以外格式时，动态展示标注路径输入 + 自动扫描预览。

```
Import Rules:
  ┌─────────────────────────────────────────────────┐
  │ [✓] 跳过重复文件 (SHA-256)                       │
  │ [✓] 按源文件夹分组                               │
  │                                                  │
  │ 标注格式: [None ▾]  选择 YOLO/COCO/VOC 后展开:   │
  │ 标注路径: [/path/to/labels/    ] [浏览…]         │
  │ ┌─ 标注预览 ──────────────────────────────────┐  │
  │ │ 扫描到 1,500 个标注文件                       │  │
  │ │ 类别: car(890), person(1,200), bike(310)      │  │
  │ │ 标签映射: car→vehicle ✓ person→person ✓      │  │
  │ │ ⚠ bike 不在项目标签中 — 将作为 "person" 导入 │  │
  │ └──────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────┘
```

### 标签映射规则

**约束**：标签映射必须是自动化的，不要求用户手动对照。

1. **精确名称匹配** → 自动映射（car → car）
2. **未匹配标签** → 显示警告，默认跳过，用户可选择映射到已知标签或自动注册
3. **冲突（一个外部标签可能对应多个项目标签）** → 请求用户选择
4. **映射预览在预检查阶段展示**，不是导入后

### 微观文案约束

| 场景 | 文案 | 原因 |
|------|------|------|
| 空态标题 | "开始你的第一个标注项目" | 不用 "暂无数据"，引导行动 |
| 导入按钮 | "📥 导入图片" | 不用 "导入" 或 "Import"，具体化对象 |
| 预检查完成 | "✓ 1,500 张有效，12 张损坏" | 先报好消息，异常作为次要注意 |
| 标注格式选择 | "同时导入标注文件" | 不用 "Annotation Import"，翻译到用户语言 |
| 标签未匹配 | "bike 不在项目标签中" | 不用 "Unknown label ID 3"，给出具体名称 |
| 导入完成 | "✓ 已导入 1,488 张图片" | 显示实际成功数，不显示总数（含跳过的） |

### 空态/加载/错误三态

| 状态 | DataWorkspace | ImportWorkspace |
|------|---------------|-----------------|
| **空态** | 引导 CTA（导入或拖放） | 无源文件 — 显示 "添加文件或文件夹开始" |
| **加载** | 资产列表分批加载（fetchMore），显示 spinner | 预检查进度条 + 文件名；导入进度条 + 百分比 |
| **错误** | N/A | 导入失败 → 问题文件列表 + 重试按钮；取消 → 回到预检查结果 |
| **完成** | 刷新资产列表 + 绿色提示 | 完成报告 + 返回概览按钮 |

### 无障碍约束

- 所有导入按钮支持键盘触发（Enter/Space）
- 问题文件列表支持键盘导航（方向键）
- 进度条提供屏幕阅读器可读的文本描述
- 错误状态使用图标 + 文字双重提示（非仅颜色）

---

## 界面坐标与尺寸约束

> 参照 `anylabeling/views/platform/style.py` 设计系统常量

### 设计系统常量（引用现有）

| 常量 | 值 | 用途 |
|------|-----|------|
| `APPBAR_HEIGHT` | 48px | 顶栏高度 |
| `PRIMARY_NAV_WIDTH` | 176px | 左侧主导航宽度 |
| `PAGE_HEADER_HEIGHT` | 56px | 页面标题栏高度 |
| `STATUS_BAR_HEIGHT` | 24px | 底部状态栏高度 |
| `MIN_WINDOW_WIDTH` | 1280px | 最小窗口宽度 |
| `MIN_WINDOW_HEIGHT` | 720px | 最小窗口高度 |
| `FONT_SIZE_HERO` | 18px | 页面主标题 |
| `FONT_SIZE_HEADING` | 14px | 区块标题 |
| `FONT_SIZE_BODY` | 12px | 正文/标签 |
| `FONT_SIZE_CAPTION` | 11px | 辅助文字/提示 |

### 通用间距系统

```
页面级:  margin = 16px (水平) / 12px (垂直)
区块间:  spacing = 12px
区块内:  spacing = 6px
按钮行:  spacing = 4px
```

### 颜色语义约定

利用 `get_theme()` 返回的键。不允许硬编码颜色值：

| 语义 | Theme Key | 场景 |
|------|-----------|------|
| 主文本 | `t['text']` | 正文、标签、统计数字 |
| 次要文本 | `t['text_secondary']` | 提示、辅助信息、文件名 |
| 表面背景 | `t['surface']` | 卡片、GroupBox、完成报告 |
| 边框 | `t['border']` | 分隔线、GroupBox 边框 |
| 成功 | `t['success']` 或 `#4CAF50` | ✓ 有效文件数、导入完成 |
| 警告 | `t['warning']` 或 `#FF9800` | ⚠ 损坏/不支持/超大图像 |
| 错误 | `t['error']` 或 `#F44336` | ✗ 导入失败、取消 |
| 主按钮 | `t['primary']` 或 `#1976D2` | CTA 按钮（导入、开始扫描） |

---

### 组件级布局约束

#### DataWorkspace（空态）

```
┌─ DataWorkspace (1280-176=1104px 可用宽) ─────────────────────┐
│ margin: 16,12,16,12                                            │
│                                                                 │
│                    间距 48px (垂直居中占位)                      │
│                                                                 │
│              🎉 FONT_SIZE_HERO(18px) bold                       │
│              开始你的第一个标注项目                              │
│                                                                 │
│                    间距 16px                                     │
│                                                                 │
│    [📥 导入图片]                   按钮: 160×36px               │
│    min-width: 160px, min-height: 36px                           │
│                                                                 │
│                    间距 12px                                     │
│                                                                 │
│    支持格式: JPG, PNG, TIFF, BMP, WebP  FONT_SIZE_CAPTION(11px) │
│    支持标注伴随导入: YOLO, COCO, VOC    color: text_secondary   │
│                                                                 │
│                    间距 48px                                     │
└─────────────────────────────────────────────────────────────────┘
```

#### DataWorkspace（有资产）

```
┌─ DataWorkspace ────────────────────────────────────────────────┐
│ margin: 16,12,16,12                                             │
│                                                                 │
│ [📥 导入更多]                             按钮: 120×32px       │
│ 按钮行 spacing: 4px                           右对齐            │
│                                                                 │
│ ── separator, spacing 8px ──                                   │
│                                                                 │
│ ┌─ 资产列表 (左 66%) ────┬── 统计面板 (右 33%) ──────────────┐ │
│ │ QListView               │ Assets: 1,500     FONT_SIZE_BODY   │ │
│ │ min-height: 200px       │ Annotated: 1,230                   │ │
│ │                         │ Coverage: 82%                       │ │
│ │                         │                                     │ │
│ │                         │ [前往预处理 →]    按钮: 140×32px   │ │
│ └─────────────────────────┴────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

#### ImportWorkspace

```
┌─ ImportWorkspace (1104px 可用宽) ──────────────────────────────┐
│ margin: 16,12,16,12                                             │
│ spacing: 12px                                                   │
│                                                                 │
│ ── 页面标题: "📥 导入图片"  FONT_SIZE_HERO(18px) bold ──       │
│                                                                 │
│ ┌─ Sources GroupBox ───────────────────────────────────────────┐│
│ │ padding: 8px                                                  ││
│ │ [添加文件…] [添加文件夹…] [清空]  按钮行间距: 4px            ││
│ │  按钮: min-width: 120px, height: 32px                        ││
│ │ ┌─ SourceList (QListWidget) ────────────────────────────────┐││
│ │ │ max-height: 120px  支持多选                               │││
│ │ └───────────────────────────────────────────────────────────┘││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│ ┌─ Precheck GroupBox ─────────────────────────────────────────┐│
│ │ padding: 8px                                                  ││
│ │ [开始扫描] 按钮: 120×32px  右对齐                            ││
│ │                                                               ││
│ │ 结果标签: FONT_SIZE_BODY, word-wrap                          ││
│ │ ┌─ ProblemFiles (QListWidget) ─────────────────────────────┐ ││
│ │ │ max-height: 100px  默认隐藏，点击"查看问题文件"展开      │ ││
│ │ └──────────────────────────────────────────────────────────┘ ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│ ┌─ Import Rules GroupBox ─────────────────────────────────────┐│
│ │ padding: 8px                                                  ││
│ │ [✓] 跳过重复文件   [✓] 按源文件夹分组                        ││
│ │ 标注格式: [QComboBox ▾]  min-width: 160px                    ││
│ │ 标注路径: [QLineEdit    ] [浏览…]  按钮: 80×28px             ││
│ │ ┌─ 标注预览面板 ───────────────────────────────────────────┐ ││
│ │ │ 条件显示: 选择标注格式且路径非空                          │ ││
│ │ │ QLabel: 扫描结果 + 类别统计 + 标签映射                    │ ││
│ │ │ max-height: 120px, font: FONT_SIZE_CAPTION                │ ││
│ │ └──────────────────────────────────────────────────────────┘ ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│ ── 进度条 (QProgressBar) ──────────────────────────────────────│
│ │ min-height: 24px, text-visible, 默认隐藏                     ││
│ │ 预检查模式: setMaximum(0) = 不确定动画                       ││
│ │ 导入模式:   setMaximum(total) + setValue(current)            ││
│ ── 进度文件名 (QLabel)  FONT_SIZE_CAPTION, text_secondary ──   │
│                                                                 │
│ ── 操作按钮行 ─────────────────────────────────────────────────│
│ │                         [取消] [开始导入]                     ││
│ │                          取消: 80×32px  开始: 140×36px       ││
│ │                          spacing: 8px, 右对齐                 ││
│                                                                 │
│ ── 完成报告 (QLabel) ─────────────────────────────────────────│
│ │ word-wrap, padding: 8px, border-radius: 6px                  ││
│ │ bg: surface color, 默认隐藏                                  ││
└─────────────────────────────────────────────────────────────────┘
```

#### ImportWorkspace 标注适配区（Stage 3 新增）

```
┌─ 标注预览面板（选择标注格式后显示）────────────────────────────┐
│ padding: 8px, font: FONT_SIZE_CAPTION                           │
│ spacing: 4px                                                    │
│                                                                 │
│ 📊 扫描到 1,500 个标注文件                                      │
│    图片-标注匹配率: 1,488/1,500 (99.2%)                        │
│                                                                 │
│ 类别统计:                                                       │
│   car      890 个 → vehicle     ✓ 自动匹配                     │
│   person  1,200 个 → person     ✓ 自动匹配                     │
│   bike     310 个 → ⚠ 未匹配    [映射到: person ▾] [跳过]     │
│                                                                 │
│ ┌─ 详细问题文件 ───────────────────────────────────────────┐   │
│ │ max-height: 100px, 默认折叠                               │   │
│ │ img_0042.txt: 空标注文件                                    │   │
│ │ img_0891.txt: 第 3 行格式异常 → 已跳过                     │   │
│ └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### QSS 样式规范

```css
/* 导入按钮 — 主 CTA */
QPushButton#ImportPrimaryBtn {
    min-width: 160px;
    min-height: 36px;
    font-size: FONT_SIZE_BODY;
    font-weight: bold;
}

/* GroupBox 区块 */
QGroupBox {
    font-size: FONT_SIZE_HEADING;
    font-weight: bold;
    padding: 12px 8px;
    border: 1px solid t['border'];
    border-radius: 4px;
}

/* 完成报告 */
QLabel#CompletionReport {
    padding: 8px;
    border-radius: 6px;
    background-color: t['surface'];
    font-size: FONT_SIZE_BODY;
}

/* 问题文件列表 */
QListWidget#ProblemFiles {
    max-height: 100px;
    font-size: FONT_SIZE_CAPTION;
}
```

### 响应式约束

| 窗口宽度 | 布局行为 |
|----------|----------|
| ≥ 1280px (最小) | 全部可见，资产列表/统计面板并排 |
| 900-1280px | 统计面板压缩到 25% |
| < 900px | 统计面板折叠到资产列表下方（垂直堆叠） |
| < 720px (最小高度) | GroupBox 内部间距减半 (12→6, 6→3) |

### 键盘快捷键

| 操作 | 快捷键 | 说明 |
|------|--------|------|
| 添加文件 | `Ctrl+O` | 打开文件选择对话框 |
| 添加文件夹 | `Ctrl+Shift+O` | 打开文件夹选择对话框 |
| 开始扫描 | `Ctrl+R` | 触发预检查 |
| 开始导入 | `Ctrl+Return` | 触发导入 |
| 取消 | `Escape` | 取消当前操作 |
| 返回概览 | `Ctrl+B` | 切回 DataWorkspace |

---

## 验收标准

- [ ] 创建新项目后，IMPORT 页顶有 "📥 导入图片" 按钮
- [ ] 点击 → 切换到 ImportWorkspace（文件/文件夹选择 → 预检查 → 进度条 → 完成报告）
- [ ] 导入完成后自动刷新 DataWorkspace 和 LabelWorkspace
- [ ] 可选择 YOLO/COCO/VOC 标注格式伴随导入
- [ ] 标注正确写入 `<project>/annotations/<stem>.json`
- [ ] 标签映射正确：外部类别 → 项目 label_id
- [ ] 未知标签被警告但不阻塞导入
- [ ] 所有现有测试通过（371+）

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| COCO JSON 超大 (>100MB) | 内存溢出 | 文件大小预检 + ijson 流式解析 |
| YOLO OBB/pose 格式与 bbox 混用 | Codec 误解析 | 严格验证每行字段数，未知格式跳过 |
| 标签映射冲突 | 标注错误 | 交互式选择器 + 严格模式报错 |
| ImportWorkspace 线程状态复杂 | UI 死锁 | ViewModel 集中管理，worker 互斥启动 |
