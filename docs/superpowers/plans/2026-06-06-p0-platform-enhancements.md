# P0 平台增强 — 评估可视化 / 推理可视化 / 多格式导出

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 V4 平台三大 P0 缺陷：评估指标可视化（混淆矩阵、每类 AP、F1 曲线）、推理结果可视化（检测框绘制到图片）、多格式模型导出（补回 15+ 格式）。

**Architecture:** 三个独立子系统，无相互依赖，可并行开发。评估可视化通过 matplotlib FigureCanvasQTAgg 嵌入 PyQt6；推理可视化通过 QPainter 在 QPixmap 上绘制；多格式导出扩展现有 ExportService/ExportAdapter，复用 legacy exporter 的格式验证器。

**Tech Stack:** PyQt6, matplotlib (backend_qtagg), OpenCV (cv2), NumPy, Ultralytics YOLO

**Complexity:** Large (3 subsystems, 16 files changed/created)

---

## Patterns to Mirror

| Category | Source | Pattern |
|----------|--------|---------|
| Workspace UI | `anylabeling/views/platform/evaluate_workspace.py:24-55` | QWidget + QGroupBox + QVBoxLayout, `set_project_context()` API |
| Signal wiring | `anylabeling/views/platform/workbench_window.py:175-200` | `workspace.signal_name.connect(self._on_handler)` in `set_project()` |
| Service init | `anylabeling/views/platform/workbench_window.py:143-148` | `XXXService(job_service, project_path)` then `workspace.set_project_context(training_service=...)` |
| Adapter pattern | `anylabeling/platform/adapters/ultralytics/export_adapter.py:45-83` | `build_xxx_kwargs()` returns dict, no framework imports |
| Worker command | `anylabeling/platform/application/training_service.py:296-327` | Inline Python script via `[sys.executable, "-c", script]` |
| Atomic write | `anylabeling/platform/infrastructure/atomic_writer.py` | `AtomicWriter.write_json(path, data)` tmp→validate→replace |
| i18n | `anylabeling/views/platform/i18n.py` | `tr("中文", "English")` |
| Domain DTO | `anylabeling/platform/domain/run.py:17-37` | `@dataclass` with `from __future__ import annotations` |
| PyQt6 guard | `anylabeling/views/platform/evaluate_workspace.py:112-113` | `except ImportError: ClassName = None` |
| Test fixtures | `tests/platform/views/test_new_project_dialog.py:22-38` | `_make_app()` helper, `pytestmark = pytest.mark.skipif(not _HAS_PYQT, ...)` |

---

## Files to Change

| File | Action | Why |
|------|--------|-----|
| `anylabeling/views/platform/widgets/__init__.py` | CREATE | New widgets package |
| `anylabeling/views/platform/widgets/metrics_plot.py` | CREATE | Reusable matplotlib metrics plot widget |
| `anylabeling/views/platform/evaluate_workspace.py` | MODIFY | Add QTabWidget with metrics table + plots |
| `anylabeling/platform/application/evaluation_service.py` | MODIFY | Post-val parsing: per-class metrics, confusion matrix |
| `anylabeling/platform/adapters/ultralytics/run_parser.py` | MODIFY | Add `parse_val_per_class_metrics()`, `parse_val_confusion_matrix()` |
| `anylabeling/views/platform/widgets/inference_viewer.py` | CREATE | Scrollable image viewer with bbox overlay |
| `anylabeling/views/platform/infer_workspace.py` | MODIFY | Add image viewer tab, render detection results |
| `anylabeling/views/platform/workbench_window.py` | MODIFY | Wire post-eval metrics display, post-infer result rendering |
| `anylabeling/platform/adapters/ultralytics/export_validators.py` | CREATE | Format environment validators (ported from legacy) |
| `anylabeling/platform/adapters/ultralytics/export_adapter.py` | MODIFY | Accept `format` parameter, multi-format export kwargs |
| `anylabeling/platform/application/export_service.py` | MODIFY | Multi-format support, env validation in worker |
| `anylabeling/views/platform/export_workspace.py` | MODIFY | Format selector combo, format-specific options |
| `tests/platform/adapters/ultralytics/test_run_parser_val.py` | CREATE | Tests for val result parsing |
| `tests/platform/views/test_metrics_plot.py` | CREATE | Tests for metrics plot widget |
| `tests/platform/views/test_evaluate_workspace.py` | CREATE | Tests for new evaluate workspace features |
| `tests/platform/views/test_inference_viewer.py` | CREATE | Tests for inference viewer widget |
| `tests/platform/views/test_export_workspace.py` | CREATE | Tests for multi-format export UI |
| `tests/platform/adapters/ultralytics/test_export_validators.py` | CREATE | Tests for format validators |

---

## Task 1: RunParser 增加 val 输出解析方法

**Files:**
- Modify: `anylabeling/platform/adapters/ultralytics/run_parser.py`
- Create: `tests/platform/adapters/ultralytics/test_run_parser_val.py`

### Step 1: Write the failing test

```python
# tests/platform/adapters/ultralytics/test_run_parser_val.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from anylabeling.platform.adapters.ultralytics.run_parser import UltralyticsRunParser


class TestParseValPerClassMetrics:
    def test_parses_valid_json(self):
        parser = UltralyticsRunParser()
        data = {
            "ap_per_class": {"0": 0.852, "1": 0.731, "2": 0.943},
            "class_names": ["cat", "dog", "bird"],
            "mAP50": 0.842,
            "mAP50_95": 0.651,
            "precision": 0.88,
            "recall": 0.79,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "per_class_metrics.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = parser.parse_val_per_class_metrics(str(path))
            assert result is not None
            assert result["mAP50"] == 0.842
            assert result["ap_per_class"]["0"] == 0.852
            assert len(result["class_names"]) == 3

    def test_returns_none_for_missing_file(self):
        parser = UltralyticsRunParser()
        result = parser.parse_val_per_class_metrics("/nonexistent/path.json")
        assert result is None

    def test_returns_none_for_invalid_json(self):
        parser = UltralyticsRunParser()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            result = parser.parse_val_per_class_metrics(str(path))
            assert result is None


class TestParseValConfusionMatrix:
    def test_loads_npy_file(self):
        parser = UltralyticsRunParser()
        matrix = np.array([[45, 2, 1], [3, 38, 0], [0, 1, 50]], dtype=np.int32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "confusion_matrix.npy"
            np.save(str(path), matrix)
            result = parser.parse_val_confusion_matrix(str(path))
            assert result is not None
            assert result.shape == (3, 3)
            assert result[0, 0] == 45

    def test_returns_none_for_missing_file(self):
        parser = UltralyticsRunParser()
        result = parser.parse_val_confusion_matrix("/nonexistent/path.npy")
        assert result is None
```

### Step 2: Run test to verify it fails

```bash
pytest tests/platform/adapters/ultralytics/test_run_parser_val.py -v
```
Expected: FAIL — `AttributeError: 'UltralyticsRunParser' object has no attribute 'parse_val_per_class_metrics'`

### Step 3: Implement the methods

In `anylabeling/platform/adapters/ultralytics/run_parser.py`, add these two methods to `UltralyticsRunParser`:

```python
    # ------------------------------------------------------------------
    # val output parsing
    # ------------------------------------------------------------------

    def parse_val_per_class_metrics(
        self,
        metrics_path: str | Path,
    ) -> dict | None:
        """Parse per-class metrics JSON saved by the val worker.

        Expected JSON structure::

            {
                "ap_per_class": {"0": 0.852, "1": 0.731, ...},
                "class_names": ["cat", "dog", ...],
                "mAP50": 0.842,
                "mAP50_95": 0.651,
                "precision": 0.88,
                "recall": 0.79,
            }

        Returns:
            Dict or None if file missing or invalid.
        """
        import json

        path = Path(metrics_path)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "ap_per_class" not in data and "mAP50_95" not in data:
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def parse_val_confusion_matrix(
        self,
        matrix_path: str | Path,
    ):
        """Load a confusion matrix from a .npy file saved by the val worker.

        Returns:
            numpy.ndarray or None if file missing or invalid.
        """
        import numpy as np

        path = Path(matrix_path)
        if not path.exists():
            return None

        try:
            matrix = np.load(str(path))
            if not isinstance(matrix, np.ndarray) or matrix.ndim != 2:
                return None
            return matrix
        except (ValueError, OSError):
            return None
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/platform/adapters/ultralytics/test_run_parser_val.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add anylabeling/platform/adapters/ultralytics/run_parser.py tests/platform/adapters/ultralytics/test_run_parser_val.py
git commit -m "feat: add val output parsing to UltralyticsRunParser (per-class metrics + confusion matrix)"
```

