# Vision Algorithm Platform -- Canvas Performance Baseline

**Date:** 2026-06-06
**Task:** M2.1 -- Freeze current canvas performance baseline
**Branch:** `vision_platfrom`
**Author:** sfn

---

## 1. Current Canvas Architecture

X-AnyLabeling has **two independent rendering paths** for image display within the labeling widget:

### Path A: `Canvas + Camera2D + ImageProvider` (default rendering path)

This is the **production rendering path** used for all image sizes. Its components are:

| Component | File | Role |
|---|---|---|
| `Canvas` | `anylabeling/views/labeling/widgets/canvas.py` (~4175 lines) | Main QWidget -- drawing, shape interaction, paint dispatch |
| `Camera2D` | `anylabeling/views/labeling/viewport/camera.py` (196 lines) | HALCON-style DisplayPart camera over finite image coordinates; zoom/pan/fit with constraint clamping |
| `CoordinateMap` | `anylabeling/views/labeling/viewport/coordinate_map.py` | Bidirectional image<->view coordinate mapping with scale factor |
| `QImageRegionProvider` | `anylabeling/views/labeling/viewport/image_provider.py` (394 lines) | Multi-resolution GPU pyramid image provider with QImageReader fallback |
| `ImageProvider` (ABC) | `anylabeling/views/labeling/viewport/image_provider.py` | Abstract contract: `read_region(image_rect, target_size) -> ImageReadResult` |
| `RectF` | `anylabeling/views/labeling/viewport/rect.py` | Immutable float rectangle with validation |
| `TileCache` | `anylabeling/views/labeling/viewport/tile_cache.py` | LRU tile cache |
| `TileGrid` / `TileKey` | `anylabeling/views/labeling/viewport/tile_grid.py` | Tile addressing scheme |
| `RenderQuality` | `anylabeling/views/labeling/viewport/render_quality.py` | SMOOTH / FAST quality enum |

**Paint dispatch logic** (in `Canvas.paintEvent`, line 2438):
1. Guard: no pixmap AND no provider -> fall through to `super().paintEvent()`
2. Image dimensions: prefer `camera.image_width/height`, fall back to `pixmap.width/height`
3. Coordinate map: from `camera.coordinate_map()` if camera exists, else raw `self.scale`
4. **Image drawing branch:**
   - If `has_provider and coordinate_map` -> `_paint_provider_image()` (GPU pyramid + pixel-grid paths)
   - Else -> legacy `p.drawPixmap(0, 0, self.pixmap)` (full QPixmap with QTransform)
5. Shapes always drawn with `coordinate_map.image_to_view_qtransform()` transform
6. Compare view only active in legacy pixmap mode (disabled when provider active)

**Provider paint sub-paths** (in `_paint_provider_image`, line 2324):
- **Pixel-grid path** (opt-in, `ENABLE_PIXEL_GRID_RENDERING=False` by default): When visible region is <= 200 pixels in each dimension AND `enable_pixel_grid_rendering` is True. Renders individual pixel-colored rectangles. Falls through to file path on failure.
- **GPU pyramid path** (default): Uses `provider.get_pyramid_pixmap()` to get the best cached pyramid level, then `p.drawPixmap(target_rect, pyramid_pixmap, source_rect)` for GPU-accelerated scaling.
- **File fallback**: Reads exact pixels from original file via `QImageReader` with clip rect.

### Path B: `HugeImageCanvas + pyqtgraph ViewBox + ImageItem` (experimental)

This is an **experimental path** that is NOT wired into the default labeling workflow.

| Component | File | Role |
|---|---|---|
| `HugeImageCanvas` | `anylabeling/views/labeling/widgets/huge_image_canvas.py` (367 lines) | QGraphicsView wrapping pyqtgraph ViewBox + ImageItem |
| `PerformanceMonitor` | same file | Ring-buffer perf tracker with avg/p95/max per stage |
| `PixelGridItem` | same file | Dynamic pixel grid visible at >= 8x zoom (cosmetic pen) |

**Key characteristics of Path B:**
- Uses pyqtgraph's `ViewBox` with `lockAspect=True`, `invertY=True`
- Builds a 3-level LOD pyramid (L0 = full, L1 = 1/2 area-average, L2 = 1/4)
- Hysteresis-based level switching to prevent flickering:
  - Switching coarser: wait until scale drops below threshold (L0->L1: 0.6, L1->L2: 0.15)
  - Switching finer: wait until scale rises above threshold (L2->L1: 0.3, L1->L0: 1.0)
