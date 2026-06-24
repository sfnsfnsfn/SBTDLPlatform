<!-- Generated: 2026-06-25 | Files scanned: 523 | Token estimate: ~850 | Updated: dead code cleanup -->

# 数据集 — 构建与预处理 (Dataset)

## 领域模型

| 类型 | 文件 |
|------|------|
| `TaskSpec` (frozen) — family (5 types), labels, primary_metric | `platform/domain/task.py` |
| `DatasetBuild` (frozen) — split_seed, split_strategy, tile_plan, adapter_id | `platform/domain/dataset.py` |
| `SplitManifest` (frozen) — strategy, ratios, seed, asset_assignments | `platform/domain/split_manifest.py` |
| `PreprocessConfig` (frozen) — 16 params, estimate_tiles() | `platform/domain/preprocess_config.py` |
| `DatasetBuildRecord` (frozen) — SQLite 持久化 | `platform/domain/records.py` |
| `AssetRecord` (frozen) — SQLite 持久化 | `platform/domain/records.py` |
| `AnnotationSummaryRecord` (frozen) — SQLite 持久化 | `platform/domain/records.py` |

## SQLite 仓储

| 仓储 | 文件 | 方法 |
|------|------|------|
| `SQLiteAssetRepository` | `infrastructure/sqlite_repositories/assets.py` | upsert, get, list, stats, mark_deleted |
| `SQLiteAnnotationRepository` | `infrastructure/sqlite_repositories/annotations.py` | upsert_summary, get_by_asset, count_annotated, label_histogram |
| `SQLiteDatasetBuildRepository` | `infrastructure/sqlite_repositories/dataset_builds.py` | create, mark_running, mark_completed, mark_failed |

全部通过 `ProjectContext` 统一组装，使用 `UnitOfWork` 管理事务。

## DatasetBuildService (`platform/application/dataset_build_service.py`, 895L)

```
build(task_spec, assets, annotations, tile_plan=None, image_sources=None)
  → _assign_splits()           ← random_by_asset / group_by_group_id
  → _detect_leakage()          ← 跨分割数据泄露检测
  → _write_yolo_labels()       ← 归一化 bboxes (YOLO .txt)
  → _write_data_yaml()         ← 数据集配置文件
  → _write_split_manifest()    ← 资产→分割 映射 (JSONL)
  → _write_tile_manifest()     ← 切片→资产/分割 映射 (JSONL)
  → _write_build_json()        ← 构建元数据
  → _write_manifest()          ← ManifestStore 持久化
  → return DatasetBuild
```

## 标注格式支持

| 格式 | 枚举值 | 导入 | 导出 | 几何类型 |
|------|--------|------|------|----------|
| X-AnyLabeling (JSON) | `"xanylabel"` | ✅ | ✅ | 全部 |
| COCO JSON | `"coco"` | ✅ | ✅ | bbox_xyxy |
| YOLO .txt | `"yolo"` | ✅ | ✅ | bbox_xyxy, obb, pose, seg |
| Pascal VOC XML | `"voc"` | ✅ | ✅ | bbox_xyxy |

## 编解码器 (`platform/application/codecs/`)

| 编解码器 | 文件 | 解析方式 |
|----------|------|----------|
| `YOLOCodec` | `yolo_codec.py` | 5-字段归一化 bbox, 9-字段 OBB, 6+-字段 pose |
| `COCOCodec` | `coco_codec.py` | COCO JSON: images/annotations/categories |
| `VOCCodec` | `voc_codec.py` | Pascal VOC XML: `<object><bndbox>` |

## ImportService (`platform/application/import_service.py`)

### 导入流水线

1. **预检阶段**: 扫描源文件, 验证扩展名, 通过 `ImageReader.metadata()` 验证图像可读性, 检测大图 (>2000px)
2. **导入阶段**: SHA-256 去重复制到 `assets/`, 分配稳定 asset_id, 检测大图, 进度回调, 支持取消 (threading.Event)
3. **标注导入** (`import_with_annotations()`): 按格式路由到对应编解码器, 标签映射, 写入 `annotations/<stem>.json`

### ImportWorkspace UI (`views/platform/workspaces/import_workspace.py`, 803L)

非模态 QWidget 页面:
- 添加源 (文件/目录) → "预检" 按钮 (QThread worker)
- 结果展示: 有效/损坏/不支持/过大 计数
- 导入规则: 去重复选框, 按文件夹分组
- **标注格式选择器**: None / X-AnyLabeling / YOLO / COCO / Pascal VOC
- 条件标注路径输入 (格式特定过滤: .json for COCO, 目录 for YOLO/VOC)
- **预览面板**: 扫描标注源并显示类别统计
- 进度条 + 取消按钮
- 完成报告 (导入/大图/重复/错误计数)
- 信号: `import_completed(ImportResult)`, `asset_repository_changed()`

## 数据泄露检测

`DatasetBuildService.detect_leakage()`:
- 检查 `split_manifest.jsonl` 中出现在多个分割的组
- 分析 YOLO 标签文件的类别分布
- 通过 `LeakageReport` 报告类别不平衡警告

## 构建完整性验证

`DatasetBuildService.verify_build_integrity()`:
- 读取 `build.json` 获取预期 manifest 哈希
- 重新哈希磁盘上的 manifest 文件
- 返回 `ManifestIntegrityReport` (损坏/缺失文件列表)

## PreprocessWorkspace (`views/platform/preprocess_workspace.py`, 310L)

- 切片大小 (64–4096), 重叠 (0–2048), 边缘模式 (crop/pad)
- 实时切片数量预览
- 分割比例: train/val/test + 随机种子
- 数据增强复选框: H-flip, V-flip, brightness, rotation (⚠️ 仅 UI, 无实际逻辑)
- TilePreviewWidget: 源图像上的可视化切片网格叠加
- TileInspectorPanel: 逐切片详细信息 + 标签分布
- 构建历史面板 (ManifestStore)

## 项目存储结构

```
<project_root>/
├── project.json           # 元数据: name, version, task_spec
├── labels.json            # 标签唯一真实来源: [{id, name}]
├── assets/                # 已复制的图像文件 (SHA-256 去重)
├── annotations/           # <stem>.json 标注文件
├── dataset_builds/        # 数据集构建输出
├── jobs/                  # 作业工作目录
├── runs/                  # 训练运行记录
├── evaluations/           # 评估结果
├── models/                # 导出的模型产物
├── cache/                 # 缓存文件
└── logs/                  # 日志文件
```

## 实现状态

| 功能 | 状态 |
|------|------|
| TaskSpec + DatasetBuild 领域模型 | ✅ |
| DatasetBuildService YOLO 输出 | ✅ |
| 4 种标注格式导入/导出 | ✅ |
| SHA-256 去重导入 | ✅ |
| ImportWorkspace 完整 UI | ✅ |
| PreprocessWorkspace UI | ✅ |
| 数据泄露检测 | ✅ |
| 构建完整性验证 | ✅ |
| ManifestStore 构建历史 | ✅ |
| 数据增强 (实际效果) | ❌ 仅 UI 复选框, 无逻辑 |
| 端到端管线 | ⚠️ 可运行但未充分测试 |