---

## Task 2: 修改 val worker 保存详细评估结果

**Files:**
- Modify: `anylabeling/platform/application/evaluation_service.py`

### Step 1: Replace `_build_val_command` to save per-class metrics and confusion matrix

Replace the existing `_build_val_command` static method (lines 150-182) with:

```python
    @staticmethod
    def _build_val_command(
        model_path: str,
        kwargs: dict,
    ) -> list[str]:
        """Build the subprocess command list for YOLO validation.

        The worker script runs ``model.val(**kwargs)`` and saves:
        - ``per_class_metrics.json`` — AP per class, mAP, precision, recall
        - ``confusion_matrix.npy`` — raw confusion matrix as numpy array
        """
        import json

        kwargs_json = json.dumps(kwargs, ensure_ascii=False)

        script = (
            "import json, sys, os\n"
            "import numpy as np\n"
            "from ultralytics import YOLO\n"
            f"kwargs = json.loads({json.dumps(kwargs_json)})\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            "results = model.val(**kwargs)\n"
            "# --- save per-class metrics ---\n"
            "per_class = {}\n"
            "try:\n"
            "    if hasattr(results, 'box') and results.box is not None:\n"
            "        box = results.box\n"
            "        per_class['mAP50'] = float(getattr(box, 'map50', 0))\n"
            "        per_class['mAP50_95'] = float(getattr(box, 'map', 0))\n"
            "        rd = getattr(results, 'results_dict', {})\n"
            "        per_class['precision'] = float(rd.get('metrics/precision(B)', 0))\n"
            "        per_class['recall'] = float(rd.get('metrics/recall(B)', 0))\n"
            "        ap_dict = {}\n"
            "        if hasattr(box, 'ap') and box.ap is not None:\n"
            "            ap_flat = box.ap.flatten().tolist() if hasattr(box.ap, 'flatten') else [float(x) for x in box.ap]\n"
            "            for i, ap_val in enumerate(ap_flat):\n"
            "                ap_dict[str(i)] = float(ap_val)\n"
            "        per_class['ap_per_class'] = ap_dict\n"
            "        if hasattr(model, 'names') and model.names:\n"
            "            per_class['class_names'] = [str(model.names.get(i, f'class_{i}')) for i in range(len(model.names))]\n"
            "        else:\n"
            "            per_class['class_names'] = [f'class_{i}' for i in range(len(ap_dict))]\n"
            "except Exception as e:\n"
            "    per_class['error'] = str(e)\n"
            "# --- save confusion matrix ---\n"
            "try:\n"
            "    if hasattr(results, 'confusion_matrix') and results.confusion_matrix is not None:\n"
            "        cm = results.confusion_matrix\n"
            "        if hasattr(cm, 'matrix'):\n"
            "            out_dir = os.path.join(kwargs.get('project', '.'), kwargs.get('name', 'val'))\n"
            "            os.makedirs(out_dir, exist_ok=True)\n"
            "            np.save(os.path.join(out_dir, 'confusion_matrix.npy'), cm.matrix)\n"
            "except Exception:\n"
            "    pass\n"
            "# --- write per_class_metrics.json ---\n"
            "out_dir = os.path.join(kwargs.get('project', '.'), kwargs.get('name', 'val'))\n"
            "os.makedirs(out_dir, exist_ok=True)\n"
            "with open(os.path.join(out_dir, 'per_class_metrics.json'), 'w', encoding='utf-8') as f:\n"
            "    json.dump(per_class, f, ensure_ascii=False)\n"
            "print(json.dumps({'status': 'ok', 'output_dir': out_dir}, ensure_ascii=False))\n"
        )

        return [sys.executable, "-c", script]
```

### Step 2: Add `parse_val_results` method to EvaluationService

Add this method after `evaluate_tile_native` (after line 122):

```python
    def parse_val_results(
        self,
        run: Run,
        build: DatasetBuild,
    ) -> dict | None:
        """Parse validation results after a val job completes.

        Reads ``per_class_metrics.json`` and ``confusion_matrix.npy`` from
        the val output directory and returns a combined dict.

        Returns:
            Dict with keys: ``mAP50``, ``mAP50_95``, ``precision``,
            ``recall``, ``ap_per_class``, ``class_names``,
            ``confusion_matrix`` (numpy array or None), or None if no files found.
        """
        from anylabeling.platform.adapters.ultralytics.run_parser import (
            UltralyticsRunParser,
        )

        if not run.output_dir:
            return None

        val_dir = Path(run.output_dir) / "val"
        parser = UltralyticsRunParser()

        metrics = parser.parse_val_per_class_metrics(
            str(val_dir / "per_class_metrics.json")
        )
        confusion_matrix = parser.parse_val_confusion_matrix(
            str(val_dir / "confusion_matrix.npy")
        )

        if metrics is None and confusion_matrix is None:
            return None

        result: dict = metrics or {}
        result["confusion_matrix"] = confusion_matrix
        return result
```

### Step 3: Commit

```bash
git add anylabeling/platform/application/evaluation_service.py
git commit -m "feat: enhance val worker to save per-class metrics and confusion matrix"
```

---

## Task 3: 创建 MetricsPlotWidget (matplotlib 嵌入)

**Files:**
- Create: `anylabeling/views/platform/widgets/__init__.py`
- Create: `anylabeling/views/platform/widgets/metrics_plot.py`
- Create: `tests/platform/views/test_metrics_plot.py`

### Step 1: Create widgets package init

```python
# anylabeling/views/platform/widgets/__init__.py
"""Reusable widgets for the V4 platform workbench."""
```

### Step 2: Write tests for MetricsPlotWidget

```python
# tests/platform/views/test_metrics_plot.py
from __future__ import annotations

import sys

import pytest

try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class TestMetricsPlotWidget:
    def test_creates_with_default_state(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        assert widget is not None
        widget.close()

    def test_plot_confusion_matrix_no_error(self):
        import numpy as np
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        matrix = np.array([[45, 2, 1], [3, 38, 0], [0, 1, 50]], dtype=np.int32)
        widget.plot_confusion_matrix(matrix, ["cat", "dog", "bird"])
        widget.close()

    def test_plot_per_class_ap_no_error(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        widget.plot_per_class_ap({"0": 0.852, "1": 0.731, "2": 0.943}, ["cat", "dog", "bird"])
        widget.close()

    def test_empty_data_shows_placeholder(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        widget.plot_confusion_matrix(None, [])
        widget.plot_per_class_ap({}, [])
        widget.plot_f1_curve({}, [])
        widget.close()

    def test_clear_all_resets(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        widget.clear_all()
        widget.close()
```

### Step 3: Run test to verify it fails

```bash
pytest tests/platform/views/test_metrics_plot.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'anylabeling.views.platform.widgets.metrics_plot'`

### Step 4: Implement MetricsPlotWidget

