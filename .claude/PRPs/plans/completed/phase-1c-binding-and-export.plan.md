# Plan: Phase 1c — 来源强绑定验证 + 评估指标修复 + ONNX 基础自测

## Summary
审计训练→评估→导出来源强绑定的类型约束是否真实生效，修复评估指标缺失时 "N/A" 显示，验证 ONNX 导出模型可加载和 shape 检查，新增覆盖闭环的绑定审计测试。

## User Story
As a 算法工程师, I want 训练 Run 绑定到不可变 DatasetBuild，评估不能选错权重或数据集，ONNX 导出后模型可加载，So that 我信任每个模型产物的来源链和评估结果。

## Problem → Solution
来源绑定已有类型约束但缺少穿透测试 → 新增审计测试覆盖所有绑定点。评估缺失指标显示 "N/A" → "未生成"。ONNX 导出链路已实现但无自测 → 新增 onnx.load + onnxruntime 加载测试。

## Metadata
- **Complexity**: Medium (5–7 files, ~300 lines)
- **Source PRD Phase**: 阶段 1 — 真实闭环 (子阶段 1c)
- **Depends On**: Phase 1b (complete)
- **PROD Coverage**: PROD-009, PROD-010, PROD-011
- **Estimated Files**: 5 modified, 2 new

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `platform/application/evaluation_service.py` | 69–128 | evaluate_tile_native() — 强制 Run+Build 类型参数 |
| P0 | `platform/application/training_service.py` | 244–311 | start_training() 验证序列 — 4 项检查 |
| P0 | `views/platform/evaluate_workspace.py` | 235–270 | display_metrics() — "N/A" 在 lines 238-241 |
| P1 | `platform/application/export_service.py` | 65–175, 325–377 | start_export() + _build_export_command() |
| P1 | `platform/domain/run.py` | all (42L) | Run.dataset_build_id 绑定字段 |

---

## Patterns to Mirror

### EvaluationService mandatory binding (typed parameters, no fallback)
// SOURCE: platform/application/evaluation_service.py:69-99
```python
def evaluate_tile_native(self, run: Run, build: DatasetBuild, ...) -> str:
    provider = self._get_provider(run)
    model_path = self._resolve_best_pt(run)
    if model_path is None:
        raise ValueError(f"No best.pt found for run {run.id}.")
    dataset_adapter = provider.dataset_adapter
    data_yaml = dataset_adapter.get_data_path(build)
```

### TrainingService binding via Run record
// SOURCE: platform/application/training_service.py:143-160
```python
run = Run(
    id=run_id,
    dataset_build_id=request.dataset_build.id,  # ← 创建时绑定，永不可变
    task_family=request.task_spec.family,
    ...
)
```