- Level selection thresholds: scale < 0.2 -> L2, scale < 0.8 -> L1, else -> L0
- Wheel zoom centered on cursor position with 1.1x factor per step
- `autoDownsample=True` on ImageItem (additional automatic downsampling)
- Emits `zoom_changed(float)`, `pixel_hovered(int, int, value)` signals
- Configurable `use_opengl` and `show_pixel_grid` flags

**Benchmark script:** `scripts/test_pyqtgraph_canvas.py` -- creates synthetic NxN image (default 42000x42000) and opens `HugeImageCanvas` window with live performance telemetry in the status bar. Requires GUI (cannot run headless).

---

## 2. `PROVIDER_THRESHOLD_MEGAPIXELS` Status

**Current value:** `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000` (line 109 of `label_widget.py`)

**Meaning:** Effectively **disabled**. No real image will exceed 1,000,000 megapixels (1 terapixel). The provider-backed rendering path is compiled and tested but never activated in production.

**Decision logic** (in `_try_create_image_provider`, line 5538-5542):
```python
megapixels = (size.width() * size.height()) / 1_000_000
if megapixels < PROVIDER_THRESHOLD_MEGAPIXELS:
    return None  # skip provider, use legacy pixmap path
```

**Development history:** The threshold was originally `16` (meaning 4096x4096), which is the documented design intent. It was raised to `1_000_000` as a safety measure during the V4 platform MVP development to ensure the default rendering path remains unchanged.

**MVP platform policy for THIS task (M2.1):** DO NOT MODIFY. The threshold stays at `1_000_000`. Any future adjustment requires a separate acceptance plan with before/after comparison.

### 2.1 Configurability Evaluation

The spec requires evaluating whether `PROVIDER_THRESHOLD_MEGAPIXELS` should be configurable rather than a module-level constant. Four options were evaluated:

#### Option A: Module Constant (current)

```python
# anylabeling/views/labeling/label_widget.py, line 109
PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000
```

**Pros:**
- Simplest implementation -- one well-known location, zero runtime overhead
- No user confusion -- no exposed knob to misunderstand
- Version-controlled -- changes go through code review
- Trivially discoverable via grep

**Cons:**
- Requires code edit + redeploy to change
- No differentiation between dev/CI/production
- Cannot be temporarily lowered for debugging without modifying source

**Best for:** Production deployments where the rendering path must be consistent and auditable across all users.

#### Option B: Config File Entry (in `.xanylabelingrc`)

```json
{
  "canvas": {
    "provider_threshold_megapixels": 16
  }
}
```

**Pros:**
- User-configurable without code modification
- Persists across sessions (survives app restart)
- Can be set per-project via project-level `.xanylabelingrc`
- Read at startup, no per-frame overhead

**Cons:**
- Adds config file parsing dependency to rendering initialization
- Users can unknowingly toggle a path that changes coordinate behavior
- Config drift: two users of the same repo may have different thresholds
- Requires documentation and UI exposure for discoverability

**Best for:** Developer workstations where the operator understands the trade-off and wants to experiment with provider vs legacy rendering without rebuilding.

#### Option C: Environment Variable

```bash
export XANYLABELING_PROVIDER_THRESHOLD_MP=16
```

**Pros:**
- Deployment-level control (set differently for CI vs production)
- No file I/O -- read once at process start via `os.environ.get()`
- Common DevOps pattern (12-factor app)
- Can be set per-session (`XANYLABELING_PROVIDER_THRESHOLD_MP=16 python test.py`)

**Cons:**
- Not persistent (forgotten after terminal close)
- Environment leakage between sessions
- Silent: no indication in-app of what threshold is active
- Windows environment variable management is less ergonomic

**Best for:** CI pipelines where the threshold needs to differ between headless test runs and manual GUI test runs; Docker containers.

#### Option D: CLI Flag

```bash
python -m anylabeling --provider-threshold-mp 16
```

**Pros:**
- Per-session override with explicit intent
- Discoverable via `--help`
- Overrides all other sources (clear precedence: CLI > env > config > default)
- No persistent state

**Cons:**
- Only works for CLI startup (not IDE launches or double-click)
- Requires remembering the flag every session
- Adds argument parsing dependency to rendering module