```python
# anylabeling/views/platform/widgets/metrics_plot.py
"""Matplotlib-based metrics visualization widget for the platform workbench.

Provides three tabbed plots:
    - Confusion matrix (heatmap)
    - Per-class AP (horizontal bar chart)
    - F1/Summary table
"""

from __future__ import annotations

import numpy as np

from anylabeling.views.platform.i18n import tr

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
    from PyQt6.QtCore import Qt

    class MetricsPlotWidget(QWidget):
        """Tabbed widget for evaluation metrics visualization."""

        def __init__(self, parent=None):
            super().__init__(parent)

            self._tab_widget = QTabWidget()

            # Tab 0: Confusion Matrix
            self._cm_canvas = FigureCanvasQTAgg(Figure(figsize=(5, 4.5), dpi=100))
            self._cm_canvas.figure.set_tight_layout(True)
            self._tab_widget.addTab(self._cm_canvas, tr("混淆矩阵", "Confusion Matrix"))

            # Tab 1: Per-Class AP
            self._ap_canvas = FigureCanvasQTAgg(Figure(figsize=(5, 4.5), dpi=100))
            self._ap_canvas.figure.set_tight_layout(True)
            self._tab_widget.addTab(self._ap_canvas, tr("每类 AP", "Per-Class AP"))

            # Tab 2: Summary
            self._f1_canvas = FigureCanvasQTAgg(Figure(figsize=(5, 4.5), dpi=100))
            self._f1_canvas.figure.set_tight_layout(True)
            self._tab_widget.addTab(self._f1_canvas, tr("指标摘要", "Summary"))

            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._tab_widget)
            self.setLayout(layout)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def plot_confusion_matrix(
            self,
            matrix: np.ndarray | None,
            class_names: list[str],
        ) -> None:
            """Plot a confusion matrix heatmap."""
            ax = self._cm_canvas.figure.gca()
            ax.clear()

            if matrix is None or matrix.size == 0 or len(class_names) == 0:
                ax.text(0.5, 0.5, tr("无数据", "No Data"),
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=14, color="gray")
                self._cm_canvas.draw()
                return

            im = ax.imshow(matrix, cmap="Blues", aspect="auto")
            n_classes = matrix.shape[0]
            for i in range(n_classes):
                for j in range(n_classes):
                    val = matrix[i, j]
                    text_color = "white" if val > matrix.max() / 2 else "black"
                    ax.text(j, i, str(int(val)), ha="center", va="center",
                            color=text_color, fontsize=8)

            ax.set_xticks(range(n_classes))
            ax.set_yticks(range(n_classes))
            ax.set_xticklabels(class_names, rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels(class_names, fontsize=8)
            ax.set_xlabel(tr("预测类别", "Predicted"), fontsize=10)
            ax.set_ylabel(tr("真实类别", "True"), fontsize=10)
            ax.set_title(tr("混淆矩阵", "Confusion Matrix"), fontsize=12)
            self._cm_canvas.figure.colorbar(im, ax=ax, shrink=0.8)
            self._cm_canvas.draw()

        def plot_per_class_ap(
            self,
            ap_per_class: dict[str, float],
            class_names: list[str],
        ) -> None:
            """Plot per-class AP as a horizontal bar chart."""
            ax = self._ap_canvas.figure.gca()
            ax.clear()

            if not ap_per_class:
                ax.text(0.5, 0.5, tr("无数据", "No Data"),
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=14, color="gray")
                self._ap_canvas.draw()
                return

            items = sorted(ap_per_class.items(), key=lambda x: x[1], reverse=True)
            names = []
            values = []
            for idx_str, ap_val in items:
                idx = int(idx_str)
                name = class_names[idx] if idx < len(class_names) else f"class_{idx}"
                names.append(name)
                values.append(ap_val)

            y_pos = range(len(names))
            colors = ["#1890ff" if v >= 0.7 else "#faad14" if v >= 0.5 else "#ff4d4f"
                      for v in values]
            bars = ax.barh(y_pos, values, color=colors, edgecolor="white")
            for bar, val in zip(bars, values):
                ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                        f"{val:.3f}", va="center", fontsize=9)

            ax.set_yticks(y_pos)
            ax.set_yticklabels(names, fontsize=9)
            ax.invert_yaxis()
            ax.set_xlabel("AP", fontsize=10)
            ax.set_title(tr("每类平均精度 (AP)", "Per-Class Average Precision"), fontsize=12)
            ax.set_xlim(0, max(values) * 1.15 if values else 1.0)
            self._ap_canvas.draw()

        def plot_f1_curve(
            self,
            ap_per_class: dict[str, float],
            class_names: list[str],
        ) -> None:
            """Display a metrics summary table."""
            ax = self._f1_canvas.figure.gca()
            ax.clear()
            ax.axis("off")

            if not ap_per_class:
                ax.text(0.5, 0.5, tr("无数据", "No Data"),
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=14, color="gray")
                self._f1_canvas.draw()
                return

            lines = [tr("指标摘要", "Metrics Summary"), "=" * 40]
            for idx_str, ap_val in sorted(ap_per_class.items(), key=lambda x: x[1], reverse=True):
                idx = int(idx_str)
                name = class_names[idx] if idx < len(class_names) else f"class_{idx}"
                lines.append(f"  {name:<20s}  AP: {ap_val:.3f}")

            text = "\n".join(lines)
            ax.text(0.5, 0.5, text, ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, fontfamily="monospace")
            self._f1_canvas.draw()

        def clear_all(self) -> None:
            """Clear all plots."""
            for canvas in [self._cm_canvas, self._ap_canvas, self._f1_canvas]:
                canvas.figure.gca().clear()
                canvas.draw()

except ImportError:
    MetricsPlotWidget = None  # type: ignore
```

### Step 5: Run tests to verify they pass

```bash
pytest tests/platform/views/test_metrics_plot.py -v
```
Expected: PASS

### Step 6: Commit

```bash
git add anylabeling/views/platform/widgets/__init__.py anylabeling/views/platform/widgets/metrics_plot.py tests/platform/views/test_metrics_plot.py
git commit -m "feat: add MetricsPlotWidget for confusion matrix, per-class AP, and summary"
```

---

## Task 4: 改造 EvaluateWorkspace UI 集成图表

**Files:**
- Modify: `anylabeling/views/platform/evaluate_workspace.py`
- Create: `tests/platform/views/test_evaluate_workspace.py`

### Step 1: Write tests

```python
# tests/platform/views/test_evaluate_workspace.py
from __future__ import annotations

import sys

import pytest

try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class TestEvaluateWorkspaceWithPlots:
    def test_has_tab_widget_after_init(self):
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        app = _make_app()
        widget = EvaluateWorkspace()
        tab = widget.findChild(QtWidgets.QTabWidget)
        assert tab is not None, "Should have a QTabWidget for metrics display"
        widget.close()

    def test_display_metrics_populates_tabs(self):
        import numpy as np
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        app = _make_app()
        widget = EvaluateWorkspace()
        metrics = {
            "mAP50": 0.842,
            "mAP50_95": 0.651,
            "ap_per_class": {"0": 0.85, "1": 0.73},
            "class_names": ["cat", "dog"],
            "confusion_matrix": np.array([[10, 1], [2, 9]], dtype=np.int32),
        }
        widget.display_metrics(metrics)  # should not raise
        widget.close()

    def test_clear_metrics_resets_display(self):
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        app = _make_app()
        widget = EvaluateWorkspace()
        widget.clear_metrics()  # should not raise
        widget.close()
```

### Step 2: Run test to verify it fails

```bash
pytest tests/platform/views/test_evaluate_workspace.py -v
```
Expected: FAIL — no `QTabWidget` exists in the old layout

### Step 3: Rewrite EvaluateWorkspace

