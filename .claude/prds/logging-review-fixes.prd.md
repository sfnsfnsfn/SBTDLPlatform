# 日志系统审查问题修复

## Problem

日志系统集成后，代码审查发现 5 个问题（2 HIGH + 3 MEDIUM）：

- `root.handlers.clear()` 会误删第三方库（Qt、onnxruntime）注册的 handler
- `--work-dir` 参数指定的工作目录未传递给日志配置，日志始终写入 `~/.xanylabeling/logs/`
- `ColoredFormatter` 等旧代码成为死代码但未清理
- 模块 docstring 缺少使用约束说明

## Evidence

代码审查报告明确列出了每个问题的文件位置、行号和影响。

## Users

- **Primary**: 开发者和用户 — 需要可靠的日志文件用于排查问题
- **Not for**: 不涉及日志系统的功能模块

## Hypothesis

我们相信**修复这 5 个问题**将**使日志系统稳定可靠且符合用户配置**。验证标准：启动应用后第三方库日志不丢失、`--work-dir` 生效、无死代码警告。

## Success Metrics

| Metric | Target | How measured |
|--------|--------|-------------|
| 第三方库日志保留 | 100% | 启动后检查日志文件包含 Qt 相关日志 |
| `--work-dir` 生效 | 是 | 指定 `--work-dir /tmp/test` 后日志写入 `/tmp/test/logs/` |
| 死代码清理 | 0 个未使用的 formatter | grep 确认 `ColoredFormatter` 无引用或标记 deprecated |

## Scope

**MVP** — 5 个文件的最小修改：

1. `logging_config.py` — 改用幂等检查替代 `handlers.clear()`
2. `app.py` — 传递 `log_dir` 参数，清理冗余 `setLevel`
3. `logger.py` — 清理或标记 `ColoredFormatter` 为 deprecated
4. `logging_config.py` — 补充 docstring 使用约束

**Out of scope**

- 新增日志 UI 配置界面 — 不在本次范围内
- 改变日志格式 — 已确定，不重复讨论
- 添加第三方日志库（loguru 等） — 已决定使用标准库

## Delivery Milestones

| # | Milestone | Outcome | Status | Plan |
|---|-----------|---------|--------|------|
| 1 | 修复 handler 清理策略 | 第三方库日志不丢失 | in-progress | `.claude/plans/logging-review-fixes.plan.md` |
| 2 | 日志目录跟随 work-dir | 用户配置生效 | in-progress | `.claude/plans/logging-review-fixes.plan.md` |
| 3 | 清理死代码 | 代码库无未使用的 formatter | in-progress | `.claude/plans/logging-review-fixes.plan.md` |
| 4 | 补充文档 | 模块使用约束明确 | in-progress | `.claude/plans/logging-review-fixes.plan.md` |

## Open Questions

- [ ] `ColoredFormatter` 是否有外部用户直接引用？如有需保留并标记 deprecated

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 清理 handler 时误删有效 handler | Low | Medium | 只移除 StreamHandler/RotatingFileHandler 类型 |
| `--work-dir` 传递时机过早 | Low | Low | 在 args 解析后调用 setup_logging |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
