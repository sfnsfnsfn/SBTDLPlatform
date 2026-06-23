# Plan: V4 平台产品化 + 图像 IO 统一化

**Branch**: `feat/dataset-scan-service`
**Status**: Phase 0–4 + unify-image-io 已完成，验证阶段进行中
**Stats**: +276 文件, +83 测试文件, +75,043 行
**Created**: 2026-06-23 | **Last Updated**: 2026-06-24

## Completed Phases

| 阶段 | 提交 | 内容 |
|------|------|------|
| Phase 0 | `d79ae933` | Freeze & Baseline — UI 控件审计, 8 条 E2E 基线 |
| Phase 1a/1b/1c | `741f3a4a` | DataWorkspace 接入, 数据集构建, ONNX 自测 |
| Phase 2a | `9af7a0e3` | Shell Skeleton — 5 域左侧导航替换 8 步水平 Pipeline |
| Phase 2b | `c5844f4e` | WorkflowState + ProjectSession + TaskCenterDrawer + ErrorBanner |
| Phase 3a | `f2e4a757` | Import Precheck Pipeline + Virtual Asset List + Multi-Facet Filtering |
| Phase 3b | `89e70c7c` | Auto-Save + Mask Brush + AI Suggestions |
| Phase 3c | `95202a59` | Tile Preview + Build History + Manifest + Leakage Detection |
| Phase 3 Suppl | `be381ea0` | Import-Annotation — 导入通道打通 + 标注伴随导入 |
| Phase 4 | `28783820` | Train + Evaluate + Validate + Deliver — 训练就绪检查 + 自动流转 |
| Unify I/O | `b638dd49` → `b7771afe` | ImageReader 统一入口 (PIL/Qt/OpenCV) + 批量迁移 |
| Review Fix | `269c5ed9` | Phase 3 三 Agent 审计修复 (10 fixes) |

## In Progress

| 任务 | 状态 |
|------|------|
| Codemap 11 文件更新 | ✅ |
| CodeTour 创建 | ✅ |
| CONTRIBUTING.md 重写 | ✅ |
| Plan 归档 (10 个→completed/) | ✅ |
| DESIGN.md 创建 | 🔧 |
| CCG tasks 初始化 | 🔧 |

## Remaining

| 任务 | 状态 |
|------|------|
| Code Review (ecc:code-review) | ❌ |
| E2E 集成测试 | ❌ |
| PR 提交 | ❌ |
