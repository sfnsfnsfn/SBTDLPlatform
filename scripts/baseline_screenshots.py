#!/usr/bin/env python
"""Baseline screenshot capture for Phase 0 freeze.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/baseline_screenshots.py

Output:
    docs/baseline/           — 8 PNG screenshots, one per platform page

Limitations:
    - Requires a minimal project to be created first (TEMPORARY: auto-creates
      a synthetic project in a temp directory).
    - QT_QPA_PLATFORM=offscreen must be set for headless environments.
"""

from __future__ import annotations

import os
import sys
import tempfile
import json
from pathlib import Path

import cv2
import numpy as np

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _create_minimal_project(project_dir: Path) -> Path:
    """Create a minimal synthetic project for screenshot capture."""
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    for i in range(3):
        img = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
        color = [(255, 0, 0), (0, 255, 0), (0, 0, 255)][i]
        cv2.rectangle(img, (50 + i * 30, 50 + i * 30),
                      (200 + i * 30, 200 + i * 30), color, -1)
        cv2.imwrite(str(assets_dir / f"sample_{i:02d}.jpg"), img)

    meta = {
        "version": "4.0.0",
        "name": "baseline_project",
        "task_spec": {
            "id": "baseline_task",
            "family": "detection_hbb",
            "annotation_schema": "yolo_bbox",
            "primary_metric": "mAP50-95",
        },
    }
    (project_dir / "project.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    labels = [
        {"id": 0, "name": "defect", "color": "#FF0000"},
        {"id": 1, "name": "scratch", "color": "#00FF00"},
    ]
    (project_dir / "labels.json").write_text(
        json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return project_dir


def _capture_screenshots():
    """Launch the app and capture screenshots of all 8 platform pages."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6 import QtWidgets, QtCore

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    from anylabeling.views.platform.workbench_window import WorkbenchWindow
    from anylabeling.views.platform.navigation_bar import PipelineStep, step_label

    output_dir = _PROJECT_ROOT / "docs" / "baseline"
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "baseline_project"
        _create_minimal_project(project_dir)

        window = WorkbenchWindow()
        window.resize(1400, 900)
        window.show()

        app.processEvents()
        QtCore.QThread.msleep(500)

        window.set_project(str(project_dir))
        app.processEvents()
        QtCore.QThread.msleep(500)

        for step in PipelineStep:
            page_name = step_label(step).replace(
                " ", "_").replace("(", "").replace(")", "")
            try:
                window._navigate_to(step)
                app.processEvents()
                QtCore.QThread.msleep(300)

                page_widget = window._pages.currentWidget()
                if page_widget is not None:
                    pixmap = page_widget.grab()
                    filepath = output_dir / (
                        f"page_{step.value:02d}_{page_name}.png"
                    )
                    pixmap.save(str(filepath), "PNG")
                    print(f"  [OK] {filepath}")
                else:
                    print(f"  [SKIP] Page {step.value}: no widget")
            except Exception as exc:
                print(f"  [FAIL] Page {step.value} ({page_name}): {exc}")

        window.close()

    print(f"\nScreenshots saved to: {output_dir}")
    return 0


def main():
    print("=" * 60)
    print("Baseline Screenshot Capture — Phase 0 Freeze")
    print("=" * 60)
    return _capture_screenshots()


if __name__ == "__main__":
    sys.exit(main())
