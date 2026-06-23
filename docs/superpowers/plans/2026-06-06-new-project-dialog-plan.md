# Plan: 新建项目 — 任务类型选择

**来源需求**: 当前 `_on_new_project()` 中 `TaskSpec` 硬编码，用户无法选择项目类型
**分支**: `vision_platfrom`
**复杂性**: Medium

## 需求

- 新建项目时允许用户选择任务类型：**Detection (HBB)** 和 **OBB**
- 每种类型提供合理的默认标签预设
- 用户可以编辑初始标签列表（添加/删除/重命名）

## 代码模式对照

| 类别 | 来源 | 模式 |
|---|---|---|
| 命名 | `anylabeling/views/platform/project_home.py:21` | `*Widget(QtWidgets.QWidget)` 类命名 |
| i18n | `anylabeling/views/platform/i18n.py:55` | `tr("中文", "English")` 所有 UI 字符串 |
| 错误处理 | `anylabeling/views/platform/project_home.py:180-185` | `try/except → QMessageBox.critical` |
| 信号 | `anylabeling/views/platform/project_home.py:24` | `pyqtSignal(str)` 跨组件通信 |
| 领域对象 | `anylabeling/platform/domain/task.py:18` | `@dataclass(frozen=True)` 不可变数据类 |
| 样式 | `anylabeling/views/platform/project_home.py:305-341` | 内联 QSS 样式字符串 |
| 测试 | `tests/platform/application/test_evaluation_service.py` | pytest + `unittest.mock.MagicMock` |

## 涉及文件

| 文件 | 操作 | 原因 |
|---|---|---|
| `anylabeling/views/platform/new_project_dialog.py` | CREATE | 新建项目对话框组件 |
| `anylabeling/views/platform/project_home.py` | UPDATE | 替换硬编码 TaskSpec，调用新对话框 |
| `anylabeling/views/platform/__init__.py` | UPDATE | 导出 NewProjectDialog |
| `tests/platform/views/test_new_project_dialog.py` | CREATE | 对话框单元测试 |

## 任务

### Task 1: 创建 `NewProjectDialog` 组件

- **文件**: `anylabeling/views/platform/new_project_dialog.py` (CREATE)
- **内容**:
  - `QLineEdit` — 项目名称输入
  - `QPushButton` + `QLineEdit` — 父目录选择（调用 `QFileDialog.getExistingDirectory`）
  - `QComboBox` — 任务类型下拉框（"目标检测 (HBB)" / "旋转框检测 (OBB)"）
  - `QTableWidget` — 标签编辑器（两列：ID(auto) + Name(editable)，支持添加/删除行）
  - 任务类型切换时自动替换为对应预设标签
  - 创建 / 取消按钮
  - 校验：项目名非空、目录有效、至少 1 个标签
- **预设定义**:
  - `detection_hbb`: labels=`[LabelClass(id=0, name="object")]`, metric=`map50_95`
  - `detection_obb`: labels=`[LabelClass(id=0, name="object")]`, metric=`map50_95`
- **镜像**: `project_home.py` 的样式模式、`i18n.py` 的 `tr()` 模式、`QMessageBox` 错误模式

### Task 2: 更新 `ProjectHomeWidget._on_new_project()`

- **文件**: `anylabeling/views/platform/project_home.py` (UPDATE，约 40 行替换)
- **变更**: 删除 `QInputDialog.getText` + 硬编码 `TaskSpec` 逻辑，改为弹出 `NewProjectDialog`
- **保持**: `project_opened.emit` 信号和 `_activate_project` 调用

### Task 3: 更新 `__init__.py` 导出

- **文件**: `anylabeling/views/platform/__init__.py` (UPDATE)
- **变更**: 添加 `NewProjectDialog` 到 export 列表

### Task 4: 测试

- **文件**: `tests/platform/views/test_new_project_dialog.py` (CREATE)
- **覆盖**:
  1. 对话框初始化为 Detection 类型
  2. 切换到 OBB 类型
  3. 标签预设随类型切换而更新
  4. 项目名称为空时创建被阻止
  5. 标签列表为空时创建被阻止
  6. 目录无效时创建被阻止
  7. `get_result()` 返回正确的 `(name, parent_dir, task_spec)` 元组

## 验证

```bash
python -m py_compile anylabeling/views/platform/new_project_dialog.py
python -m py_compile anylabeling/views/platform/project_home.py
python -m pytest tests/platform/views/test_new_project_dialog.py -q
python -m pytest tests/platform/ -q
```

## 风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| TaskSpec 预设与下游 TrainWorkspace 不一致 | 低 | 使用 `TaskSpec.family` 的 Literal 值 `detection_hbb` / `detection_obb`，与现有 `TASK_TYPES` 对齐 |
| 标签编辑 UI 过于复杂 | 低 | MVP 仅支持添加/删除/重命名，无需颜色/超类别 |
| 项目创建后无法修改类型 | 中 | 记录为已知限制，后续版本扩展 |

## 验收

- [ ] Task 1–4 全部完成
- [ ] 验证命令全部通过
- [ ] 模式对照表中的约定全部遵守
- [ ] GUI 手动验证：创建 Detection 项目和 OBB 项目，确认 project.json 中 task_spec.family 正确