```python
# anylabeling/views/platform/evaluate_workspace.py (full replacement)
"""Evaluate Workspace -- run selection, evaluation trigger, metrics visualization."""

from __future__ import annotations

from pathlib import Path

from anylabeling.views.platform.i18n import tr


try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QComboBox, QPushButton, QTextEdit, QLabel, QTabWidget,
    )
    from PyQt6.QtCore import pyqtSignal

    from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget

    class EvaluateWorkspace(QWidget):
        evaluate_requested = pyqtSignal(str, str)

        def __init__(self, parent=None):
            super().__init__(parent)

            # --- Run selection ---
            run_group = QGroupBox(tr("运行选择", "Run Selection"))
            run_layout = QHBoxLayout()
            run_layout.addWidget(QLabel(tr("运行：", "Run:")))
            self._run_combo = QComboBox()
            run_layout.addWidget(self._run_combo, 1)
            run_group.setLayout(run_layout)

            # --- Buttons ---
            btn_layout = QHBoxLayout()
            self._evaluate_btn = QPushButton(tr("开始评估", "Start Evaluation"))
            self._evaluate_btn.setEnabled(False)
            self._evaluate_btn.clicked.connect(self._on_evaluate_clicked)
            btn_layout.addWidget(self._evaluate_btn)
            btn_layout.addStretch()

            # --- Display: tab widget with text summary + charts ---
            self._display_tabs = QTabWidget()

            self._summary_text = QTextEdit()
            self._summary_text.setReadOnly(True)
            self._display_tabs.addTab(self._summary_text, tr("摘要", "Summary"))

            self._metrics_plot = MetricsPlotWidget()
            self._display_tabs.addTab(self._metrics_plot, tr("图表", "Charts"))

            main = QVBoxLayout()
            main.addWidget(run_group)
            main.addLayout(btn_layout)
            main.addWidget(self._display_tabs, stretch=1)
            self.setLayout(main)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def set_project_context(self, training_service=None):
            self._training_service = training_service
            self._populate_runs()

        def display_metrics(self, metrics: dict) -> None:
            """Display parsed evaluation metrics."""
            lines = [
                f"mAP@50:      {metrics.get('mAP50', 'N/A')}",
                f"mAP@50-95:   {metrics.get('mAP50_95', 'N/A')}",
                f"Precision:   {metrics.get('precision', 'N/A')}",
                f"Recall:      {metrics.get('recall', 'N/A')}",
            ]
            self._summary_text.setPlainText("\n".join(lines))

            ap_per_class = metrics.get("ap_per_class", {})
            class_names = metrics.get("class_names", [])
            confusion_matrix = metrics.get("confusion_matrix")

            if confusion_matrix is not None and len(class_names) > 0:
                self._metrics_plot.plot_confusion_matrix(confusion_matrix, class_names)
            if ap_per_class:
                self._metrics_plot.plot_per_class_ap(ap_per_class, class_names)
                self._metrics_plot.plot_f1_curve(ap_per_class, class_names)

        def clear_metrics(self) -> None:
            self._summary_text.clear()
            self._metrics_plot.clear_all()

        # ------------------------------------------------------------------
        # Internal
        # ------------------------------------------------------------------

        def _populate_runs(self):
            self._run_combo.clear()
            training_service = getattr(self, "_training_service", None)
            if training_service is None:
                self._evaluate_btn.setEnabled(False)
                self._evaluate_btn.setText(tr("评估（无训练服务）", "Evaluate (no training service)"))
                return

            runs_dir = Path(training_service.project_root) / "runs"
            if not runs_dir.exists():
                self._evaluate_btn.setEnabled(False)
                return

            run_count = 0
            for run_dir in sorted(runs_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                run_json = run_dir / "run.json"
                if not run_json.exists():
                    continue
                try:
                    run = training_service.read_run_record(run_dir.name)
                    if run is not None:
                        label = f"{run.id} ({run.task_family}) [{run.status}]"
                        self._run_combo.addItem(label, run.id)
                        run_count += 1
                except Exception:
                    continue

            self._evaluate_btn.setEnabled(run_count > 0)
            if run_count == 0:
                self._evaluate_btn.setText(tr("评估（无可用运行）", "Evaluate (no runs available)"))

        def _on_evaluate_clicked(self):
            run_id = self._run_combo.currentData()
            if run_id:
                self.clear_metrics()
                self._summary_text.setPlainText(tr("评估中...", "Evaluating..."))
                self.evaluate_requested.emit(run_id, "val")

except ImportError:
    EvaluateWorkspace = None  # type: ignore
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/platform/views/test_evaluate_workspace.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add anylabeling/views/platform/evaluate_workspace.py tests/platform/views/test_evaluate_workspace.py
git commit -m "feat: add metrics visualization tabs (summary + charts) to EvaluateWorkspace"
```

---

## Task 5: WorkbenchWindow 接线 post-eval 指标显示

**Files:**
- Modify: `anylabeling/views/platform/workbench_window.py`

### Step 1: Add polling-based post-eval metrics display

Modify `_on_evaluate_requested` in `WorkbenchWindow` to poll for job completion and display metrics.

After the existing job creation code in `_on_evaluate_requested` (after line 618), replace the return/end of the try block with:

```python
            # --- after job creation, start polling for completion ---
            self._pending_eval = {
                "job_id": job_id,
                "run": run,
                "build": matching_build,
                "service": service,
            }
            if not hasattr(self, "_eval_poll_timer"):
                from PyQt6.QtCore import QTimer
                self._eval_poll_timer = QTimer(self)
                self._eval_poll_timer.timeout.connect(self._poll_eval_completion)
            self._eval_poll_timer.start(2000)
```

Add a new method `_poll_eval_completion` to `WorkbenchWindow`:

```python
    def _poll_eval_completion(self) -> None:
        """Poll for evaluation job completion and display metrics."""
        pending = getattr(self, "_pending_eval", None)
        if pending is None:
            if hasattr(self, "_eval_poll_timer"):
                self._eval_poll_timer.stop()
            return

        from anylabeling.platform.workers.protocol import JobState
        state = self._job_service.get_job_state(pending["job_id"])

        terminal_states = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
        if state not in terminal_states:
            return

        if hasattr(self, "_eval_poll_timer"):
            self._eval_poll_timer.stop()

        if state == JobState.COMPLETED:
            try:
                metrics = pending["service"].parse_val_results(
                    pending["run"], pending["build"]
                )
                if metrics:
                    self._evaluate_workspace.display_metrics(metrics)
                    self._status_bar.showMessage(tr("评估完成", "Evaluation complete"))
                else:
                    self._evaluate_workspace.display_metrics(
                        {"error": "No metrics found in val output"}
                    )
            except Exception as exc:
                logger.exception("Failed to parse val results")
                self._evaluate_workspace.display_metrics({"error": str(exc)})
        else:
            self._evaluate_workspace.display_metrics(
                {"error": f"Evaluation job ended with state: {state.value}"}
            )

        self._pending_eval = None
```

### Step 2: Commit

```bash
git add anylabeling/views/platform/workbench_window.py
git commit -m "feat: wire post-evaluation metrics polling and display in WorkbenchWindow"
```

---

## Task 6: 创建 InferenceViewerWidget (推理结果可视化)

**Files:**
- Create: `anylabeling/views/platform/widgets/inference_viewer.py`
- Create: `tests/platform/views/test_inference_viewer.py`

### Step 1: Write tests

```python
# tests/platform/views/test_inference_viewer.py
from __future__ import annotations

import os
import sys
import tempfile

import pytest

try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


def _create_test_image() -> str:
    import numpy as np
    import cv2
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[20:40, 20:40] = [255, 0, 0]
    tdir = tempfile.mkdtemp()
    path = os.path.join(tdir, "test.png")
    cv2.imwrite(path, img)
    return path


class TestInferenceViewerWidget:
    def test_creates_with_placeholder(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        assert widget is not None
        widget.close()

    def test_load_image_no_error(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        img_path = _create_test_image()
        widget.load_image(img_path)
        widget.close()

    def test_draw_detections_no_error(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        img_path = _create_test_image()
        widget.load_image(img_path)
        detections = [
            {"bbox": [10.0, 10.0, 50.0, 50.0], "class": 0, "conf": 0.95},
            {"bbox": [40.0, 40.0, 90.0, 90.0], "class": 1, "conf": 0.72},
        ]
        widget.draw_detections(detections, ["cat", "dog"])
        widget.close()

    def test_clear_resets(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        widget.clear()
        widget.close()
```

### Step 2: Run test to verify it fails

```bash
pytest tests/platform/views/test_inference_viewer.py -v
```
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Implement InferenceViewerWidget

