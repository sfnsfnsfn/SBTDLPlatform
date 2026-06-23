#!/usr/bin/env python
"""Standalone benchmark for HugeImageCanvas with synthetic NxN images.

Usage:
    python scripts/test_pyqtgraph_canvas.py --size 2000           # small smoke test
    python scripts/test_pyqtgraph_canvas.py --size 42000          # full benchmark
    python scripts/test_pyqtgraph_canvas.py --size 10000 --opengl # with OpenGL
"""

import argparse
import sys
import time

import numpy as np
from PyQt6 import QtCore, QtWidgets

sys.path.insert(0, ".")
from anylabeling.views.labeling.widgets.huge_image_canvas import HugeImageCanvas


class TestWindow(QtWidgets.QMainWindow):
    """Benchmark window hosting a HugeImageCanvas with a synthetic image."""

    def __init__(self, use_opengl: bool = False, image_size: int = 42000):
        super().__init__()
        self.setWindowTitle(
            f"HugeImageCanvas Test — {image_size}x{image_size}"
        )
        self.resize(1400, 900)

        # Create and set the canvas as central widget
        self.canvas = HugeImageCanvas(parent=None, use_opengl=use_opengl)
        self.setCentralWidget(self.canvas)

        # Wire signals
        self.canvas.zoom_changed.connect(self._on_zoom)
        self.canvas.pixel_hovered.connect(self._on_pixel)

        # Defer image generation so the window is visible during construction
        self.statusBar().showMessage("Generating test image...")
        QtCore.QTimer.singleShot(50, lambda: self._load_image(image_size))

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------
    def _load_image(self, size: int) -> None:
        """Generate a synthetic uint8 image and hand it to the canvas."""
        t0 = time.perf_counter()
        rng = np.random.default_rng(42)
        img = rng.integers(0, 256, (size, size), dtype=np.uint8)

        # Grid lines every 1000 px for visual orientation
        img[::1000, :] = 200
        img[:, ::1000] = 200

        # Centre crosshair (10x10 white square)
        half = size // 2
        img[half - 5 : half + 5, half - 5 : half + 5] = 255

        gen_elapsed = time.perf_counter() - t0
        self.canvas.set_image(img)
        load_elapsed = time.perf_counter() - t0

        self._img_size = size
        status = (
            f"Loaded {size}x{size} uint8 ({img.nbytes / 1e6:.0f} MB) "
            f"| gen: {gen_elapsed:.2f}s load: {load_elapsed:.2f}s"
        )
        self.statusBar().showMessage(status)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------
    def _on_zoom(self, scale: float) -> None:
        """Update status bar with current scale and performance summary."""
        perf_text = self.canvas.perf.summary()
        if perf_text:
            self.statusBar().showMessage(
                f"Scale: {scale:.4f} | {perf_text}"
            )
        else:
            self.statusBar().showMessage(f"Scale: {scale:.4f}")

    def _on_pixel(self, row: int, col: int, value: object) -> None:
        """Log pixel info to the status bar title area."""
        self.setWindowTitle(
            f"HugeImageCanvas Test — {self._img_size}x{self._img_size} "
            f"| Pixel [{row}, {col}] = {value}"
        )


# ======================================================================
# Entry point
# ======================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark HugeImageCanvas with a synthetic NxN image"
    )
    parser.add_argument(
        "--opengl", action="store_true",
        help="Enable OpenGL rendering in pyqtgraph",
    )
    parser.add_argument(
        "--size", type=int, default=42000,
        help="Side length of the square test image (default: 42000)",
    )
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    win = TestWindow(use_opengl=args.opengl, image_size=args.size)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
