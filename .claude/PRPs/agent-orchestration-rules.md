# Agent Orchestration Rules

> **Status**: 强制 — 所有 `.claude/PRPs/plans/*.plan.md` 必须包含此编排规则。新生成的 Plan 以此为基准模板。

---

## Agent Orchestration

### Core Rules (21 条铁律)

1. 主会话负责整体调度和最终决策，不得独自完成全部分析+实现+审查。
2. 每个 Task 开始前必须调用该 Task 的 PRECHECK_AGENTS。
3. 需要架构判断时调用 `architect`。
4. 新功能或 Bug 修复必须先调用 `tdd-guide`。
5. 生产代码默认由主会话串行写入。
6. `tdd-guide` 只有在 WRITE_SCOPE 明确包含测试文件时，才能修改测试文件。
7. 完成 Python 修改后必须调用 `python-reviewer`。
8. 完成 C++ 修改后必须调用 `cpp-reviewer`（本项目为纯 Python，不使用）。
9. 每个 Task 完成后必须调用 `code-reviewer`。
10. 涉及文件路径、子进程、模型加载、用户输入和本地数据时，必须调用 `security-reviewer`。
11. 构建失败时调用对应 `build-error-resolver` 分析根因。
12. 所有专业 Agent 必须返回结构化报告。
13. 审核 Agent 默认只读，不允许直接修改源码。
14. 主会话根据专业 Agent 报告实施修复。
15. 禁止两个 Agent 同时修改同一个文件。
16. 独立只读分析可以并行。
17. 写入任务必须串行。
18. 任何 Agent 不得执行 `git push`, `merge`, `rebase`, `reset`, `clean`。
19. 提交仅由主会话在 Phase 完成后统一执行。
20. Auto 模式只用于权限自动判断，不得替代 Agent 编排。
21. 最终 Implementation Report 必须增加 Agent Execution Log。

### Agent Assignment

| Agent | Role | Scope | Available |
|-------|------|-------|:---:|
| `architect` | 架构审查 | 系统设计、页面接线、API 契约、数据模型 | ✅ |
| `tdd-guide` | 测试驱动 | 新功能测试先行、测试用例设计、80% 覆盖率验证 | ✅ |
| `code-reviewer` | 代码审查 | 每个 Task 完成后强制审查 | ✅ |
| `python-reviewer` | Python 审查 | PEP 8 合规、Python 惯用法、项目规范合规 | ✅ |
| `security-reviewer` | 安全审查 | 路径处理、子进程、模型加载、文件 I/O、用户输入 | ✅ |
| `build-error-resolver` | 构建修复 | 构建/导入错误根因分析 | ✅ |
| `doc-updater` | 文档 | 文档更新和同步（按需） | ✅ |

### EXECUTION_MODE

**Sequential** — Task 串行执行。

每个 Task 内部：
- **PRECHECK** Agent 可并行调用（只读互不干扰）
- **IMPLEMENT** 由主会话串行写入（同一时间只有一个写入者）
- **POST_REVIEW** Agent 可并行调用（只读互不干扰）

### WRITE_SCOPE

| Agent | Permitted Files | Constraint |
|--------|-----------------|------------|
| 主会话 | `anylabeling/` 下所有源码 + `docs/` 下文档 | 生产代码与文档唯一写入者 |
| `tdd-guide` | `tests/` 下测试文件 | 仅限测试文件，不得修改生产代码 |
| `architect` | 只读 | 不得修改任何文件 |
| `code-reviewer` | 只读 | 不得修改任何文件 |
| `python-reviewer` | 只读 | 不得修改任何文件 |
| `security-reviewer` | 只读 | 不得修改任何文件 |
| `build-error-resolver` | 只读 | 建议修复方案，不直接修改 |
| `doc-updater` | `docs/` 下文档文件 | 仅限文档，不得修改源码 |

### Agent Execution Log（Implementation Report 中）

| Task | Agent | 阶段 | 输出摘要 | 是否采纳 | 验证结果 |
|------|-------|------|----------|----------|----------|
| T0 | architect | PRECHECK | ... | ✅/❌ | 通过/失败 |
| T0 | tdd-guide | PRECHECK | ... | ✅/❌ | 通过/失败 |
| T0 | 主会话 | IMPLEMENT | ... | — | — |
| T0 | code-reviewer | POST_REVIEW | ... | ✅/❌ | 通过/失败 |
| T0 | python-reviewer | POST_REVIEW | ... | ✅/❌ | 通过/失败 |
| ... | ... | ... | ... | ... | ... |

### Task 级 Agent 标注格式

每个 Task 必须包含：

```markdown
### Task N: Name
- **PRECHECK_AGENTS**: architect (理由) + tdd-guide (理由) + security-reviewer (理由)
- **IMPLEMENTATION_AGENT**: 主会话 — 具体任务
- **POST_REVIEW_AGENTS**: code-reviewer + python-reviewer + security-reviewer
- **ACTION**: ...
```

**PRECHECK 分配指南**:
- 涉及新类/API/服务/页面接线 → +`architect`
- 涉及新功能/新测试/行为变更 → +`tdd-guide`
- 涉及路径/子进程/文件I/O/用户输入 → +`security-reviewer`
- 无风险的单行删除/注释/常量变更 → 可省略 PRECHECK
- 始终至少包含 1 个 PRECHECK Agent 或明确标注 `(none — reason)`

**POST_REVIEW 分配指南**:
- 每个 Task 完成后至少调用 `code-reviewer`
- Python 源码变更 → +`python-reviewer`
- 安全相关变更 → +`security-reviewer`
- 文档变更 → +`doc-updater`