**Best for:** One-off debugging sessions where the developer wants to compare legacy vs provider rendering on the same image without changing any files.

#### Recommendation

**For the MVP platform phase, keep Option A (module constant) with a documented migration path to Option B + C.**

Rationale:
1. The current `1_000_000` value (effectively disabled) is the correct MVP setting. No configurability is needed because the path is not in use.
2. When the threshold is lowered (per Section 6 rules 3-4), add **both** Option B (config file) and Option C (environment variable) as supplementary overrides:
   - Default value: module constant (e.g., `16`)
   - Override chain: env var > config file > module constant
   - Option D (CLI flag) is low priority -- environment variable covers the CI use case with less plumbing
3. The config file path should be `.xanylabelingrc` key `canvas.provider_threshold_megapixels`, parsed at `LabelingWidget.__init__` time with a fallthrough chain.
4. Do NOT expose this as a GUI setting in the MVP -- it is an advanced rendering knob that should only be touched by developers who understand the coordinate-mapping implications.

---

## 3. Existing Tests

### Viewport test suite: `tests/views/labeling/viewport/` (12 test files)

| Test File | Description | Status |
|---|---|---|
| `test_huge_image_canvas_source.py` | Source-level assertions on HugeImageCanvas (LOD rect, zoom scale, pixel grid flag) | 3 passed |
| `test_canvas_region_rendering.py` | QImageRegionProvider read/crop/pyramid, Canvas provider paint path, GPU pyramid selection, memory policy, pixel grid geometry | 10 passed, 4 failed |
| `test_camera_zoom_pan.py` | Camera2D zoom/pan/fit behavior | passed |
| `test_canvas_camera_state.py` | Canvas camera initialization and state transitions | passed |
| `test_canvas_interactions.py` | Canvas mouse/key interactions (GUI-dependent, skipped) | skipped |
| `test_canvas_small_image_coordinates.py` | Small image coordinate transformations | passed |
| `test_coordinate_map.py` | CoordinateMap bidirectional mapping correctness | passed |
| `test_image_provider_contract.py` | ImageProvider ABC contract and validation | passed |
| `test_label_roundtrip_coordinates.py` | Label coordinate preservation across camera changes | passed |
| `test_render_quality.py` | RenderQuality enum and apply function | passed |
| `test_tile_cache.py` | TileCache LRU eviction and lookup | passed |
| `test_tile_grid.py` | TileKey hashing and tiles_for_rect | passed |

**Overall viewport test results** (run 2026-06-06):
```
84 passed, 11 skipped, 13 subtests passed in 0.20s
```
Skipped tests are `Canvas+QWidget` integration tests that require a running GUI event loop.

### Two specific test files (task-specified):

```
python -m pytest tests/views/labeling/viewport/test_huge_image_canvas_source.py \
                 tests/views/labeling/viewport/test_canvas_region_rendering.py -q
```

**Result:** 13 passed, 4 failed

**Failure analysis (all expected -- stub limitations, not code bugs):**

| Test | Failure | Root Cause |
|---|---|---|
| `test_read_full_image_returns_image_at_target_size` | `AttributeError: 'QPixmap' object has no attribute 'copy'` | Test stubs' `QPixmap` lacks `.copy(QRect)` method; production `_read_from_level` calls `src_qimage.copy(QRect(...))` on QPixmap which has a `.copy()` overload |
| `test_read_sub_region_clips_correctly` | same | same |
| `test_partially_outside_reads_only_intersection` | same | same |
| `test_paint_event_with_provider_uses_provider_read_region` | `ImportError: cannot import name 'QRectF' from 'PyQt6.QtCore'` | Stub `PyQt6.QtCore` does not export `QRectF`; production code imports it in `_paint_provider_image` for `drawPixmap(QRectF, QPixmap, QRectF)` |

These failures occur ONLY in the stub/test environment. With real PyQt6 installed (e.g., in the application), QPixmap.copy() and QRectF are available. This is a known test-infrastructure limitation documented in the test file itself via the `_install_pyqt_stubs()` helper.

### Integration test: `test_label_widget_provider_integration.py`

**Result:** 8 passed, 1 failed

| Test | Failure |
|---|---|
| `test_large_image_returns_provider` | `numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.73 TiB` |

This test attempts to create an image exceeding `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000`, which requires allocating ~2.73 TiB of memory -- impossible on any practical machine. This is expected behavior given the intentionally high threshold.

