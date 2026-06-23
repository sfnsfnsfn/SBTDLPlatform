# SBTDL Platform

离线桌面深度学习标注与训练一体化平台。

## 概述

SBTDL Platform 是基于 PyQt6 + ONNX Runtime 的 Windows/Linux/macOS 离线深度学习平台，
集成**图像标注**、**AI 辅助标注**（87+ 种模型）、**模型训练**、**评估验证**、**模型导出**全流程。

## 特性

- **双模式工作台**: 传统快速标注模式 + V4 5 域流水线模式
- **87+ AI 模型**: YOLO 全系列(v5-v12, v26)、SAM v1/v2/v3、Grounding DINO、Florence-2、PaddleOCR 等
- **一键训练**: Ultralytics YOLO 5 种任务 (Classify/Detect/OBB/Segment/Pose)
- **14 种导出格式**: ONNX、TensorRT、OpenVINO、CoreML、TFLite 等
- **大图支持**: 规则网格切分 + 5 种标签分割器 + 金字塔视口渲染
- **完全离线**: 无需网络、无需数据库、无需云服务

## 快速开始

```bash
# 安装 (Python >=3.11)
pip install -e ".[cpu,dev]"

# 启动
xanylabeling                 # 传统标注模式
xanylabeling --platform      # V4 平台流水线模式
xanylabeling checks          # 系统诊断
```

## 架构

```
anylabeling/
├── platform/        DDD四层: domain → application → infrastructure → adapters
├── services/        AI推理(87+模型) + YOLO训练管线
├── views/           PyQt6 GUI: 标注画布 + V4平台工作台
├── configs/         模型配置(~365 YAML)
└── tools/           CLI工具 + ONNX导出器
```

## 文档

| 文档 | 说明 |
|------|------|
| `DESIGN.md` | 架构设计决策 |
| `CONTRIBUTING.md` | 贡献指南 |
| `docs/CODEMAPS/` | 11 个子系统架构详解 |
| `.tours/` | VS Code CodeTour 新人导览 |

## 平台支持

Windows 10+ / Linux (Ubuntu 20.04+) / macOS 12+
CPU 推理 (onnxruntime) 或 GPU 推理 (onnxruntime-gpu, CUDA 11.x/12.x)