### Display metrics current pattern
// SOURCE: views/platform/evaluate_workspace.py:235-241
```python
def display_metrics(self, metrics: dict) -> None:
    lines = [
        f"mAP@50:      {metrics.get('mAP50', 'N/A')}",
        f"mAP@50-95:   {metrics.get('mAP50_95', 'N/A')}",
        f"Precision:   {metrics.get('precision', 'N/A')}",
        f"Recall:      {metrics.get('recall', 'N/A')}",
    ]
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `views/platform/evaluate_workspace.py` | UPDATE | "N/A" → "未生成" / "Not generated" |
| `tests/platform/application/test_training_service.py` | UPDATE | 新增 dataset_build_id 绑定测试 |
| `tests/platform/application/test_evaluation_service.py` | UPDATE | 新增 Run+Build 强绑定审计测试 |
| `tests/platform/application/test_export_service.py` | UPDATE | 新增 ONNX 加载 + shape 自测 |
| `tests/e2e/platform/test_fixtures.py` | UPDATE | 新增 E2E-01c: build→verify 闭环验证 |
| `docs/baseline/onnx-self-test.md` | CREATE | ONNX 自测流程文档 |

## NOT Building (1c scope)

- ONNX 交付包（checksum, README, sample） — Phase 4
- 评估报告混淆矩阵渲染 — Phase 4
- 评估对比功能 — Phase 4
- 本地模型库 — Phase 4
- 训练就绪检查 UI — Phase 4
- 推理验证结果合并 — Phase 4

---

## Agent Orchestration

> 遵循 `.claude/PRPs/agent-orchestration-rules.md` 强制编排规则。

### Core Rules (21 条铁律)

1. 主会话负责整体调度和最终决策，不得独自完成全部分析+实现+审查。
2. 每个 Task 开始前必须调用该 Task 的 PRECHECK_AGENTS。
3. 需要架构判断时调用 `architect`；新功能/Bug 修复先调用 `tdd-guide`。
4. 生产代码由主会话串行写入；`tdd-guide` 仅在 WRITE_SCOPE 授权时写测试。
5. Python 修改后 → `python-reviewer`；Task 完成后 → `code-reviewer`。
6. 文件路径/子进程/模型加载/用户输入/本地数据 → `security-reviewer`。
7. 构建失败 → `build-error-resolver`。审核 Agent 只读不修改源码。
8. 独立只读分析可并行；写入任务必须串行；禁止两个 Agent 同时修改同文件。
9. Agent 禁止 git push/merge/rebase/reset/clean；提交仅由主会话执行。
10. Auto 模式只用于权限判断，不替代 Agent 编排。
11. Implementation Report 必须增加 Agent Execution Log。

### Agent Assignment

| Agent | Role | Tasks | Scope |
|-------|------|-------|-------|
| `tdd-guide` | 测试驱动 | T1, T2, T3 | 来源绑定审计 + ONNX 自测 + E2E 闭环测试设计 |
| `security-reviewer` | 安全审查 | T2, T3 | ONNX 模型文件加载 + E2E 文件操作 |
| `code-reviewer` | 代码审查 | All | 每 Task 完成后强制审查 |
| `python-reviewer` | Python 审查 | All | PEP 8 合规 + 惯用法检查 |
| `doc-updater` | 文档 | T4 | ONNX 自测基线文档 |

### EXECUTION_MODE

**Sequential** — Task 串行执行：T0 → T1 → T2 → T3 → T4。

每个 Task 内部：
- **PRECHECK** Agent 可并行调用（只读互不干扰）
- **IMPLEMENT** 由主会话串行写入（同一时间只有一个写入者）
- **POST_REVIEW** Agent 可并行调用（只读互不干扰）

### WRITE_SCOPE

| Agent | Permitted Files | Constraint |
|--------|-----------------|------------|
| 主会话 | `anylabeling/` 下所有源码 + `docs/` 下文档 | 生产代码 + 文档唯一写入者 |
| `tdd-guide` | `tests/` 下测试文件 | 仅限测试文件，不得修改生产代码 |
| `doc-updater` | `docs/` 下文档文件 | 仅限文档，不得修改源码 |
| 审核 Agent | 只读 | 不得修改任何文件 |

### Agent Execution Log

| Task | Agent | 阶段 | 输出摘要 | 是否采纳 | 验证结果 |
|------|-------|------|----------|----------|----------|
| ... | ... | ... | ... | ... | ... |

---

## Hard Blockers

### HB-5: ONNX "基础自测" 范围
- **Assumption** (Phase 1 最小版本): ONNX 自测 = onnx.load() 成功 + onnxruntime.InferenceSession() 创建成功 + input/output shape 匹配。不包含推理一致性检查（属于 Phase 4）。
- **Resolution**: 使用此范围。`pytest.importorskip("onnxruntime")` 处理依赖缺失。

### HB-6: 评估 "伪指标" 定义
- **Analysis**: 当前代码无虚构数值、无重复 AP 值、无伪造统计。唯一问题是缺失指标显示 "N/A"。
- **Resolution**: 仅修复显示文案。不涉及数据模型变更。

---

## Step-by-Step Tasks

### Task 0: Fix evaluation metrics display
- **ACTION**: 替换 evaluate_workspace.py display_metrics() 中的 "N/A" 默认值
- **PRECHECK_AGENTS**: (none — 显示文案修复，无架构或安全风险)
- **IMPLEMENTATION_AGENT**: 主会话 — 修改 `evaluate_workspace.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**:
  1. 将 `metrics.get('mAP50', 'N/A')` 改为 `_NO_METRIC_TEXT if (v := metrics.get('mAP50')) is None else f"{v:.4f}"`
  2. 四行全部更新：mAP50, mAP50_95, precision, recall
  3. **关键**: 必须用 `is None` 而非 `or` — `0.0` 是有效的 mAP 值，`0.0 or fallback` 会错误显示回退文本
  4. 添加模块常量 `_NO_METRIC_TEXT = tr('未生成', 'Not generated')`
