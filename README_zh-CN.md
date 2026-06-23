# SBTDL Platform

离线桌面深度学习标注与训练一体化平台。

## 概述

SBTDL Platform 是基于 PyQt6 + ONNX Runtime 的跨平台离线深度学习工作台，
提供从**数据导入** → **AI 辅助标注** → **模型训练** → **评估验证** → **模型导出**的完整流水线。

## 核心功能

| 功能 | 说明 |
|------|------|
| 智能标注 | 10 种标注形状 + 87+ AI 模型自动标注 |
| 模型训练 | Ultralytics YOLO 一键训练, 5 种任务类型 |
| 模型导出 | ONNX/TensorRT/OpenVINO/CoreML 等 14 种格式 |
| 大图处理 | 网格切分 + SAM/OCR 标签分割 + 金字塔视口 |
| 数据管理 | 多格式标注导入(COCO/VOC/YOLO) + SHA-256 去重 |
| 质量评估 | 混淆矩阵 + 误分类分析 + 多模型对比 |

## 快速安装

```bash
git clone https://github.com/sfnsfnsfn/SBTDLPlatform.git
cd SBTDLPlatform

# CPU 环境
pip install -e ".[cpu,dev]"

# GPU (CUDA 12.x)
pip install -e ".[gpu,dev]"
```

## 使用方式

```bash
xanylabeling                      # 传统标注模式
xanylabeling --platform           # V4 流水线模式
xanylabeling checks               # 环境诊断
xanylabeling convert <task>       # 标签格式转换
```

## 架构导览

| 目录 | 职责 |
|------|------|
| `platform/domain/` | 不可变领域模型 (frozen dataclass) |
| `platform/application/` | 18 个用例服务 |
| `platform/infrastructure/` | ImageReader、ProcessJobRunner、原子写入 |
| `platform/adapters/` | AlgorithmRegistry + Ultralytics 适配器 |
| `services/auto_labeling/` | 87+ AI 模型 + ModelManager |
| `services/auto_training/` | YOLO 训练管线 |
| `views/labeling/` | 标注画布 + 视口 + 30+ 对话框 |
| `views/platform/` | V4 工作台 (Shell + 9 个工作区) |

## 新手入门

推荐阅读顺序：
1. `DESIGN.md` — 架构设计决策
2. `CONTRIBUTING.md` — 开发规范
3. `.tours/new-joiner-xanylabeling.tour` — 代码导览 (VS Code CodeTour 扩展)
4. `docs/CODEMAPS/architecture.md` — 架构总览
5. 其他 codemap 按需查阅

## 技术栈

Python 3.11+ / PyQt6 / ONNX Runtime / OpenCV / Shapely / Ultralytics