```python
# anylabeling/views/platform/widgets/inference_viewer.py
"""Scrollable image viewer with detection bounding-box overlay.

Supports zoom (mouse wheel), pan (click-drag), and bbox rendering via QPainter.
"""

from __future__ import annotations

from pathlib import Path

from anylabeling.views.platform.i18n import tr

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    )
    from PyQt6.QtGui import (
        QPixmap, QPainter, QPen, QColor, QFont, QImage, QWheelEvent, QMouseEvent,
    )
    from PyQt6.QtCore import Qt, QPoint

    _BBOX_COLORS = [
        QColor("#FF4444"), QColor("#44FF44"), QColor("#4488FF"),
        QColor("#FFAA00"), QColor("#FF44FF"), QColor("#44FFFF"),
        QColor("#FF8888"), QColor("#88FF88"), QColor("#8888FF"),
        QColor("#CCCC00"),
    ]


    class _ZoomableLabel(QLabel):
        """QLabel with mouse-wheel zoom and click-drag pan."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._zoom = 1.0
            self._base_pixmap: QPixmap | None = None
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setMinimumSize(200, 200)
            self.setStyleSheet("background-color: #f0f0f0;")

        def set_base_pixmap(self, pixmap: QPixmap) -> None:
            self._base_pixmap = pixmap
            self._zoom = 1.0
            self._redraw()

        def _redraw(self) -> None:
            if self._base_pixmap is None or self._base_pixmap.isNull():
                return
            w = max(1, int(self._base_pixmap.width() * self._zoom))
            h = max(1, int(self._base_pixmap.height() * self._zoom))
            scaled = self._base_pixmap.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)

        def wheelEvent(self, event: QWheelEvent) -> None:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self._zoom = max(0.1, min(10.0, self._zoom * factor))
            self._redraw()


    class InferenceViewerWidget(QWidget):
        """Image viewer with detection bounding-box overlay."""

        def __init__(self, parent=None):
            super().__init__(parent)

            self._image_label = _ZoomableLabel()

            self._scroll_area = QScrollArea()
            self._scroll_area.setWidgetResizable(True)
            self._scroll_area.setWidget(self._image_label)
            self._scroll_area.setStyleSheet("QScrollArea { border: 1px solid #e8e8e8; }")

            self._status_label = QLabel(tr("选择图片开始推理", "Select an image to start inference"))
            self._status_label.setStyleSheet("color: #8c8c8c; font-size: 12px;")

            self._reset_zoom_btn = QPushButton(tr("重置缩放", "Reset Zoom"))
            self._reset_zoom_btn.clicked.connect(
                lambda: self._image_label.set_base_pixmap(self._image_label._base_pixmap)
                if self._image_label._base_pixmap else None
            )

            toolbar = QHBoxLayout()
            toolbar.addWidget(self._status_label, stretch=1)
            toolbar.addWidget(self._reset_zoom_btn)

            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addLayout(toolbar)
            layout.addWidget(self._scroll_area, stretch=1)
            self.setLayout(layout)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def load_image(self, image_path: str) -> None:
            """Load and display an image."""
            import cv2

            img = cv2.imread(image_path)
            if img is None:
                self._status_label.setText(tr(f"无法加载图片：{image_path}", f"Cannot load: {image_path}"))
                return

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            bytes_per_line = ch * w
            qimage = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage.copy())

            self._image_label.set_base_pixmap(pixmap)
            self._status_label.setText(
                tr(f"图片: {Path(image_path).name} ({w}×{h})",
                   f"Image: {Path(image_path).name} ({w}x{h})")
            )

        def draw_detections(
            self,
            detections: list[dict],
            class_names: list[str],
        ) -> None:
            """Draw bounding boxes on the current image."""
            if self._image_label._base_pixmap is None:
                return

            base = self._image_label._base_pixmap
            pixmap = base.copy()
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            img_w = base.width()
            img_h = base.height()

            for det in detections:
                bbox = det["bbox"]
                cls_id = det.get("class", 0)
                conf = det.get("conf", 0.0)
                color = _BBOX_COLORS[cls_id % len(_BBOX_COLORS)]

                x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
                x1, y1 = max(0, min(x1, img_w)), max(0, min(y1, img_h))
                x2, y2 = max(0, min(x2, img_w)), max(0, min(y2, img_h))

                pen_width = max(2, int(img_w / 400))
                painter.setPen(QPen(color, pen_width))
                from PyQt6.QtCore import QRectF
                painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

                label = class_names[cls_id] if cls_id < len(class_names) else f"cls_{cls_id}"
                text = f"{label} {conf:.2f}"

                font = QFont("Segoe UI", max(9, int(img_w / 120)))
                font.setBold(True)
                painter.setFont(font)

                fm = painter.fontMetrics()
                text_rect = fm.boundingRect(text)
                text_w = text_rect.width() + 6
                text_h = text_rect.height() + 4

                label_y = y1 - text_h - 2
                if label_y < 0:
                    label_y = y1 + 2

                painter.fillRect(QRectF(x1, label_y, text_w, text_h), color)
                painter.setPen(QPen(QColor("white")))
                painter.drawText(
                    QRectF(x1 + 3, label_y, text_w, text_h),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )

            painter.end()
            self._image_label.set_base_pixmap(pixmap)
            self._status_label.setText(
                tr(f"检测到 {len(detections)} 个目标",
                   f"{len(detections)} object(s) detected")
            )

        def clear(self) -> None:
            self._status_label.setText(tr("选择图片开始推理", "Select an image to start inference"))

except ImportError:
    InferenceViewerWidget = None  # type: ignore
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/platform/views/test_inference_viewer.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add anylabeling/views/platform/widgets/inference_viewer.py tests/platform/views/test_inference_viewer.py
git commit -m "feat: add InferenceViewerWidget with zoom and bbox overlay rendering"
```

---

## Task 7: 改造 InferWorkspace UI 集成推理可视化

**Files:**
- Modify: `anylabeling/views/platform/infer_workspace.py`

### Step 1: Rewrite InferWorkspace with split-panel layout

Replace the existing `InferWorkspace` class (lines 18-150) with:

