# X-AnyLabeling 工程文档索引

> 本目录存放 V4 视觉算法平台 (`vision_platfrom`) 的设计规格、实现计划和评审记录。

## 目录结构

```
docs/superpowers/
├── README.md                          # 本文件 — 文档索引
├── specs/                             # 设计规格文档
│   ├── 2026-06-06-vision-algorithm-platform-design.md                  # V4 平台总体设计
│   ├── 2026-06-06-vision-algorithm-platform-design-v4-mvp-foundation.md # V4 MVP 基础设计
│   ├── 2026-06-06-vision-algorithm-platform-v4-mvp-contract.md         # V4 MVP 接口契约
│   ├── 2026-06-06-platform-defect-analysis.md                           # V4 平台缺陷分析报告
│   └── 2026-06-05-pyqtgraph-canvas-design.md                           # pyqtgraph 画布方案设计
├── plans/                             # 实现计划文档
│   ├── 2026-06-06-vision-algorithm-platform-v4-mvp-foundation-implementation.md # V4 MVP 基础实现计划
│   ├── 2026-06-06-new-project-dialog-plan.md                            # 新建项目任务类型选择
│   ├── 2026-06-05-pyqtgraph-canvas-phase-a.md                         # pyqtgraph 画布 Phase A 计划
│   └── AGENTS_vision_algorithm_platform_canvas_baseline.md             # 画布性能基线报告 (M2.1)
└── reviews/                           # 评审文档
    └── vision_platform_review_checklists.md                            # V4 平台评审检查清单
```

## 文档分类说明

### specs/ — 设计规格

定义"做什么"和"为什么"。包含架构决策、技术方案对比、接口约定、风险分析等。

### plans/ — 实现计划

定义"怎么做"。包含任务分解、阶段划分、验收标准、工程师分配等可执行的实现指导。

### reviews/ — 评审记录

记录代码评审检查清单、质量门禁结果、安全审计发现等。

## 相关文档

- **用户文档**: `docs/zh_cn/vision_platform_v4_user_guide.md` — V4 平台用户指南
- **规划跟踪**: `.planning/vision_algorithm_platform_v4_mvp/` — V4 MVP 任务跟踪
- **旧画布工作**: `.planning/virtual_canvas/` — `feat_virtual_canvas` 分支归档

## 命名约定

- 文件名前缀为日期 (`YYYY-MM-DD-`)，便于按时间排序
- 语言：技术文档使用中文，代码标识符保持英文
