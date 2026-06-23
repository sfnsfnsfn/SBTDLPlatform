# Vision Algorithm Platform V4 MVP — Review Agent Checklists

> Source: `docs/superpowers/specs/2026-06-06-vision-algorithm-platform-design-v4-mvp-foundation.md` Section 12
> Date: 2026-06-06
> Status: Active — applies to all milestones M0 through M5

---

## Review Agent Definition

| Agent | Scope | Primary Focus |
|--------|-------|---------------|
| R1 | Architecture boundaries | Layered imports, DTO, Manifest, AtomicWriter, Service boundaries |
| R2 | Geometry & coordinates | Camera2D, canvas baseline, TilePlan, label split/merge, prediction recovery |
| R3 | Training reproducibility & offline | Split seed, DatasetBuild, Run, offline model, no network download |
| R4 | UI & threading | UI state, Worker events, cancel, logging, no UI thread blocking |
| R5 | Release acceptance | End-to-end closure, 32k large image, ONNX self-test, documentation evidence |

Each milestone must be reviewed by at least two Review Agents, one of which must not be the primary direction for that milestone.

---

## Review Conclusion Format

Every review MUST output the following structured conclusion:

```
## Findings
(Concrete findings — code issues, design concerns, data quality problems)

## Blocking
(Blocking items that prevent milestone pass. Write "None" if there are none.)

## Tests
(Summary of test results — commands run and their output)

## Residual Risk
(Remaining risks accepted by the reviewer)
```

---

## R1: Architecture Boundary Review

### Review Scope

Verify that the platform domain layer has zero dependencies on UI layer (PyQt, views), that infrastructure layer respects write contracts, and that manifest files conform to the JSONL specification.

### Files That Must Be Reviewed

| Category | Files / Directories |
|----------|---------------------|
| Domain imports | `anylabeling/platform/domain/**/*.py` |
| Service layer | `anylabeling/platform/**/services/` or equivalent |
| Infra layer | `anylabeling/platform/**/infrastructure/` or equivalent |
| Manifest files | `*.jsonl` in project directories |
| Project file store | `anylabeling/platform/**/project_file_store*` or equivalent |

### Commands That Must Be Run

```bash
# Domain must not import PyQt, Ultralytics, or views
rg "import.*PyQt|from.*PyQt|import.*ultralytics|from.*ultralytics|import.*views|from.*views" anylabeling/platform/domain/ --no-filename

# DatasetBuildService must not import views.*
rg "import.*views|from.*views" anylabeling/platform/ -l

# All manifest files must be UTF-8 JSONL, each line must parse independently
python -c "
import json, glob
for f in glob.glob('**/*.jsonl', recursive=True):
    with open(f, 'r', encoding='utf-8') as fp:
        for i, line in enumerate(fp, 1):
            line = line.strip()
            if not line: continue
            json.loads(line)
    print(f'{f}: OK')
"

# Run platform domain + infrastructure tests
python -m pytest tests/platform/domain tests/platform/infrastructure -q --tb=short
```

### Blocking Conditions

| # | Condition | Severity |
|----|-----------|----------|
| R1-B1 | `anylabeling/platform/domain/` imports `PyQt*` | CRITICAL |
| R1-B2 | `anylabeling/platform/domain/` imports `ultralytics` | CRITICAL |
| R1-B3 | `anylabeling/platform/domain/` imports anything from `anylabeling.views` | CRITICAL |
| R1-B4 | Any platform service class imports `views.*` | CRITICAL |
| R1-B5 | `ProjectFileStore` writes authoritative JSON without using `AtomicWriter` | CRITICAL |
| R1-B6 | Any `*.jsonl` manifest is not UTF-8 or a line fails `json.loads()` independently | HIGH |
| R1-B7 | `python -m pytest tests/platform/domain tests/platform/infrastructure` fails | CRITICAL |

---

## R2: Geometry & Coordinate Review

### Review Scope

Verify that all coordinates in shapes, tiles, and predictions use L0 image coordinates as the sole authority. Ensure that canvas performance baselines are preserved, tile splits do not modify original annotations, and merge errors are within tolerance.

### Files That Must Be Reviewed

| Category | Files / Directories |
|----------|---------------------|
| Canvas baseline | Performance baseline file (see M2.1), `anylabeling/views/labeling/widgets/huge_image_canvas.py` |
| Camera2D & coordinate map | `anylabeling/views/labeling/viewport/camera.py`, `coordinate_map.py` |
| Image provider | `anylabeling/views/labeling/viewport/image_provider.py` |
| Tile planning | `anylabeling/platform/**/tile_plan*` or equivalent |
| Label splitter | `anylabeling/platform/**/splitter*` or equivalent |
| Label merger | `anylabeling/platform/**/merger*` or equivalent |
| Prediction recovery | `anylabeling/platform/**/prediction*` or equivalent |
| Viewport tests | `tests/views/labeling/viewport/` |

### Commands That Must Be Run

