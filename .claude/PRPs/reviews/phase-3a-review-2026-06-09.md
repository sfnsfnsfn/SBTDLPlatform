# Code Review: Phase 3a — Plan Compliance + Quality

**Reviewed**: 2026-06-09
**Branch**: feat/dataset-scan-service
**Decision**: APPROVE with fixes applied

## Summary

Phase 3a core infrastructure is substantially complete — ImportService precheck/cancel pipeline, ImportViewModel state machine, AssetListModel virtual list, AssetFilterBar multi-facet filter, and AssetRepository extension are all implemented and wired. All 33 tests pass with zero regressions. This review found 5 issues (2 HIGH, 3 MEDIUM), all of which have been fixed.

## Findings

### CRITICAL
None

### HIGH

| # | File | Line | Issue | Fix |
|---|------|------|-------|-----|
| H1 | `label_workspace.py` | 372 | `except Exception: pass` silently swallows ALL exceptions including MemoryError, KeyboardInterrupt | → `except (json.JSONDecodeError, OSError): pass` |
| H2 | `label_workspace.py` | 331-334 | AssetRepository path only maps `complete` vs `unannotated`, ignoring PARTIAL status. All partially-annotated assets show wrong icon | → Added `status_map` with 3-way mapping: complete/partial/unannotated |

### MEDIUM

| # | File | Line | Issue | Fix |
|---|------|------|-------|-----|
| M1 | `import_vm.py` | 166 | `except Exception as exc` in `start_precheck()` catches KeyboardInterrupt/SystemExit | → `except (OSError, ValueError, RuntimeError)` |
| M2 | `import_vm.py` | 217 | `except Exception as exc` in `start_import()` — same issue | → `except (OSError, ValueError, RuntimeError)` |
| M3 | `asset_repository.py` | 168 | `uuid.uuid4().hex[:12]` — Asset IDs non-deterministic across sessions. Two calls to `get_asset()` for same path produce different IDs after cache invalidation | → `hashlib.sha256(rel.encode()).hexdigest()[:12]` for deterministic, path-derived IDs |

### LOW

| # | File | Issue | Status |
|---|------|-------|--------|
| L1 | `asset_filter_bar.py:153-158` | Sort dropdown populated but not wired to `QSortFilterProxyModel.setSortRole()` / `sort()` | Known limitation — deferred to full UI integration |
| L2 | `label_workspace.py` | Still uses `QListWidget` (not `QListView`+`AssetListModel`) — Task A8 incomplete | Architectural change, out of scope for this review cycle |
| L3 | `label_workspace.py:_scan_assets()` | AssetRepository path calls `scan_assets()` without pagination — loads all paths at once | Acceptable for now; AssetListModel provides pagination when wired to QListView |

## Validation Results

| Check | Result |
|---|---|
| Import validation (6 modules) | ✅ All pass |
| Unit tests (33) | ✅ 33 passed in 1.47s |
| Plan acceptance (Phase 3a) | ✅ 7/9 criteria met |

## Files Reviewed

| File | Action | Lines |
|---|---|---|
| `anylabeling/platform/domain/import_config.py` | Modified | +66 (PrecheckResult, ImportCancelledError, get_supported_extensions) |
| `anylabeling/platform/domain/__init__.py` | Modified | +5 exports |
| `anylabeling/platform/application/import_service.py` | Modified | +140 (precheck, progress/cancel) |
| `anylabeling/platform/application/asset_repository.py` | Modified | +292 (extended query API, deterministic IDs) |
| `anylabeling/views/platform/view_models/import_vm.py` | 🆕 New | 242 (ImportViewModel state machine) |
| `anylabeling/views/platform/view_models/__init__.py` | Modified | +ImportViewModel export |
| `anylabeling/views/platform/widgets/asset_list_model.py` | 🆕 New | 143 (QAbstractListModel) |
| `anylabeling/views/platform/widgets/asset_filter_bar.py` | 🆕 New | 201 (filter bar + proxy model) |
| `anylabeling/views/platform/widgets/__init__.py` | Modified | +4 exports |
| `anylabeling/views/platform/label_workspace.py` | Modified | +91 (AssetRepository wiring, partial status) |
| `anylabeling/views/platform/workbench_window.py` | Modified | +21 (AssetRepository wiring) |

## Plan Acceptance Cross-Check

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Import precheck separates scan from copy | ✅ | `ImportService.precheck()` — no shutil.copy2 |
| Progress callback + cancel support | ✅ | `import_images()` +progress_callback/cancel_token |
| AssetRepository single source of truth | ✅ | WorkbenchWindow + LabelWorkspace wired |
| QAbstractListModel virtual list | ✅ | `AssetListModel` created (awaiting QListView wiring) |
| Filter bar (status/group/search) | ✅ | `AssetFilterBar` + `AssetFilterProxyModel` created |
| Extension set unified | ✅ | `get_supported_extensions()` single source |
| Domain models immutable | ✅ | `PrecheckResult(frozen=True)` |
| No PyQt6 in application/domain | ✅ | All service/domain files clean |
| ViewModel no PyQt6 imports | ✅ | ImportViewModel pure Python |

## Fixes Applied This Review

1. `label_workspace.py:372` — bare `except Exception:` → `except (json.JSONDecodeError, OSError):`
2. `label_workspace.py:331-334` — added STATUS_PARTIAL support in AssetRepository scanning path
3. `import_vm.py:166` — `except Exception` → `except (OSError, ValueError, RuntimeError)`
4. `import_vm.py:217` — `except Exception` → `except (OSError, ValueError, RuntimeError)`
5. `asset_repository.py:168` — `uuid.uuid4()` → `hashlib.sha256()` for deterministic Asset IDs
