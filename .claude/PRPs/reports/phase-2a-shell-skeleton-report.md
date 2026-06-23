# Implementation Report: Phase 2a — New Application Shell Skeleton

**Date**: 2026-06-08
**Branch**: feat/dataset-scan-service

## Summary

Replaced the old 8-step horizontal NavigationBar + QTreeWidget + Inspector + JobConsole layout
with a modern 5-domain vertical navigation Shell: AppBar (48px) + PrimaryNav (176px/56px folded)
+ PageHeader (56px) + SubNav (conditional) + StatusBar (24px).

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Large | Large |
| Files Changed | 6 new, 6 modified | 6 new, 4 modified |
| Lines | ~1200 | ~950 |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 0 | Add Shell layout constants to style.py | ✅ | 14 new constants |
| 1 | Create PrimaryNavigation widget | ✅ | Domain enum (5), NavState enum (6), fold/unfold |
| 2 | Create AppBar widget | ✅ | Logo, project selector, task center badge, settings, help |
| 3 | Create PageHeader widget | ✅ | Title, subtitle, breadcrumb, status, primary action |
| 4 | Create StatusBar widget | ✅ | Save status, device, background tasks, offline |
| 5 | Create SubNav widget | ✅ | 4-step data prep inline stepper with summary |
| 6 | Create shell/__init__.py | ✅ | 8 public exports |
| 7 | Refactor WorkbenchWindow to new Shell | ✅ | New layout, legacy widgets preserved (hidden) |
| 8 | Mark NavigationBar deprecated | ✅ | Docstrings updated, PipelineStep/step_label preserved |
| 9 | Add LabelWorkspace nav fold signal | ✅ | showEvent/hideEvent → nav_fold_requested |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | ✅ | All shell imports OK |
| Unit Tests | ✅ | 884 passed, 0 regressions |
| Integration | ✅ N/A | Desktop GUI app |
| Edge Cases | ✅ | Legacy widgets still importable |

## Files Changed

| File | Action | Lines |
|---|---|---|
| `views/platform/shell/__init__.py` | CREATED | +20 |
| `views/platform/shell/app_bar.py` | CREATED | +190 |
| `views/platform/shell/primary_navigation.py` | CREATED | +235 |
| `views/platform/shell/page_header.py` | CREATED | +190 |
| `views/platform/shell/status_bar.py` | CREATED | +160 |
| `views/platform/shell/sub_nav.py` | CREATED | +195 |
| `views/platform/style.py` | UPDATED | +20 |
| `views/platform/workbench_window.py` | UPDATED | +85 / -40 |
| `views/platform/navigation_bar.py` | UPDATED | +8 / -2 |
| `views/platform/label_workspace.py` | UPDATED | +11 |

## Deviations from Plan

1. **AppBar logo**: Plan specified `new_icon("icon")` from `resources.resources` which does not exist. Used styled QLabel with "X" letter mark instead.
2. **StatusBar showMessage**: Old QStatusBar calls replaced with `_status_bar_widget.set_save_status()` instead of custom showMessage. Full StatusBar API retained.
3. **Nav fold auto-breakpoint**: Plan mentioned `< 1440px` auto-suggest fold. Implementation uses explicit `showEvent`/`hideEvent` on LabelWorkspace instead (more predictable for desktop use).

## Agent Execution Log

| Task | Agent | Stage | Output Summary | Adopted | Verified |
|---|---|---|---|---|---|
| T0 | — | — | Direct (no PRECHECK required) | N/A | ✅ |
| T1-T5 | — | IMPLEMENT | Direct — new widget files | N/A | ✅ |
| T6 | — | — | Direct (no PRECHECK) | N/A | ✅ |
| T7 | — | IMPLEMENT | WorkbenchWindow layout refactored | N/A | ✅ |
| T8 | — | IMPLEMENT | NavigationBar deprecated | N/A | ✅ |
| T9 | — | IMPLEMENT | LabelWorkspace nav fold signal | N/A | ✅ |

> Note: Agent orchestration was streamlined due to session cost constraints.
> All code was reviewed for correctness, PEP 8, and PyQt6 best practices.

## Code Review Findings & Fixes

### CRITICAL (fixed)
| File | Issue | Fix |
|------|-------|-----|
| `shell/status_bar.py:63` | `mousePressEvent` monkey-patch broken in PyQt6 | Replaced with `installEventFilter()` + `eventFilter()` |

### HIGH — Phase 2a introduced (fixed)
| File | Issue | Fix |
|------|-------|-----|
| `shell/page_header.py:77` | Dead `actionable` parameter in `set_status()` | Removed parameter |
| `shell/page_header.py:127` | Redundant `setStyleSheet` overwritten by `_apply_theme()` | Removed redundant call |
| `shell/primary_navigation.py:201` | Duplicate `tr()` call for same result | Extracted local variable |

### HIGH — pre-existing (deferred to Phase 2b)
| File | Issue |
|------|-------|
| `workbench_window.py:885` | `_train_workspace` never assigned — build refresh silently broken |
| `workbench_window.py:411,1349` | Bare `except Exception: pass` swallows errors |

### Validation after fixes
| Check | Result |
|-------|--------|
| eventFilter unit test | ✅ PASS |
| Platform regression | ✅ 884 passed, 0 regressions |

## Next Steps
- [x] Code review via `/code-review` — 1 CRITICAL + 3 HIGH fixed, 2 pre-existing HIGH deferred
- [x] Manual GUI smoke test via `/verify` — PASS, all Shell widgets functional
- [ ] Phase 2b: WorkflowState + ProjectSession + TaskCenterDrawer + ErrorBanner
- [ ] Phase 3: data import precheck refactor + label autosave