- **MIRROR**: `display_metrics()` at `evaluate_workspace.py:235-270`
- **IMPORTS**: `tr` 已导入
- **GOTCHA**: 不要改变实际指标值格式。使用 `is None` 而非 `or`（0.0 是合法 mAP 值）。已有 `test_format_metric` 导入不存在函数 — 跳过。
- **VALIDATE**: `python -m pytest tests/views/platform/test_evaluate_workspace.py -v -k "not test_format_metric"`

### Task 1: Write source binding audit tests (5 tests)
- **ACTION**: 新增测试验证 Run→Build→TaskSpec 绑定不可绕过
- **PRECHECK_AGENTS**: `tdd-guide` (来源绑定审计测试设计 + dataclass 不可变性测试策略)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (最终审查)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**:
  1. `test_train_request_requires_dataset_build`: TrainRequest 缺少 dataset_build → TypeError/ValueError
  2. `test_run_stores_dataset_build_id`: 创建 Run → Run.dataset_build_id 非空
  3. `test_evaluate_requires_run_and_build`: 验证 evaluate_tile_native() 类型签名强制 Run + DatasetBuild
  4. `test_export_requires_run_id`: 验证导出必须提供 run_id
  5. `test_run_stores_dataset_build_id_on_creation`: 创建 Run → Run.dataset_build_id 非空，验证绑定字段已写入
- **MIRROR**: `tests/platform/application/test_training_service.py`
- **IMPORTS**: `TrainRequest`, `Run`, `DatasetBuild`, `TaskSpec`, `pytest`
- **GOTCHA**: Run 是普通 dataclass（非 frozen），字段可变但绑定值在创建时写入。不需要验证不可变性，只验证值写入正确。
- **VALIDATE**: 5 个新测试通过

### Task 2: Write ONNX self-test (3 tests)
- **ACTION**: 新增 ONNX 导出后验证测试
- **PRECHECK_AGENTS**: `tdd-guide` (ONNX 测试设计 + importorskip 策略) + `security-reviewer` (ONNX 模型文件加载安全性)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (最终审查)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` + `security-reviewer`
- **IMPLEMENT**:
  1. `test_onnx_file_produced`: 模拟导出 → 验证 .onnx 文件存在 + 非空
  2. `test_onnx_loadable`: `onnx.load(model)` 成功
  3. `test_onnx_session_creatable`: `onnxruntime.InferenceSession(model)` 成功 → 检查 input/output shapes
  4. 全部使用 `pytest.importorskip("onnxruntime")` 处理依赖缺失
  5. `@pytest.mark.slow` 标记（导出耗时）
- **MIRROR**: `tests/platform/application/test_export_service.py`
- **IMPORTS**: `onnx`, `onnxruntime`, `ExportService`, `Run`, `pytest`
- **GOTCHA**: 需 ultralytics + PyTorch 环境 — CI 可能跳过但不报错
- **VALIDATE**: 3 个测试通过（或正确跳过）

### Task 3: Add E2E closed-loop smoke test
- **ACTION**: 新增 `test_e2e_01c_closed_loop_build` in test_fixtures.py
- **PRECHECK_AGENTS**: `tdd-guide` (E2E 闭环测试设计) + `security-reviewer` (数据集构建产物写入本地文件系统)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (E2E fixture 验证)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` + `security-reviewer`
- **IMPLEMENT**:
  1. 创建 3 张合成图片 + 标注
  2. 创建 TaskSpec(detection_hbb) + 标签
  3. 调用 DatasetBuildService.build(tile_plan=None)
  4. 验证: build.id, output_path, build.json 存在, data.yaml 存在, split_manifest.json 正确