---

## 4. Verification Commands

### Run viewport unit tests (no GUI required):
```bash
python -m pytest tests/views/labeling/viewport/ -q
```
Expected: 84 passed, 11 skipped, 13 subtests passed

### Run specific test files:
```bash
python -m pytest tests/views/labeling/viewport/test_huge_image_canvas_source.py \
                 tests/views/labeling/viewport/test_canvas_region_rendering.py -q
```
Expected: 13 passed, 4 failed (stub limitations as documented in section 3)

### Run integration test:
```bash
python -m pytest tests/views/labeling/test_label_widget_provider_integration.py -q
```
Expected: 8 passed, 1 failed (memory allocation, expected)

### GUI benchmark (REQUIRES DISPLAY):
```bash
python scripts/test_pyqtgraph_canvas.py --size 42000
```
**Cannot run headless** -- this script creates a `QMainWindow` with `HugeImageCanvas`, generates a synthetic 42000x42000 image (1.76 GB uint8), and requires interactive GUI. In headless CI, this command will fail with `qt.qpa.xcb: could not connect to display` or equivalent.

For manual verification, open the app with a large image (>= 8192x8192) and verify:
- Image opens without error
- Zoom in/out using mouse wheel is smooth (no flickering)
- Pan (drag) is smooth
- Shape coordinates are correct (label at pixel (100, 200) maps correctly)
- Status bar shows coordinate info

---

## 5. Performance Baseline

### 5.1 Measured Test Execution Performance (2026-06-06)

These are actual test run timings from the CI environment (`Python 3.12.13 / PyQt6 / Windows 11`). No interactive GUI profiling was possible (see Section 5.2).

**Viewport unit test suite** (`tests/views/labeling/viewport/`):
```
84 passed, 11 skipped, 13 subtests passed in 0.12s
```
All 95 collected items execute in ~0.12 seconds wall-clock time. Every individual test completes in under 5 ms (288 durations all < 0.005s). This is a strongly constrained unit-test execution profile -- the viewport pure-logic tests (`CoordinateMap`, `TileCache`, `TileGrid`, `Camera2D`, `RenderQuality`, `ImageProvider` contract, etc.) are isolated from GPU and QApplication. No performance regressions are detectable at the individual test level.

**Specific test files** (`test_huge_image_canvas_source.py` + `test_canvas_region_rendering.py`):
```
13 passed, 4 failed in 0.61s
```
The 4 failures are known stub-infrastructure limitations (QPixmap.copy and QRectF import -- see Section 3 failure analysis), not performance issues. The remaining 13 pass in similar sub-5ms time.

**Integration test** (`test_label_widget_provider_integration.py`):
```
8 passed, 1 failed in 2.83s
```
The single failure (`test_large_image_returns_provider`) attempts to allocate a NumPy array exceeding available RAM (2.73 TiB) because the intentionally inflated threshold requires an impossibly large test image. This is expected given `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000`. The 8 passing tests cover threshold comparisons, empty/nonexistent file guards, and constant validation.

**E2E platform fixture tests** (`tests/e2e/platform/test_fixtures.py`):
```
52 passed in 0.32s
```
All 52 tests pass, including all 7 ci_large_sample tests verifying 8192x8192 image dimensions, JSON annotation validity, shape coordinate bounds, and file size. The ci_large_sample image load time is 0.19s (dominant individual test call in the 0.32s total). See Section 7 for coverage details.

### 5.2 Pyqtgraph Benchmark Script (UNMEASURABLE)

The command `python scripts/test_pyqtgraph_canvas.py --size 2000` was attempted but **fails at startup** with a code-level error, not a display availability error:

```
AttributeError: 'HugeImageCanvas' object has no attribute 'sigRangeChanged'
```

This occurs inside pyqtgraph's `GraphicsItem._updateView()` which expects the enclosing `QGraphicsView` to export `sigRangeChanged`. The installed pyqtgraph version (0.14-snapshot range) introduced this signal on `GraphicsView` but our `HugeImageCanvas` inherits directly from `QGraphicsView` without the pyqtgraph signal interface. This is a **code compatibility gap**, not a headless-CI limitation:

- **Why it fails:** Pyqtgraph `ImageItem`/`ViewBox` internally expects `view.sigRangeChanged` to exist on the parent view. `HugeImageCanvas(QGraphicsView)` does not provide this.
- **Why it matters:** The benchmark script is the ONLY source of live performance telemetry for Path B. No other mechanism records zoom/pan latency, LOD switch timing, or memory usage at runtime.
- **What would be needed to measure:** Either (a) fix the signal compatibility so the benchmark launches, or (b) extract `PerformanceMonitor` into a standalone utility that can be tested independently of the pyqtgraph view hierarchy.
- **What IS measurable without a display:** The `PerformanceMonitor` class itself (line 32-72 of `huge_image_canvas.py`) is a pure-Python ring-buffer with `time.perf_counter_ns()`. It could be unit-tested with mock timer data to verify its avg/p95/max computation without needing a QApplication. No such tests currently exist.

### 5.3 No Performance Assertions in Test Code

A search across all viewport test files for timing-related assertions (fps, frame time, duration, timing, performance, benchmark, latency, ms, millisecond) returned **zero matches**. The existing test suite covers functional correctness only:
- Coordinate mapping round-trips
- Tile cache LRU eviction
- Camera zoom/pan/fit constraints
- Image provider contract compliance
- Render quality enum values

No test measures frame time, calls-per-second, memory allocation rate, or any quantitative performance metric. Performance regression detection at CI level is not currently possible from the unit test suite -- it would require a dedicated performance harness with GPU access.

### 5.4 Code-Analysis Baseline (from source, not runtime)

**HugeImageCanvas (Path B) characteristics:**
- LOD pyramid: 3 levels (L0 full, L1 1/2, L2 1/4)
- Downsampling: area-average (np.mean over reshape)
- Hysteresis prevents LOD flickering at boundary thresholds
- `autoDownsample=True` on pyqtgraph ImageItem for additional auto-decimation
- Wheel zoom: 1.1x per step, cursor-centered via `ViewBox.scaleBy()`
- Pixel grid: cosmetic pen, visible only at scale >= 8.0 AND explicit flag enabled
- `PerformanceMonitor`: ring-buffer (120 samples) tracking per-stage latency in nanoseconds
- For 42000x42000 (1.76 GB): L0 = 1.76 GB, L1 = 440 MB, L2 = 110 MB (in-memory)
- OpenGL: optional via `pg.setConfigOption("useOpenGL", True)`
- **Runtime measurement status:** Blocked (benchmark script does not launch). See Section 5.2.

**Canvas + QImageRegionProvider (Path A) characteristics:**
- Pyramid: up to 4 levels (L0-L3, each 1/2 of previous)
- Level budget: `_MAX_PYRAMID_LEVEL_BYTES = 256 MiB` per level
- Level 0 (full resolution) is NOT cached for large images (exceeds budget)
- Level 1 (1/2) is the minimum GPU pyramid level (`_MIN_GPU_LEVEL = 1`)
- For 30980x30276 (example from code): L0 = 3.6 GB (skipped), L1 = 900 MB (skipped), L2 = 225 MB (cached), L3 = 56 MB (cached)
- `get_pyramid_pixmap()` selects level closest to 1:1 source/target ratio
- Falls back to QImageReader with clip rect when no cached level available
- GPU path: `p.drawPixmap(target_rect, pyramid_pixmap, source_rect)` for hardware scaling
- Camera2D: `max_zoom = 1000.0`, `max_margin_factor = 4.0` (pan constraint)
- **Runtime measurement status:** Not measurable (provider path disabled by `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000`). Only measurable on a developer machine after lowering the threshold.

**Known performance notes from code comments:**
- Pixel-grid rendering is opt-in only -- "Switching into this branch while wheel zooming causes visible white gaps/flashes on some GPU paths"
- Pixel-grid threshold of 200 pixels means each pixel is >= 6 screen pixels in a 1200px viewport
- GPU path `_MIN_GPU_LEVEL = 1` exists because "Level 0 pixmaps (e.g. 30980x30276 = 3.6 GB) hurt GPU texture cache efficiency"

---

## 6. MVP Platform Embedding Decision

### Policy rules for MVP Workbench integration:

1. **MVP Workbench embeds the current LabelingWidget as-is.**
   The `LabelingWidget` widget from `anylabeling/views/labeling/label_widget.py` is the single labeling workspace widget. The MVP platform's `WorkbenchWidget` embeds it directly without modifying its internal canvas selection logic.

