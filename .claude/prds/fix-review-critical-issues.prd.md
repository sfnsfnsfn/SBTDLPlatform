# Fix P0-P4 Review Critical Issues

## Problem
6月24日 V4 平台产品化代码审查发现 **7 CRITICAL + 17 HIGH** 问题。核心症状：DB 镜像链路的 3 处 wiring 死代码导致 SQLite 持久化完全失效，JobService/WorkflowState/四个 UI 工作区的 DB 路径全部是 dead code。数据正确性方面存在 payload_json 格式错误、manifest_hash 永久为空等 bug。若不合入修复，用户所有操作仅在文件系统生效，SQLite 数据库保持空白。

## Evidence
- 5 个独立 python-reviewer 交叉验证的审查报告
- `SQLiteWorkflowQuery` 创建于 `project_context.py:55` 但从未传给 `WorkflowState`
- `JobService(jobs_root)` 缺少 `context=self`，4 个 DB 镜像方法全部是 no-op
- 4/5 工作区未调用 `set_context()`
- `payload_json=str(request.params)` 产出非法 JSON（单引号）
- `manifest_hash=""` 在 `mark_completed()` 中永远不会被更新

## Users
- **Primary**: X-AnyLabeling 平台用户 — 期望 project.sqlite 正确记录所有操作历史
- **Not for**: 使用旧版 `--legacy` 模式的用户（纯文件系统，不涉及 DB）

## Hypothesis
We believe **修复 3 处 wiring 死代码 + 4 处数据正确性 bug + 一致性保护** will **使 DB 镜像链路从全部失效变为完整工作** for **平台用户**.
We'll know we're right when **P0-P4 全部修复后，14 个相关测试 + e2e smoke test 全部通过**.

## Success Metrics
| Metric | Target | How measured |
|---|---|---|
| DB wiring 激活 | 3/3 wiring fixes done | pytest 相关测试通过 |
| 数据正确性 | 0 data corruption bugs | json.dumps / manifest_hash 校验 |
| 测试通过率 | 100% (14 test files) | `pytest -m "not slow" -x` |
| 无回归 | 0 存量测试失败 | 全量 pytest |

## Scope
**MVP** — P0 (3 wiring fixes, ~5行) + P1 (4 data correctness fixes, ~30行)
修复后 DB 镜像链路可工作，数据格式正确。

**Out of scope**
- 存量代码重构（dataset_build_service 拆分为更小文件） — 风险高，独立 PR
- 新功能添加 — 本次仅修复
- 测试覆盖率提升（已有 14 个新测试文件覆盖核心路径）
- UI 样式/布局改动

## Delivery Milestones
| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | P0: 激活 DB 链路 | WorkflowState/JobService/4工作区 DB 路径可用 | pending | — |
| 2 | P1: 数据正确性 | payload_json 合法、manifest_hash 写入、list_failed() 替代原始 SQL | pending | — |
| 3 | P2: 数据一致性 | 孤儿资源清理、状态同步、操作顺序修正 | pending | — |
| 4 | P3: 资源管理+线程安全 | close() 取消子进程、DB 加锁、GUI 错误边界 | pending | — |
| 5 | P4: 代码质量 | 死代码删除、类型注解、命名修复、输入验证 | pending | — |

## Open Questions
- [ ] P2 操作顺序调整后是否需要新增测试覆盖异常路径？→ TBD 执行时评估

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| P0 激活后暴露下游 bug | Medium | High | 每级修复后立即跑测试 |
| P2 重排序改变异常语义 | Low | Medium | 独立 commit，便于 bisect |
| P3 加锁影响 GUI 响应 | Low | Low | SQLite 写入微秒级，实测验证 |
| 修复与未提交文件冲突 | Low | Medium | 使用 worktree 隔离 |

---
*Status: DRAFT — P0 execution starting immediately via workflow.*