- **MIRROR**: `tests/e2e/platform/test_fixtures.py` 现有 E2E-01 模式
- **IMPORTS**: `TaskSpec`, `LabelClass`, `DatasetBuildService`, `Asset`, `AnnotationDocument`, `FileImageSource`
- **GOTCHA**: training/eval/export 阶段需要子进程 + ultralytics → 不适合 fixture 测试。仅在 E2E 中覆盖数据准备→构建阶段。
- **VALIDATE**: 测试通过；完整闭环留作人工验证

### Task 4: Create ONNX self-test baseline document
- **ACTION**: 创建 `docs/baseline/onnx-self-test.md`
- **PRECHECK_AGENTS**: `doc-updater` (文档结构与可复现性审查)
- **IMPLEMENTATION_AGENT**: 主会话 — 创建 `docs/baseline/onnx-self-test.md`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `doc-updater` (验证 4 部分完整性)
- **IMPLEMENT**: 4 个部分:
  1. Prerequisites (ultralytics, onnx, onnxruntime 版本)
  2. Manual procedure (export → load → shape check → dummy inference)
  3. Known limitations (Phase 1: no inference consistency check)
  4. Pass/fail criteria
- **MIRROR**: `docs/baseline/packaging-baseline.md`
- **IMPORTS**: N/A
- **GOTCHA**: 文档应是可复现检查清单
- **VALIDATE**: 文件存在且包含所有 4 部分

---

## Testing Strategy

| Test | Input | Expected |
|---|---|---|
| display_metrics({}) | 空 dict | "未生成" 每个指标 |
| display_metrics({'mAP50': 0.0}) | mAP=0.0 | "0.0000"（不触发 fallback） |
| TrainRequest without build | missing field | 错误 |
| Run.dataset_build_id | TrainRequest with build | 等于 build.id |
| ONNX load | exported .onnx | 加载成功 |
| ONNX session create | exported .onnx | 会话创建成功 |
| E2E build smoke | 3 images + labels | build.json + data.yaml 存在 |

---

## Validation Commands

```bash
# 评估显示修复
python -m pytest tests/views/platform/test_evaluate_workspace.py -v -k "not test_format_metric"

# 来源绑定审计
python -m pytest tests/platform/application/ -v -k "bind or export or require"

# ONNX 自测（若 onnxruntime 可用）
python -m pytest tests/platform/application/test_export_service.py -v -k "onnx"

# E2E 闭环验证
python -m pytest tests/e2e/platform/test_fixtures.py -v -k "closed_loop"

# 全量回归
python -m pytest tests/ -x -m "not slow" -k "not test_format_metric"
```

---

## Acceptance Criteria
- [ ] 评估缺失指标显示 "未生成" 而非 "N/A"
- [ ] Run 记录 dataset_build_id 不可为空（测试验证）
- [ ] 评估和导出强制接受 Run + Build 参数（测试验证）
- [ ] ONNX 导出产物可被 onnxruntime 加载（测试或手动验证）
- [ ] 数据类型约束已测试确认不可绕过
- [ ] E2E 数据准备闭环测试通过
- [ ] ONNX 自测文档已创建
- [ ] 所有已有测试无回归

## Notes
- Phase 1c 重点是**审计验证**，非新功能开发
- 完整闭环 training/eval/export 阶段需要子进程 + GPU → 标记为人工验证
- ONNX 自测范围限定为加载 + shape 检查 — 一致性和精度检查是 Phase 4