```bash
# Verify canvas performance baseline file exists
ls -la docs/superpowers/specs/*canvas-baseline* 2>/dev/null || echo "MISSING: canvas baseline file"

# Verify tile/geometry tests exist and pass
python -m pytest tests/platform/tiling tests/views/labeling/viewport -q --tb=short

# Verify no splitter modifies the original AnnotationDocument (code review check)
rg -n "AnnotationDocument.*=.*deepcopy|copied.*Annotation|original.*annotation" anylabeling/platform/ -g "*.py"

# Verify HBB merge error tolerance
python -m pytest tests/platform/tiling -k "merge or roundtrip" -q --tb=short
```

### Blocking Conditions

| # | Condition | Severity |
|----|-----------|----------|
| R2-B1 | Canvas performance baseline file is missing or unreadable | HIGH |
| R2-B2 | Any shape/tile/prediction coordinate is not in L0 image coordinates | CRITICAL |
| R2-B3 | Splitter modifies the original `AnnotationDocument` object (not a copy) | CRITICAL |
| R2-B4 | HBB merge produces errors > 1 pixel in any direction | HIGH |
| R2-B5 | OBB or Polygon merge produces illegal self-intersecting geometry | CRITICAL |
| R2-B6 | Any tile from the same source image appears in more than one split (train/val/test) | CRITICAL |
| R2-B7 | Default canvas rendering path is modified without before/after comparison and rollback switch | CRITICAL |
| R2-B8 | `python -m pytest tests/platform/tiling tests/views/labeling/viewport -q` fails | CRITICAL |

---

## R3: Training Reproducibility & Offline Review

### Review Scope

Verify that training data construction is fully reproducible (same seed + same input = same output), that each Run records all necessary provenance information, and that no platform path invokes network access, automatic downloads, or pip install.

### Files That Must Be Reviewed

| Category | Files / Directories |
|----------|---------------------|
| DatasetBuild | `anylabeling/platform/**/dataset_build*` or equivalent |
| Run model | `anylabeling/platform/**/run*` or equivalent |
| Train config | `anylabeling/platform/**/train_config*` or equivalent |
| Offline policy | `anylabeling/platform/**/offline*` or equivalent |
| Model loading | `anylabeling/platform/**/model_artifact*` or equivalent |
| Split manifest | `split_manifest.jsonl` in test project directories |
| Export manager | `anylabeling/services/auto_training/ultralytics/exporter.py` |

### Commands That Must Be Run

```bash
# Verify DatasetBuild is reproducible (byte-identical output)
# This is a structural check; actual reproducibility requires running the
# build twice with same seed and comparing checksums.
# The code must accept a seed parameter and not use random without seed.
rg -n 'random\.(sample|shuffle|randint|choice|random)' anylabeling/platform/ -g '*.py'

# Platform paths must not call pip install
rg -n "pip install|subprocess.*pip|install_package|os.system.*pip" anylabeling/platform/ -g "*.py"

# Platform paths must not auto-download bare .pt files
rg -n "attempt_download_asset|torch.hub.load|download.*\.pt" anylabeling/platform/ -g "*.py"

# Verify threshold/postprocess/augmentation selection comes from validation config only
rg -n "threshold|postprocess|augmentation" anylabeling/platform/ -g "*.py" -i

# Run platform application + adapters tests
python -m pytest tests/platform/application tests/platform/adapters -q --tb=short
```

### Blocking Conditions

| # | Condition | Severity |
|----|-----------|----------|
| R3-B1 | `DatasetBuild` with same seed and same input manifest produces different bytes on two runs | CRITICAL |
| R3-B2 | `Run` does not record: `DatasetBuild` reference, `TaskSpec`, base model, train config, and environment info | CRITICAL |
| R3-B3 | Any platform path calls `pip install` or `subprocess` package installation | CRITICAL |
| R3-B4 | Any platform path auto-downloads a bare `.pt` file from the network | CRITICAL |
| R3-B5 | Threshold, postprocess, or augmentation selection uses test/holdout data | CRITICAL |
| R3-B6 | Training or validation code uses `random.*` without a fixed seed | HIGH |
| R3-B7 | `python -m pytest tests/platform/application tests/platform/adapters -q` fails | CRITICAL |

---

## R4: UI & Threading Review

### Review Scope

Verify that the UI layer does not directly write project JSON, that long-running tasks always go through dedicated service/worker interfaces, that jobs are not destroyed on page switches, that buttons are properly disabled when preconditions are not met, and that error messages contain user-facing explanations, technical details, and log paths.

### Files That Must Be Reviewed

| Category | Files / Directories |
|----------|---------------------|
| UI pages | `anylabeling/views/**/workbench*` or equivalent |
| Project file writes | Any file that writes to project JSON/YAML |
| Service interfaces | `anylabeling/platform/**/job_service*`, `*training_service*`, `*inference_service*`, `*export_service*` |
| Worker events | `anylabeling/platform/**/worker*`, `*job_runner*` or equivalent |
| Error handling | `anylabeling/views/**` dialog/error displays |
| Button states | `anylabeling/views/**` enable/disable logic |

### Commands That Must Be Run

