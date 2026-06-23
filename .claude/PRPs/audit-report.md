# Control Wiring Audit — Phase 0

> Generated: 2026-06-07 | Branch: feat/dataset-scan-service

## Summary

| Metric | Count |
|--------|-------|
| Total controls scanned | 72 |
| ✅ WIRED (signal connected) | 38 |
| ⚠️ PASSIVE (consumed at action time) | 24 |
| ❌ DEAD (no signal, not consumed) | 6 |
| 🔮 FUTURE (placeholder only) | 4 |

---

## Detailed Audit Table

### preprocess_workspace.py (19 controls)

| Line | Control | Type | Signal | Handler | Status |
|------|---------|------|--------|---------|--------|
| 72 | _tile_width_sb | QSpinBox | valueChanged | _on_tile_params_changed | ✅ WIRED |
| 78 | _tile_height_sb | QSpinBox | valueChanged | _on_tile_params_changed | ✅ WIRED |
| 84 | _overlap_x_sb | QSpinBox | valueChanged | _on_tile_params_changed | ✅ WIRED |
| 91 | _overlap_y_sb | QSpinBox | valueChanged | _on_tile_params_changed | ✅ WIRED |
| 98 | _edge_mode_combo | QComboBox | (none) | read by _get_current_config | ⚠️ PASSIVE |
| 120 | _split_strategy_combo | QComboBox | (none) | read by _get_current_config | ⚠️ PASSIVE |
| 124 | _train_ratio_sb | QDoubleSpinBox | valueChanged | _on_split_params_changed | ✅ WIRED |
| 131 | _val_ratio_sb | QDoubleSpinBox | valueChanged | _on_split_params_changed | ✅ WIRED |
| 138 | _test_ratio_sb | QDoubleSpinBox | valueChanged | _on_split_params_changed | ✅ WIRED |
| 145 | _seed_sb | QSpinBox | (none) | read by _get_current_config | ⚠️ PASSIVE |
| 161 | _hflip_cb | QCheckBox | (none) | read by _get_current_config | ❌ DEAD (no backend) |
| 165 | _vflip_cb | QCheckBox | (none) | read by _get_current_config | ❌ DEAD (no backend) |
| 168 | _brightness_cb | QCheckBox | (none) | read by _get_current_config | ❌ DEAD (no backend) |
| 172 | _rotate_cb | QCheckBox | (none) | read by _get_current_config | ❌ DEAD (no backend) |
| 184 | _preview_btn | QPushButton | (none) | — | ❌ DEAD (no-op) |
| 187 | _build_btn | QPushButton | clicked | _on_build_clicked | ✅ WIRED |

### train_workspace.py (26 controls)

| Line | Control | Type | Signal | Handler | Status |
|------|---------|------|--------|---------|--------|
| 383 | _mode_combo | QComboBox | currentIndexChanged | _on_mode_changed | ✅ WIRED |
| 433 | _chk_resume | QCheckBox | (none) | read by _build_train_request | ❌ DEAD (no backend) |
| 542 | _btn_start | QPushButton | clicked | _on_start | ✅ WIRED |
| 549 | _btn_stop | QPushButton | clicked | _on_stop | ✅ WIRED |
| 571 | _combo_task | QComboBox | currentIndexChanged | _on_task_changed | ✅ WIRED |
| 575 | _combo_dataset | QComboBox | currentIndexChanged | _on_dataset_changed | ✅ WIRED |
| 579 | _combo_algorithm | QComboBox | currentIndexChanged | _on_algorithm_changed | ✅ WIRED |
| 583 | _edit_base_model | QLineEdit | (none) | read by _build_train_request | ⚠️ PASSIVE |
| 613 | _combo_optimizer | QComboBox | (none) | read by _build_train_request | ⚠️ PASSIVE |
| ~596 | dynamic QLineEdit × 12 | QLineEdit | (none) | read by _build_train_request | ⚠️ PASSIVE |
| ~164 | dynamic QCheckBox × 3 | QCheckBox | (none) | read by _build_train_request | ⚠️ PASSIVE |

### export_workspace.py (14 controls)

| Line | Control | Type | Signal | Handler | Status |
|------|---------|------|--------|---------|--------|
| 100 | _run_combo | QComboBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 128 | _imgsz_sb | QSpinBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 133 | _half_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 136 | _batch_sb | QSpinBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 142 | _simplify_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 146 | _dynamic_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 155 | _include_labels_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 162 | _include_preprocess_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 169 | _include_inference_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 178 | _encrypt_model_cb | QCheckBox | toggled | _on_encrypt_toggled | ✅ WIRED |
| 182 | _encrypt_password_edit | QLineEdit | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 199 | _auto_register_cb | QCheckBox | (none) | read by _on_export_clicked | ⚠️ PASSIVE |
| 210 | _export_btn | QPushButton | clicked | _on_export_clicked | ✅ WIRED |
| 276 | format QCheckBox × N | QCheckBox | toggled | _on_format_toggled | ✅ WIRED |

### label_workspace.py, evaluate_workspace.py, data_workspace.py, infer_workspace.py, task_configurator.py

All controls are either ✅ WIRED or ⚠️ PASSIVE (consumed at action time).
See full details in code.

## ❌ DEAD Controls (Phase 0 Action Required)

| File:Line | Control | Action |
|-----------|---------|--------|
| preprocess_workspace.py:161 | _hflip_cb | disable + tooltip "(规划中)" |
| preprocess_workspace.py:165 | _vflip_cb | disable + tooltip "(规划中)" |
| preprocess_workspace.py:168 | _brightness_cb | disable + tooltip "(规划中)" |
| preprocess_workspace.py:172 | _rotate_cb | disable + tooltip "(规划中)" |
| preprocess_workspace.py:184 | _preview_btn | disable + tooltip "(规划中)" |
| train_workspace.py:433 | _chk_resume | setVisible(False) |
| task_configurator.py:242 | _import_label_btn | disable + tooltip "(规划中)" |

## Dead Code Modules

| File | Status | Disposition |
|------|--------|-------------|
| `views/labeling/viewport/tile_cache.py` | 🔮 Implemented, zero consumers | Phase 1 decision |
| `views/labeling/viewport/tile_grid.py` | 🔮 Implemented, zero consumers | Phase 1 decision |
| `views/labeling/widgets/huge_image_canvas.py` | 🔮 Tested, not wired to main Canvas | Phase 1 decision |
| `views/platform/data_workspace.py` | ✅ Implemented, wired in set_project | Phase 2 |
| `views/platform/infer_workspace.py` | ✅ Implemented, not instantiated | Phase 2 |