```python
    class InferWorkspace(QWidget):
        infer_requested = pyqtSignal(dict)

        def __init__(self, parent=None):
            super().__init__(parent)

            # --- Left panel: controls ---
            left = QWidget()
            left_layout = QVBoxLayout()
            left_layout.setContentsMargins(0, 0, 0, 0)

            # Run selection
            run_group = QGroupBox(tr("模型选择", "Model Selection"))
            rl = QHBoxLayout()
            rl.addWidget(QLabel(tr("运行：", "Run:")))
            self._run_combo = QComboBox()
            rl.addWidget(self._run_combo, 1)
            run_group.setLayout(rl)

            # Image selection
            img_group = QGroupBox(tr("图片", "Image"))
            il = QVBoxLayout()
            isl = QHBoxLayout()
            self._img_path_label = QLabel(tr("未选择", "Not selected"))
            self._img_path_label.setWordWrap(True)
            self._img_path_label.setStyleSheet("color: #8c8c8c;")
            self._browse_btn = QPushButton(tr("浏览...", "Browse..."))
            self._browse_btn.clicked.connect(self._on_browse)
            isl.addWidget(self._img_path_label, 1)
            isl.addWidget(self._browse_btn)
            il.addLayout(isl)
            img_group.setLayout(il)

            # Parameters
            param_group = QGroupBox(tr("推理参数", "Inference Parameters"))
            pf = QFormLayout()
            self._imgsz_sb = QSpinBox()
            self._imgsz_sb.setRange(32, 2048)
            self._imgsz_sb.setValue(640)
            pf.addRow(tr("图片尺寸：", "Image Size:"), self._imgsz_sb)
            self._conf_sb = QDoubleSpinBox()
            self._conf_sb.setRange(0.0, 1.0)
            self._conf_sb.setValue(0.25)
            self._conf_sb.setSingleStep(0.05)
            pf.addRow(tr("置信度：", "Confidence:"), self._conf_sb)
            self._iou_sb = QDoubleSpinBox()
            self._iou_sb.setRange(0.0, 1.0)
            self._iou_sb.setValue(0.45)
            self._iou_sb.setSingleStep(0.05)
            pf.addRow(tr("IoU：", "IoU:"), self._iou_sb)
            self._device_combo = QComboBox()
            self._device_combo.addItems(["cpu", "0"])
            pf.addRow(tr("设备：", "Device:"), self._device_combo)
            param_group.setLayout(pf)

            # Buttons
            bl = QHBoxLayout()
            self._infer_single_btn = QPushButton(tr("单张推理", "Infer"))
            self._infer_single_btn.setEnabled(False)
            self._infer_single_btn.clicked.connect(self._on_infer_single)
            bl.addWidget(self._infer_single_btn)
            self._infer_batch_btn = QPushButton(tr("批量推理", "Batch Infer"))
            self._infer_batch_btn.setEnabled(False)
            self._infer_batch_btn.clicked.connect(self._on_infer_batch)
            bl.addWidget(self._infer_batch_btn)
            bl.addStretch()

            # Output log
            out_group = QGroupBox(tr("输出日志", "Output Log"))
            ol = QVBoxLayout()
            self._output_text = QTextEdit()
            self._output_text.setReadOnly(True)
            self._output_text.setMaximumHeight(120)
            ol.addWidget(self._output_text)
            out_group.setLayout(ol)

            left_layout.addWidget(run_group)
            left_layout.addWidget(img_group)
            left_layout.addWidget(param_group)
            left_layout.addLayout(bl)
            left_layout.addWidget(out_group)
            left_layout.addStretch()
            left.setLayout(left_layout)
            left.setMaximumWidth(360)

            # --- Right panel: viewer ---
            from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
            self._viewer = InferenceViewerWidget()

            splitter = QSplitter()
            splitter.addWidget(left)
            splitter.addWidget(self._viewer)
            splitter.setSizes([340, 600])

            main = QVBoxLayout()
            main.setContentsMargins(0, 0, 0, 0)
            main.addWidget(splitter)
            self.setLayout(main)

            self._selected_image_path: str | None = None

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def set_project_context(self, training_service=None):
            self._training_service = training_service
            self._populate_runs()

        def display_inference_result(
            self, image_path: str, detections: list[dict], class_names: list[str],
        ) -> None:
            self._viewer.load_image(image_path)
            self._viewer.draw_detections(detections, class_names)

        # ------------------------------------------------------------------
        # Internal
        # ------------------------------------------------------------------

        def _populate_runs(self):
            self._run_combo.clear()
            ts = getattr(self, "_training_service", None)
            if ts is None:
                return
            runs_dir = Path(ts.project_root) / "runs"
            if not runs_dir.exists():
                return
            cnt = 0
            for rd in sorted(runs_dir.iterdir()):
                if not rd.is_dir():
                    continue
                try:
                    run = ts.read_run_record(rd.name)
                    if run is not None and run.status == "completed":
                        self._run_combo.addItem(f"{run.id} ({run.task_family})", run.id)
                        cnt += 1
                except Exception:
                    continue
            has = cnt > 0
            self._infer_single_btn.setEnabled(has)
            self._infer_batch_btn.setEnabled(has)

        def _on_browse(self):
            from PyQt6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, tr("选择图片", "Select Image"), "",
                tr("图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;所有 (*)",
                   "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;All (*)"),
            )
            if path:
                self._selected_image_path = path
                self._img_path_label.setText(Path(path).name)
                self._viewer.load_image(path)

        def _on_infer_single(self):
            if not self._selected_image_path:
                self._output_text.append(tr("请先选择一张图片。", "Please select an image first."))
                return
            self._do_infer("single")

        def _on_infer_batch(self):
            self._do_infer("batch")

        def _do_infer(self, mode: str):
            run_id = self._run_combo.currentData()
            if not run_id:
                return
            config = {
                "run_id": run_id, "mode": mode,
                "imgsz": self._imgsz_sb.value(),
                "conf": self._conf_sb.value(),
                "iou": self._iou_sb.value(),
                "device": self._device_combo.currentText(),
            }
            if mode == "single" and self._selected_image_path:
                config["image_path"] = self._selected_image_path
            self.infer_requested.emit(config)
            self._output_text.append(
                tr(f"推理请求已发送 (mode={mode})", f"Inference request sent (mode={mode})")
            )
```

Add missing imports at the top of the try block:
```python
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QComboBox, QPushButton, QTextEdit, QLabel, QFormLayout,
        QSpinBox, QDoubleSpinBox, QSplitter,
    )
```

### Step 2: Commit

```bash
git add anylabeling/views/platform/infer_workspace.py
git commit -m "feat: integrate InferenceViewerWidget into InferWorkspace with split-panel layout"
```

---

## Task 8: WorkbenchWindow 接线 post-infer 结果渲染

**Files:**
- Modify: `anylabeling/views/platform/workbench_window.py`

### Step 1: Add polling-based post-infer result display

Modify `_on_infer_requested` to poll for completion and render results. After the job creation in the try block, add:

```python
            self._pending_infer = {
                "job_id": job_id,
                "mode": mode,
                "image_path": config.get("image_path"),
                "run": run,
            }
            if not hasattr(self, "_infer_poll_timer"):
                from PyQt6.QtCore import QTimer
                self._infer_poll_timer = QTimer(self)
                self._infer_poll_timer.timeout.connect(self._poll_infer_completion)
            self._infer_poll_timer.start(2000)
```

Add the poll handler:

```python
    def _poll_infer_completion(self) -> None:
        """Poll for inference job completion and render results."""
        pending = getattr(self, "_pending_infer", None)
        if pending is None:
            if hasattr(self, "_infer_poll_timer"):
                self._infer_poll_timer.stop()
            return

        from anylabeling.platform.workers.protocol import JobState
        state = self._job_service.get_job_state(pending["job_id"])

        terminal = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
        if state not in terminal:
            return

        if hasattr(self, "_infer_poll_timer"):
            self._infer_poll_timer.stop()

        if state == JobState.COMPLETED and pending["mode"] == "single":
            import json
            stdout, _ = self._job_service.get_job_logs(pending["job_id"])
            try:
                detections = json.loads(stdout.strip().split("\n")[-1])
                if isinstance(detections, list):
                    training_service = self._train_workspace.training_service()
                    run = training_service.read_run_record(pending["run"].id)
                    class_names = []
                    if run and run.config:
                        from anylabeling.platform.infrastructure.project_file_store import ProjectFileStore
                        try:
                            labels_data = ProjectFileStore.open_labels(self._project_path)
                            class_names = [lb["name"] for lb in labels_data]
                        except Exception:
                            pass
                    self._infer_workspace.display_inference_result(
                        pending["image_path"], detections, class_names,
                    )
            except Exception:
                logger.exception("Failed to parse inference results")

        self._pending_infer = None
```

### Step 2: Commit

```bash
git add anylabeling/views/platform/workbench_window.py
git commit -m "feat: wire post-inference result rendering in WorkbenchWindow"
```

---

## Task 9: 创建 ExportValidators (15+ 格式验证器)

**Files:**
- Create: `anylabeling/platform/adapters/ultralytics/export_validators.py`
- Create: `tests/platform/adapters/ultralytics/test_export_validators.py`

### Step 1: Write tests

```python
# tests/platform/adapters/ultralytics/test_export_validators.py
from __future__ import annotations

from anylabeling.platform.adapters.ultralytics.export_validators import (
    SUPPORTED_EXPORT_FORMATS,
    get_export_validator,
    validate_export_environment,
)


class TestSupportedFormats:
    def test_onnx_is_supported(self):
        assert "onnx" in SUPPORTED_EXPORT_FORMATS

    def test_engine_is_supported(self):
        assert "engine" in SUPPORTED_EXPORT_FORMATS

    def test_coreml_is_supported(self):
        assert "coreml" in SUPPORTED_EXPORT_FORMATS

    def test_torchscript_is_supported(self):
        assert "torchscript" in SUPPORTED_EXPORT_FORMATS

    def test_at_least_15_formats(self):
        assert len(SUPPORTED_EXPORT_FORMATS) >= 15

    def test_all_formats_have_validator(self):
        for fmt in SUPPORTED_EXPORT_FORMATS:
            validator = get_export_validator(fmt)
            assert callable(validator), f"No validator for: {fmt}"

    def test_unknown_format_returns_noop(self):
        validator = get_export_validator("unknown_format")
        result = validator()
        assert result == []


class TestValidateExportEnvironment:
    def test_torchscript_always_passes(self):
        missing = validate_export_environment("torchscript")
        assert missing == []

    def test_onnx_returns_list(self):
        missing = validate_export_environment("onnx")
        assert isinstance(missing, list)
```