```bash
# UI must not directly write project JSON (check for direct file writes in views)
rg -n "json\.dump|json\.dumps|yaml\.dump|open\(.*['\"]w['\"]|open\(.*['\"]a['\"]" anylabeling/views/ -g "*.py" --no-filename

# Check long tasks go through services (not direct subprocess/threading in views)
rg -n "QThread|subprocess\.Popen|threading\.Thread|multiprocessing\.Process" anylabeling/views/ -g "*.py" --no-filename

# Check page switching doesn't destroy running jobs (job lifecycle management)
rg -n "job.*cancel|stop.*job|kill.*worker|destroy.*job" anylabeling/ -g "*.py" -l

# Run UI platform tests
python -m pytest tests/views/platform -q --tb=short
```

### Blocking Conditions

| # | Condition | Severity |
|----|-----------|----------|
| R4-B1 | UI code (`anylabeling/views/`) directly writes project JSON/YAML files | CRITICAL |
| R4-B2 | A long-running task (> 500 ms) is executed outside of `JobService`/`TrainingService`/`InferenceService`/`ExportService` | CRITICAL |
| R4-B3 | A page switch destroys or cancels a running job without user confirmation | HIGH |
| R4-B4 | A button is enabled when its preconditions are not met (e.g., "Train" enabled without a dataset) | HIGH |
| R4-B5 | An error message does not include: (a) user-facing explanation, (b) technical detail, (c) log file path | MEDIUM |
| R4-B6 | `python -m pytest tests/views/platform -q` fails | CRITICAL |

---

## R5: Release Acceptance Review

### Review Scope

Verify that the acceptance document records real command output, that manual GUI screenshots and log paths are present, that 32k large-image acceptance is marked pending if not yet executed, that the ONNX self-test report contains fixed samples and thresholds, and that GPLv3 commercial distribution risk is documented in release notes.

### Files That Must Be Reviewed

| Category | Files / Directories |
|----------|---------------------|
| Acceptance docs | `docs/superpowers/**/acceptance*` or equivalent |
| Release notes | `RELEASE.md`, `CHANGELOG.md`, or equivalent |
| ONNX self-test | `docs/superpowers/**/onnx*` or equivalent |
| Manual GUI evidence | Screenshot paths and log paths recorded in acceptance |
| License docs | `LICENSE`, `LICENSES/` or equivalent |

### Commands That Must Be Run

```bash
# Check acceptance file records real command output (not placeholder text)
rg -l "PLACEHOLDER|TODO|TBD|待填写|待补充" docs/superpowers/*acceptance* && echo "WARNING: placeholder text found" || echo "OK: no placeholders"

# Check manual GUI screenshot paths exist
# (Reviewer inspects the acceptance doc and verifies referenced paths exist)

# Check 32k large-image acceptance status
rg -n "32k|32768|large.*image|大图" docs/superpowers/*acceptance*

# Run end-to-end platform tests
python -m pytest tests/e2e/platform -q --tb=short

# Verify ONNX self-test has fixed samples and thresholds
rg -n "sample|threshold|样本|阈值" docs/superpowers/*onnx*

# Check GPLv3 commercial risk documented
rg -n "GPL|commercial|商业|商用|license|许可证" RELEASE* CHANGELOG* LICENSE*
```

### Blocking Conditions

| # | Condition | Severity |
|----|-----------|----------|
| R5-B1 | Acceptance document contains placeholder text (TODO, TBD, 待填写) instead of real command output | HIGH |
| R5-B2 | Manual GUI screenshots or log paths referenced in acceptance do not exist on disk | HIGH |
| R5-B3 | 32k large-image acceptance is claimed as "complete" but no real execution evidence exists | CRITICAL |
| R5-B4 | ONNX self-test report does not include (a) fixed sample names/paths and (b) numerical comparison thresholds | HIGH |
| R5-B5 | GPLv3 commercial distribution risk is not mentioned in release notes | MEDIUM |
| R5-B6 | `python -m pytest tests/e2e/platform -q --tb=short` fails | CRITICAL |

---

## Review Milestone Assignment Matrix

| Milestone | Must Pass R1 | Must Pass R2 | Must Pass R3 | Must Pass R4 | Must Pass R5 |
|-----------|:---:|:---:|:---:|:---:|:---:|
| M0 | x | | | | x |
| M1 | x | | | x | |
| M2 | | x | x | | |
| M3 | | | x | x | |
| M4 | | x | x | | x |
| M5 | | | | | x |

---

## Cross-Review Matrix

For each milestone, the Review Agents assigned must include at least one agent whose primary expertise is NOT the milestone's main direction:

| Milestone | Primary Direction | Required Cross-Review Agent |
|-----------|-------------------|--------------------------|
| M0 (Baseline & Fixtures) | E1/E5 (DTO, fixtures) | R2 (geometry) or R3 (training) |
| M1 (Platform Foundation) | E1/E3 (DTO, Workbench) | R4 (UI) for domain review |
| M2 (Large Image) | E2/E1 (geometry, tiling) | R1 (architecture) or R3 (training) |
| M3 (Training) | E4/E3 (adapter, UI) | R2 (geometry) or R4 (UI cross-check) |
| M4 (Evaluation/ONNX) | E4/E2/E3 | R5 (release prep) mandatory |
| M5 (Release) | E5/all | R1 (architecture final check) |