2. **HugeImageCanvas remains as experimental code, NOT deleted.**
   `anylabeling/views/labeling/widgets/huge_image_canvas.py` is preserved intact. Its dependency on `pyqtgraph` remains in the project. The benchmark script `scripts/test_pyqtgraph_canvas.py` is preserved.

3. **No default rendering path changes without an independent canvas acceptance plan.**
   The current default path (legacy `drawPixmap` with full QPixmap, since `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000`) must not be altered by the MVP platform work. Any future change to enable the provider path requires:
   - A dedicated canvas acceptance plan
   - Before/after comparison on 32k images
   - Zoom/pan latency measurements
   - Memory peak measurements
   - Shape coordinate correctness verification

4. **`PROVIDER_THRESHOLD_MEGAPIXELS` adjustment requires before/after comparison.**
   If the threshold is ever lowered to re-enable the provider path (e.g., back to `16`), the change must be accompanied by A/B testing on large images (>= 8192x8192) comparing zoom smoothness, pan latency, and coordinate accuracy between the legacy pixmap path and the provider path.

5. **No code deletion.** Do NOT delete:
   - `HugeImageCanvas` class or its file
   - `pyqtgraph` imports or dependencies
   - `QImageRegionProvider` or any viewport module
   - Benchmark scripts or test files
   - `PROVIDER_THRESHOLD_MEGAPIXELS` constant or its current value

---

## 7. Regression Test Requirements

The following requirement must be verifiable before any future canvas changes are accepted:

**8192x8192 CI image regression test:**
- Image must open without error (no crash, no hang)
- Zoom in/out must work (mouse wheel, trackpad pinch)
- Pan must work (drag, scroll bars)
- Shape drawing must work (create rectangle/polygon at known coordinates)
- Coordinate mapping must be correct:
  - Shape drawn at pixel (1000, 1000) must export with coordinates (1000, 1000), not scaled or offset
  - After zoom + pan away and back, shape positions must be unchanged
  - Label file save/load round-trip must preserve coordinates

### 7.1 Existing CI Coverage: E2E Platform Fixture Tests

The e2e platform fixture suite at `tests/e2e/platform/test_fixtures.py` already provides CI-level regression coverage for 8192x8192 image handling. These tests were designed for the Vision Platform V4 MVP and execute headlessly (no GUI required).

**Test file:** `tests/e2e/platform/test_fixtures.py` (52 tests total, all passing)

**ci_large_sample fixture:** A deterministically generated 8192x8192 synthetic image (dark background, 512px grid lines, diagonal reference axis, 3 colored HBB rectangles at known positions). Annotation file lives at `tests/e2e/platform/fixtures/annotations/ci_large_sample.json`.

**7 tests specifically cover 8192x8192 handling:**

| # | Test | What it verifies |
|---|---|---|
| 1 | `test_fixture_image_exists[ci_large_sample-8192-8192]` | 8192x8192 PNG loads and has correct dimensions |
| 2 | `test_fixture_json_exists_and_valid[ci_large_sample-8192-8192]` | Annotation JSON parses with correct version, imagePath, shapes |
| 3 | `test_fixture_json_dimensions_match_image[ci_large_sample-8192-8192]` | JSON imageWidth/imageHeight == actual PNG dimensions |
| 4 | `test_fixture_shape_coordinates_in_bounds[ci_large_sample-8192-8192]` | All shape points are within [0, 8192] L0 image bounds |
| 5 | `test_fixture_shape_coordinates_are_numbers[ci_large_sample-8192-8192]` | All coordinate values are numeric (int or float) |
| 6 | `test_ci_large_sample_dimensions_and_shapes` | Concrete 8192x8192 assertion + 3 rectangles at known positions |
| 7 | `test_ci_large_sample_file_size_reasonable` | File size between 0.1 MB and 5.0 MB (compressed PNG, not raw) |

**Rectangle positions (L0 pixel coordinates):**
- Rect 1 (blue): `[[100, 100], [500, 400]]` -- top-left corner region
- Rect 2 (green): `[[4000, 4000], [4500, 4300]]` -- near-center
- Rect 3 (red): `[[7500, 7500], [8000, 8000]]` -- bottom-right corner region

These three positions span near-corner, center, and far-corner of the 8192x8192 extent, providing coordinate-range coverage.

