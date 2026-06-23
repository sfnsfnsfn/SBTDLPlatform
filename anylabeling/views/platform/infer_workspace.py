# STATUS: Implemented but never instantiated. Phase 2 wiring.
"""Infer Workspace -- model selection, inference parameters, and result visualization."""

from __future__ import annotations

from pathlib import Path

from anylabeling.views.platform.i18n import tr


try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QComboBox, QPushButton, QTextEdit, QLabel, QFormLayout,
        QSpinBox, QDoubleSpinBox, QSplitter, QFileDialog, QCheckBox,
    )
    from PyQt6.QtCore import pyqtSignal

    from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget

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

            # Project assets validation checkbox
            self._project_assets_cb = QCheckBox(
                tr("在项目资产上验证", "Validate on Project Assets")
            )
            self._project_assets_cb.setToolTip(
                tr(
                    "在项目资产上运行模型推理并与标注进行对比验证",
                    "Run model inference on project assets and "
                    "compare with annotations",
                )
            )
            self._project_assets_cb.setVisible(False)
            # Shown when project context is set

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
            """Set the training service and populate runs combo."""
            self._training_service = training_service
            self._project_assets_cb.setVisible(
                training_service is not None
            )
            self._populate_runs()

        def display_inference_result(
            self, image_path: str, detections: list[dict], class_names: list[str],
        ) -> None:
            """Display inference results by drawing detections on the image."""
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
                self._output_text.append(
                    tr("请先选择一张图片。", "Please select an image first.")
                )
                return
            self._do_infer("single")

        def _on_infer_batch(self):
            if self._project_assets_cb.isChecked():
                self._start_asset_validation()
                return
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
                tr(f"推理请求已发送 (mode={mode})",
                   f"Inference request sent (mode={mode})")
            )

        # -- asset validation --------------------------------------------------

        _VALIDATION_MAX_IMAGES = 10

        def _start_asset_validation(self):
            """Scan project assets for validation mode.

            Collects up to ``_VALIDATION_MAX_IMAGES`` images from the
            project and launches batch inference on them.  After
            inference completes, individual results can be compared
            with ground-truth annotations via
            :meth:`display_inference_result`.
            """
            ts = getattr(self, "_training_service", None)
            if ts is None:
                self._output_text.append(
                    tr("训练服务不可用。", "Training service not available.")
                )
                return

            project_root = Path(ts.project_root)
            images_dir = project_root / "assets" / "images"
            annotations_dir = project_root / "annotations" / "documents"

            if not images_dir.exists():
                self._output_text.append(
                    tr(
                        "项目中没有 assets/images/ 目录。请先导入数据。",
                        "No assets/images/ directory in project. "
                        "Import data first.",
                    )
                )
                return

            # Collect images (prefer those with annotations)
            _IMAGE_EXTS = {
                ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff",
            }
            assets: list[dict] = []
            for p in sorted(images_dir.iterdir()):
                if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                    ann = annotations_dir / f"{p.stem}.json"
                    assets.append({
                        "path": str(p),
                        "name": p.name,
                        "has_annotation": ann.exists(),
                    })
                if len(assets) >= self._VALIDATION_MAX_IMAGES:
                    break

            if not assets:
                self._output_text.append(
                    tr(
                        "项目中没有图像文件。",
                        "No image files found in project.",
                    )
                )
                return

            annotated = sum(1 for a in assets if a["has_annotation"])
            self._output_text.append(
                tr(
                    f"验证集：{len(assets)} 张图像"
                    f"（{annotated} 张有标注可供对比）。",
                    f"Validation set: {len(assets)} images "
                    f"({annotated} with annotations for comparison).",
                )
            )
            # List files
            for a in assets:
                tag = " [" + tr("有标注", "annotated") + "]" if a["has_annotation"] else ""
                self._output_text.append(f"  {a['name']}{tag}")

            # Store for later comparison
            self._validation_assets = assets

            # Dispatch batch inference
            self._output_text.append(
                tr("开始验证推理...", "Starting validation inference...")
            )
            self._do_infer("batch")

        def display_validation_comparison(
            self, image_name: str, detections: list[dict],
            class_names: list[str],
        ) -> None:
            """Display per-image validation comparison.

            Called after inference completes for a validation image.
            Compares detections with ground-truth annotations when
            available.
            """
            assets = getattr(self, "_validation_assets", []) or []
            matched = [a for a in assets if a["name"] == image_name]
            asset = matched[0] if matched else None

            if asset is None:
                return

            det_labels = {d.get("label", "?") for d in detections}
            conf_values = [d.get("confidence", 0) for d in detections]
            avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0
            max_conf = max(conf_values) if conf_values else 0

            if asset["has_annotation"]:
                import json
                try:
                    ann_path = (
                        Path(self._training_service.project_root)
                        / "annotations" / "documents"
                        / f"{Path(image_name).stem}.json"
                    )
                    ann_data = json.loads(
                        ann_path.read_text(encoding="utf-8")
                    )
                    ann_labels = {
                        s.get("label", "")
                        for s in ann_data.get("shapes", [])
                    }
                    matched_labels = det_labels & ann_labels
                    ann_count = len(ann_labels)

                    self._output_text.append(
                        tr(
                            f"{image_name}: {len(detections)} 检测 / "
                            f"{ann_count} 标注, "
                            f"匹配 {len(matched_labels)}, "
                            f"avg conf={avg_conf:.2f} max={max_conf:.2f}",
                            f"{image_name}: {len(detections)} det / "
                            f"{ann_count} ann, "
                            f"matched {len(matched_labels)}, "
                            f"avg conf={avg_conf:.2f} max={max_conf:.2f}",
                        )
                    )
                except Exception:
                    self._output_text.append(
                        f"{image_name}: {len(detections)} detections, "
                        f"avg conf={avg_conf:.2f} (annotation read error)"
                    )
            else:
                self._output_text.append(
                    tr(
                        f"{image_name}: {len(detections)} 检测, "
                        f"avg conf={avg_conf:.2f} max={max_conf:.2f} "
                        f"（无标注）",
                        f"{image_name}: {len(detections)} detections, "
                        f"avg conf={avg_conf:.2f} max={max_conf:.2f} "
                        f"(no annotation)",
                    )
                )

except ImportError:
    InferWorkspace = None  # type: ignore