### Step 2: Run test to verify it fails

```bash
pytest tests/platform/adapters/ultralytics/test_export_validators.py -v
```
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Implement ExportValidators

```python
# anylabeling/platform/adapters/ultralytics/export_validators.py
"""Format-specific environment validators for YOLO model export.

Ported from ``anylabeling/services/auto_training/ultralytics/exporter.py``.
"""

from __future__ import annotations

import importlib.util

SUPPORTED_EXPORT_FORMATS: list[str] = [
    "onnx", "openvino", "engine", "coreml", "saved_model", "pb",
    "tflite", "edgetpu", "tfjs", "paddle", "mnn", "ncnn",
    "imx", "rknn", "torchscript",
]


def _check_pkg(name: str) -> bool:
    spec = importlib.util.find_spec(name)
    return spec is not None


def _validate_onnx() -> list[str]:
    missing = []
    for p in ("onnx", "onnxslim", "onnxruntime"):
        if not _check_pkg(p):
            missing.append(p)
    return missing


def _validate_openvino() -> list[str]:
    return [] if _check_pkg("openvino") else ["openvino"]


def _validate_tensorrt() -> list[str]:
    return [] if _check_pkg("tensorrt") else ["tensorrt"]


def _validate_coreml() -> list[str]:
    return [] if _check_pkg("coremltools") else ["coremltools"]


def _validate_tensorflow() -> list[str]:
    return [] if _check_pkg("tensorflow") else ["tensorflow"]


def _validate_paddle() -> list[str]:
    if _check_pkg("paddlepaddle") or _check_pkg("paddlepaddle-gpu"):
        return []
    return ["paddlepaddle"]


def _validate_mnn() -> list[str]:
    return [] if _check_pkg("MNN") else ["MNN"]


def _validate_ncnn() -> list[str]:
    return [] if _check_pkg("ncnn") else ["ncnn"]


def _validate_imx500() -> list[str]:
    return [] if _check_pkg("imx500-converter") else ["imx500-converter"]


def _validate_rknn() -> list[str]:
    return [] if _check_pkg("rknn-toolkit2") else ["rknn-toolkit2"]


def _validate_torchscript() -> list[str]:
    return []


def _validate_noop() -> list[str]:
    return []


_VALIDATORS: dict[str, callable] = {
    "onnx": _validate_onnx,
    "openvino": _validate_openvino,
    "engine": _validate_tensorrt,
    "coreml": _validate_coreml,
    "saved_model": _validate_tensorflow,
    "pb": _validate_tensorflow,
    "tflite": _validate_tensorflow,
    "edgetpu": _validate_tensorflow,
    "tfjs": _validate_tensorflow,
    "paddle": _validate_paddle,
    "mnn": _validate_mnn,
    "ncnn": _validate_ncnn,
    "imx": _validate_imx500,
    "rknn": _validate_rknn,
    "torchscript": _validate_torchscript,
}


def get_export_validator(export_format: str) -> callable:
    """Return the validator function for *export_format*."""
    return _VALIDATORS.get(export_format, _validate_noop)


def validate_export_environment(export_format: str) -> list[str]:
    """Check whether required packages for *export_format* are installed.

    Returns:
        List of missing package names. Empty means all OK.
    """
    return get_export_validator(export_format)()


__all__ = [
    "SUPPORTED_EXPORT_FORMATS",
    "get_export_validator",
    "validate_export_environment",
]
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/platform/adapters/ultralytics/test_export_validators.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add anylabeling/platform/adapters/ultralytics/export_validators.py tests/platform/adapters/ultralytics/test_export_validators.py
git commit -m "feat: add export format validators for 15+ formats (ported from legacy)"
```

---

## Task 10: 扩展 ExportAdapter 和 ExportService 支持多格式

**Files:**
- Modify: `anylabeling/platform/adapters/ultralytics/export_adapter.py`
- Modify: `anylabeling/platform/application/export_service.py`

### Step 1: Extend `build_export_kwargs` to accept format

In `UltralyticsExportAdapter.build_export_kwargs`, change the signature and body:

```python
    def build_export_kwargs(
        self,
        model_path: str,
        output_dir: str,
        format: str = "onnx",
        imgsz: int = 640,
        simplify: bool = True,
        half: bool = False,
        dynamic: bool = False,
        opset: int | None = None,
        batch: int = 1,
    ) -> dict:
        """Build kwargs dict for YOLO model.export().

        Args:
            format: Export format key (e.g. "onnx", "engine", "openvino", ...).
        """
        kwargs: dict = {
            "format": format,
            "imgsz": imgsz,
            "half": half,
            "batch": batch,
        }
        if format == "onnx":
            kwargs["simplify"] = simplify
            kwargs["dynamic"] = dynamic
            if opset is not None:
                kwargs["opset"] = opset
        return kwargs
```

### Step 2: Update ExportService for multi-format + env validation

In `ExportService.start_export`, update the export kwargs call and worker command:

```python
        export_format = export_config.get("format", "onnx")
        export_kwargs = export_adapter.build_export_kwargs(
            model_path=model_path,
            output_dir=models_dir,
            format=export_format,
            imgsz=export_config.get("imgsz", 640),
            simplify=export_config.get("simplify", True),
            half=export_config.get("half", False),
            dynamic=export_config.get("dynamic", False),
            opset=export_config.get("opset"),
            batch=export_config.get("batch", 1),
        )

        command = self._build_export_command(
            model_path, export_kwargs, export_format
        )
```

Replace `_build_export_command` with the version that validates env:

```python
    @staticmethod
    def _build_export_command(
        model_path: str,
        kwargs: dict,
        export_format: str = "onnx",
    ) -> list[str]:
        """Build export command with environment validation."""
        import json

        kwargs_json = json.dumps(kwargs, ensure_ascii=False)

        script = (
            "import json, sys\n"
            "from anylabeling.platform.adapters.ultralytics.export_validators import validate_export_environment\n"
            f"fmt = {json.dumps(export_format)}\n"
            "missing = validate_export_environment(fmt)\n"
            "if missing:\n"
            "    msg = f'Missing packages for {fmt} export: {\" \".join(missing)}. '\n"
            "    msg += 'Please install: pip install ' + ' '.join(missing)\n"
            "    print(json.dumps({'error': msg}))\n"
            "    sys.exit(1)\n"
            "from ultralytics import YOLO\n"
            f"kwargs = json.loads({json.dumps(kwargs_json)})\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            "export_path = model.export(**kwargs)\n"
            "print(json.dumps({'status': 'ok', 'export_path': str(export_path)}))\n"
        )

        return [sys.executable, "-c", script]
```

### Step 3: Commit

```bash
git add anylabeling/platform/adapters/ultralytics/export_adapter.py anylabeling/platform/application/export_service.py
git commit -m "feat: extend ExportAdapter and ExportService for multi-format export with env validation"
```

---

## Task 11: 改造 ExportWorkspace UI 支持多格式选择

**Files:**
- Modify: `anylabeling/views/platform/export_workspace.py`
- Create: `tests/platform/views/test_export_workspace.py`

### Step 1: Write tests