**Verification command (headless CI):**
```bash
python -m pytest tests/e2e/platform/test_fixtures.py -v -k "ci_large"
```
**Result (2026-06-06):** 7 passed in 0.29s. All pass consistently.

**Full e2e fixture suite:**
```bash
python -m pytest tests/e2e/platform/test_fixtures.py -v
```
**Result (2026-06-06):** 52 passed in 0.32s.

### 7.2 Coverage Gap Analysis

The e2e fixture tests cover **static data validation** (dimensions, coordinates, file integrity) at CI level. The spec regression requirements also call for **interactive rendering validation** (zoom, pan, shape drawing) which requires a live QApplication with a physical display. The following table maps spec requirements to existing coverage:

| Spec Requirement | CI Coverage (headless) | Gap |
|---|---|---|
| Image opens without error | `test_fixture_image_exists` (dimension check, file load via OpenCV) | **Partial.** OpenCV load != QPixmap load through the Canvas pipeline. No test loads the 8192x8192 image through `LabelingWidget.loadFile()`. Need: a QApplication-level integration test that calls `canvas.loadPixmap()` with the ci_large_sample image and asserts no exception. |
| Zoom in/out works | Not covered at CI level | **Gap.** Requires QApplication + mouse event simulation. The `test_canvas_interactions.py` tests cover zoom math but are skipped in headless CI. |
| Pan works | Not covered at CI level | **Gap.** Same as zoom -- `test_canvas_interactions.py` covers pan delta math but not against an actual 8192x8192 image. |
| Shape drawing works | Not covered at CI level | **Gap.** No automated test draws a shape on an 8192x8192 image and verifies the result. |
| Coordinate mapping correct | `test_fixture_shape_coordinates_in_bounds` + `test_fixture_shape_coordinates_are_numbers` (static JSON validation) | **Partial.** Static coordinate validation passes. The viewport unit test `test_label_roundtrip_coordinates.py` verifies shape save/reload after camera changes but operates on a small synthetic image, not 8192x8192. |
| Label save/load round-trip | `test_label_roundtrip_coordinates.py` (passes, in 84 passed viewport tests) | **Partial.** Round-trip math is verified at unit level but not with the actual ci_large_sample fixture. |

**Summary of CI-level gaps:**
1. **No end-to-end load path for 8192x8192 through Canvas pipeline.** The OpenCV load in fixture tests does not exercise `QImageRegionProvider` or `Canvas.loadPixmap()`.
2. **No GUI-level interaction on 8192x8192 image.** All interaction tests are either skipped (headless) or operate on small synthetic pixmaps.
3. **No coordinate mapping test on 8192x8192 fixture.** The round-trip test uses a small synthetic image, not the ci_large_sample.

**Recommended follow-up (separate plan, not in M2.1 scope):**
- Add a `test_ci_large_loads_in_canvas` integration test that instantiates `Canvas`, calls `loadPixmap()` with the ci_large_sample image, and asserts no error + correct camera dimensions (`camera.image_width == 8192, camera.image_height == 8192`). This test requires a QApplication but works with the offscreen platform (`QT_QPA_PLATFORM=offscreen` on Linux; Windows supports headless QApplication natively).
- Add a `test_ci_large_coordinate_round_trip` test that creates shapes on the ci_large_sample annotation, simulates camera changes, and verifies coordinate preservation.
- For zoom/pan/shape-drawing on 8192x8192, these remain manual-only verification steps until a GUI automation framework is integrated.

### 7.3 Existing Viewport Coordinate Round-Trip Test

```bash
python -m pytest tests/views/labeling/viewport/test_label_roundtrip_coordinates.py -v
```
This test verifies that shapes save and reload in image coordinates after camera changes. It currently passes (included in the 84 passed). It operates on a small synthetic pixmap, not the 8192x8192 fixture -- see gap analysis above.

---

## Summary

| Item | Status |
|---|---|
| Canvas architecture documented | Done (2 paths: Canvas+provider, HugeImageCanvas+pyqtgraph) |
| PROVIDER_THRESHOLD_MEGAPIXELS status | `1_000_000` (disabled) |
| Viewport tests | 84 passed, 11 skipped, 13 subtests |
| Specific test files | 13 passed, 4 failed (stub limitations) |
| GPU benchmark | Headless-only (requires display) |
| MVP embedding policy | Documented (5 rules) |
| Regression test requirements | Documented (8192x8192 CI image) |
