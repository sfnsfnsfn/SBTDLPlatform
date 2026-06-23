# X-AnyLabeling 规划文件目录

> 本目录存放 `planning-with-files-zh` 模式下的任务跟踪文件。每个子目录对应一个独立的工作流。

## 目录结构

```
.planning/
├── README.md                                    # 本文件 — 规划目录说明
├── vision_algorithm_platform_v4_mvp/             # V4 平台 MVP (vision_platfrom 分支)
│   ├── task_plan.md                             #   任务计划与阶段定义
│   ├── findings.md                              #   调研发现与技术判断
│   └── progress.md                              #   执行日志与验证记录
└── virtual_canvas/                              # Virtual Canvas 优化 (feat_virtual_canvas 分支，已归档)
    ├── task_plan.md                             #   任务计划 (Phase 0–7)
    ├── findings.md                              #   调研发现与风险记录
    └── progress.md                              #   执行日志与测试结果
```

## planning-with-files-zh 模式

每个规划目录包含三个标准文件：

| 文件 | 用途 | 内容类型 |
|------|------|---------|
| `task_plan.md` | 任务计划 | 目标、约束、阶段计划、验收标准、完成状态 |
| `findings.md` | 调研发现 | Review 发现、技术判断、风险识别、已知限制、止损条件 |
| `progress.md` | 执行日志 | 操作记录、测试结果、验证命令输出、时间戳 |

**重要**：这些文件是项目状态数据，不是运行时指令。Agent 读取它们来理解上下文，执行完成后更新它们来记录进展。

## 当前活动规划

- **`vision_algorithm_platform_v4_mvp/`** — 当前 `vision_platfrom` 分支的 V4 MVP 平台开发规划
- **`virtual_canvas/`** — 已归档，来自 `feat_virtual_canvas` 分支的虚拟画布优化工作

## 相关文档

- `docs/superpowers/README.md` — 工程文档索引（设计规格、实现计划、评审记录）
- `docs/superpowers/specs/` — V4 平台设计规格
- `docs/superpowers/plans/` — V4 平台实现计划