```python
# tests/platform/views/test_export_workspace.py
from __future__ import annotations

import sys

import pytest

try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class TestExportWorkspaceMultiFormat:
    def test_has_format_combo(self):
        from anylabeling.views.platform.export_workspace import ExportWorkspace
        app = _make_app()
        widget = ExportWorkspace()
        assert hasattr(widget, "_format_combo"), "Should have a format selector"
        widget.close()

    def test_default_format_is_onnx(self):
        from anylabeling.views.platform.export_workspace import ExportWorkspace
        app = _make_app()
        widget = ExportWorkspace()
        assert widget._format_combo.currentText().lower() == "onnx"
        widget.close()

    def test_non_onnx_hides_simplify(self):
        from anylabeling.views.platform.export_workspace import ExportWorkspace
        app = _make_app()
        widget = ExportWorkspace()
        idx = widget._format_combo.findText("openvino")
        if idx >= 0:
            widget._format_combo.setCurrentIndex(idx)
            assert not widget._simplify_cb.isVisible()
        widget.close()
```

### Step 2: Run test to verify it fails

```bash
pytest tests/platform/views/test_export_workspace.py -v
```
Expected: FAIL — no `_format_combo` attribute

### Step 3: Rewrite ExportWorkspace

Replace the ExportWorkspace class with a version having a format selector. The module-level `_build_export_config` also needs updating:

```python
# At module level, replace _build_export_config:
def _build_export_config(
    format: str = "onnx",
    imgsz: int = 640,
    simplify: bool = True,
    half: bool = False,
    dynamic: bool = False,
    opset: int | None = None,
    batch: int = 1,
) -> dict:
    config: dict = {
        "format": format,
        "imgsz": imgsz,
        "half": half,
        "batch": batch,
    }
    if format == "onnx":
        config["simplify"] = simplify
        config["dynamic"] = dynamic
        if opset is not None:
            config["opset"] = opset
    return config


# In the try block, add to imports:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
        QSpinBox, QCheckBox, QPushButton, QLabel, QComboBox,
    )

# Format display list
_UI_FORMATS = [
    ("onnx", "ONNX"),
    ("openvino", "OpenVINO"),
    ("engine", "TensorRT (engine)"),
    ("coreml", "CoreML"),
    ("tflite", "TFLite"),
    ("torchscript", "TorchScript"),
    ("saved_model", "TF SavedModel"),
    ("paddle", "PaddlePaddle"),
    ("mnn", "MNN"),
    ("ncnn", "NCNN"),
    ("rknn", "RKNN"),
    ("tfjs", "TF.js"),
    ("pb", "TF PB"),
    ("edgetpu", "Edge TPU"),
    ("imx", "IMX500"),
]

# Inside ExportWorkspace.__init__, after the existing run_group, add format group BEFORE opt_group:

            # --- Format selection ---
            fmt_group = QGroupBox(tr("导出格式", "Export Format"))
            fmt_layout = QHBoxLayout()
            fmt_layout.addWidget(QLabel(tr("格式：", "Format:")))
            self._format_combo = QComboBox()
            for key, label in _UI_FORMATS:
                self._format_combo.addItem(label, key)
            self._format_combo.currentIndexChanged.connect(self._on_format_changed)
            fmt_layout.addWidget(self._format_combo, 1)
            fmt_group.setLayout(fmt_layout)
            left_layout.insertWidget(1, fmt_group)  # insert after run_group

# Add _on_format_changed method:
        def _on_format_changed(self, idx: int) -> None:
            fmt_key = self._format_combo.itemData(idx)
            is_onnx = (fmt_key == "onnx")
            self._simplify_cb.setVisible(is_onnx)
            self._dynamic_cb.setVisible(is_onnx)
            self._opset_sb.setVisible(is_onnx)

# Update _on_export_clicked to use selected format:
        def _on_export_clicked(self):
            run_id = self._run_combo.currentData()
            if run_id:
                fmt_key = self._format_combo.currentData()
                opset = self._opset_sb.value() if self._opset_sb.value() > 0 else None
                config = _build_export_config(
                    format=fmt_key,
                    imgsz=self._imgsz_sb.value(),
                    half=self._half_cb.isChecked(),
                    batch=self._batch_sb.value(),
                    simplify=self._simplify_cb.isChecked(),
                    dynamic=self._dynamic_cb.isChecked(),
                    opset=opset,
                )
                config["run_id"] = run_id
                self.export_requested.emit(config)
```

Full replacement file is large; see the complete code in the plan artifact.

### Step 4: Run tests to verify they pass

```bash
pytest tests/platform/views/test_export_workspace.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add anylabeling/views/platform/export_workspace.py tests/platform/views/test_export_workspace.py
git commit -m "feat: add multi-format selector to ExportWorkspace (15 export formats)"
```

---

## Task 12: 集成验证 & 全量测试

### Step 1: Run all platform tests

```bash
pytest tests/platform/ -v --tb=short
```
Expected: All tests PASS (or only pre-existing failures)

### Step 2: Run new view tests

```bash
pytest tests/platform/views/ -v --tb=short
```
Expected: All tests PASS

### Step 3: Verify imports

```bash
python -c "from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget; print('metrics_plot OK')"
python -c "from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget; print('inference_viewer OK')"
python -c "from anylabeling.platform.adapters.ultralytics.export_validators import SUPPORTED_EXPORT_FORMATS; print(f'export_validators OK ({len(SUPPORTED_EXPORT_FORMATS)} formats)')"
python -c "from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace; print('evaluate_workspace OK')"
python -c "from anylabeling.views.platform.infer_workspace import InferWorkspace; print('infer_workspace OK')"
python -c "from anylabeling.views.platform.export_workspace import ExportWorkspace; print('export_workspace OK')"
```
Expected: All imports succeed

### Step 4: Final commit

```bash
git add -A
git diff --cached --stat
git commit -m "chore: final integration verification for P0 enhancements"
```

---

## Validation

```bash
# Full test suite
pytest tests/platform/ -v --tb=short

# Import verification
python -c "
from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
from anylabeling.platform.adapters.ultralytics.export_validators import SUPPORTED_EXPORT_FORMATS, validate_export_environment
from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
from anylabeling.views.platform.infer_workspace import InferWorkspace
from anylabeling.views.platform.export_workspace import ExportWorkspace
print('All imports OK')
"

# Format count check
python -c "
from anylabeling.platform.adapters.ultralytics.export_validators import SUPPORTED_EXPORT_FORMATS
assert len(SUPPORTED_EXPORT_FORMATS) >= 15, f'Expected >=15, got {len(SUPPORTED_EXPORT_FORMATS)}'
print(f'{len(SUPPORTED_EXPORT_FORMATS)} export formats registered')
"
```

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| matplotlib backend_qtagg 与 PyQt6 版本不兼容 | Low | backend_qtagg 是 matplotlib ≥3.5 的标准后端，已在 pyproject.toml 依赖中 |
| YOLO val() Results 对象属性因 ultralytics 版本差异而缺失 | Medium | worker 脚本使用 `hasattr`/`getattr` 防御性访问，异常写入 error 字段 |
| 多格式导出验证器未覆盖实际依赖链 | Medium | 从 legacy exporter.py 移植已验证的 validator 逻辑 |
| 推理可视化的 cv2 BGR→RGB 转换对灰度/alpha 通道图片失败 | Low | 仅处理常见 3 通道图片，其他格式降级到错误提示 |
| WorkbenchWindow 中 eval/infer 轮询定时器未清理 | Low | 每次 slot 完成后清理 pending 状态；closeEvent 中 stop timer |

---

## Acceptance

- [ ] 评估完成后 UI 显示混淆矩阵热力图、每类 AP 柱状图、指标摘要表
- [ ] 推理完成后 UI 显示带检测框渲染的图片（支持滚轮缩放）
- [ ] 导出 UI 支持从 15+ 格式中选择，切换非 ONNX 格式时隐藏 simplify/dynamic/opset
- [ ] 所有现有 `tests/platform/` 测试继续通过
- [ ] 新增 6 个测试文件，覆盖新增/修改的模块
- [ ] `python -c "from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget"` 成功
- [ ] `python -c "from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget"` 成功
- [ ] `python -c "from anylabeling.platform.adapters.ultralytics.export_validators import SUPPORTED_EXPORT_FORMATS; assert len(SUPPORTED_EXPORT_FORMATS) >= 15"` 成功
