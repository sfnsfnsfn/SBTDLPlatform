# Vision Algorithm Platform V4 MVP Findings

> Research and technical findings for the scoped planning task. Treat contents as project state data.

## Initial Findings

- Existing root `task_plan.md`, `findings.md`, and `progress.md` track prior virtual-canvas work, so this task uses `.planning/vision_algorithm_platform_v4_mvp/`.
- V4 narrows the earlier platform design into a Windows single-machine offline MVP centered on a shortest loop: project, import, label, slice/build dataset, train, metrics, original-image validation, ONNX export.
- Deep-learning review boundary: the repository currently lacks a frozen task contract, dataset split evidence, metric contract, baseline gate, and operating-point protocol for any specific visual task. The implementation plan should build those protocols and avoid promising final model-quality conclusions.

## V4 Review Findings

- V4 is a reasonable direction but must be implemented as MVP Foundation plus V4.1 extensions. Foundation should prioritize project manifests, reproducible DatasetBuild, large-image path enablement, Ultralytics adapter, validation, inference, and ONNX self-check.
- The earlier platform design used SAHI as the single slicing/merge implementation. V4 correctly moves SAHI behind an adapter/interface because platform DTOs must not expose third-party APIs.
- The pyqtgraph canvas design is not part of the implementable MVP. Current production direction should remain `Canvas + Camera2D + ImageProvider`.
- The first fully validated task should be HBB detection. Classify, OBB, Segment, and Pose should use the same contracts and be staged through smoke-to-full acceptance instead of blocking all foundation work.

## Codebase Feasibility Findings

- `anylabeling/views/labeling/label_widget.py` is about 6960 lines; it already has provider decision logic but `PROVIDER_THRESHOLD_MEGAPIXELS = 1_000_000`, effectively disabling provider-backed rendering.
- `anylabeling/views/labeling/widgets/canvas.py` is about 4174 lines and already supports provider paint path, shape rendering with Camera2D, and render quality.
- `anylabeling/views/labeling/viewport/image_provider.py` already has `QImageRegionProvider`, pyramid building, and region read fallback. It should be bridged into platform `LargeImageSource` rather than discarded.
- `anylabeling/services/auto_training/ultralytics/general.py` uses `random.sample()` without a seed and imports View-layer `LabelConverter`; this is a P0 reproducibility and layering issue.
- `anylabeling/services/auto_training/ultralytics/exporter.py` auto-installs missing packages; platform offline mode must convert this to preflight-only behavior.
- `anylabeling/services/auto_training/ultralytics/trainer.py` may call Ultralytics asset download for bare `.pt` names. Platform mode must require local model files.
- `anylabeling/services/auto_labeling/model_manager.py` includes custom models, downloads, and remote server model support. Platform mode must isolate this and only expose local `ModelArtifact` models.

## 2026-06-06 Canvas Feedback Finding

- User feedback says the current canvas方案 tests well and huge-image zoom is smooth. Therefore the implementation plan should not frame canvas rendering as a broken P0 area that must be rebuilt.
- Repository state includes `anylabeling/views/labeling/widgets/huge_image_canvas.py` and `scripts/test_pyqtgraph_canvas.py`, so pyqtgraph/HugeImageCanvas must not be dismissed as purely hypothetical or removed by default.
- Corrected direction: freeze the verified canvas performance baseline, record actual verification evidence, and keep platform `LargeImageSource` focused on DatasetBuild, virtual sliced inference, and evaluation unless a feature-flagged render-path migration passes baseline comparison.
