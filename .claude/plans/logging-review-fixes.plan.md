# Plan: 日志系统审查问题修复

**Source PRD**: `.claude/prds/logging-review-fixes.prd.md`
**Selected Milestone**: All (4 milestones, single delivery)
**Complexity**: Small

## Summary

修复日志系统代码审查发现的 5 个问题（2 HIGH + 3 MEDIUM）：handler 清理策略、日志目录路径、死代码清理和文档补充。共修改 2 个文件，无新增文件。

## Patterns to Mirror

| Category | Source | Pattern |
|----------|--------|---------|
| Logging | `anylabeling/logging_config.py` | 使用 `logging.getLogger(__name__)` 获取 logger |
| Config | `anylabeling/app.py:229` | 通过 `args.work_dir` 传递工作目录 |
| Docstring | `anylabeling/logging_config.py` | Google-style docstring |

## Files to Change

| File | Action | Why |
|------|--------|-----|
| `anylabeling/logging_config.py` | UPDATE | H1: 幂等检查替代 `handlers.clear()`; M3: 补充 docstring |
| `anylabeling/app.py` | UPDATE | H2: 清理冗余 `setLevel`; M2: 传递 `log_dir` |
| `anylabeling/views/labeling/logger.py` | UPDATE | M1: 标记 `ColoredFormatter` 为 deprecated |

## Tasks

### Task 1: 修复 handler 清理策略 (H1)

- **Action**: 在 `setup_logging()` 中用幂等检查替代 `root.handlers.clear()`
- **Mirror**: 使用 `getattr(root, '_xanylabeling_configured', False)` 标记
- **Validate**: 启动应用后日志文件包含 Qt 相关日志

```python
# logging_config.py:43-47 — 替换为：
root = logging.getLogger()
if getattr(root, '_xanylabeling_configured', False):
    return log_file  # 已初始化，直接返回
root.setLevel(level)
root._xanylabeling_configured = True
# ... 后续 handler 注册不变
```

### Task 2: 日志目录跟随 work-dir (M2)

- **Action**: `app.py` 中将 `args.work_dir` 传递给 `setup_logging(log_dir=...)`
- **Mirror**: 参考 `app.py:229` 的 `set_work_directory(args.work_dir)` 模式
- **Validate**: 指定 `--work-dir /tmp/test` 后日志写入 `/tmp/test/logs/`

```python
# app.py:305-309 — 修改为：
from pathlib import Path
setup_logging(level=log_level, log_dir=Path(get_work_directory()) / "logs")
```

### Task 3: 清理冗余 setLevel (H2)

- **Action**: 移除 `app.py:311` 的 `logger.setLevel(log_level)`，或添加注释说明
- **Mirror**: 根 logger 级别已在 `setup_logging()` 中设置
- **Validate**: 日志输出级别正确

### Task 4: 标记 ColoredFormatter 为 deprecated (M1)

- **Action**: 在 `logger.py` 中为 `ColoredFormatter` 和 `COLORS` 添加 deprecation 注释
- **Mirror**: Python 标准 deprecation 注释风格
- **Validate**: grep 确认 `ColoredFormatter` 仅在 `logger.py` 内部定义

```python
# logger.py:8 — 添加注释
# @deprecated — 已由 anylabeling.logging_config 全局配置替代
COLORS: Dict[str, str] = { ... }

# logger.py:29 — 添加注释
# @deprecated — 已由 anylabeling.logging_config 全局配置替代
class ColoredFormatter(logging.Formatter):
    ...
```

### Task 5: 补充 docstring 使用约束 (M3)

- **Action**: 在 `logging_config.py` 模块 docstring 中添加使用约束说明
- **Mirror**: 现有 docstring 风格
- **Validate**: docstring 包含"不要创建独立 handler"的说明

```python
# logging_config.py:1-5 — 扩展为：
"""集中式日志配置 — 应用启动时调用一次 setup_logging()。

所有模块使用标准 ``logging.getLogger(__name__)`` 获取 logger，
无需额外配置即可自动继承全局设置。

注意: 不要在模块中创建独立的 handler，所有 handler 由 setup_logging() 统一管理。
"""
```

## Validation

```bash
# 1. 测试日志配置
python -c "from anylabeling.logging_config import setup_logging; import logging; setup_logging(); logging.getLogger('test').info('OK')"

# 2. 检查日志文件生成
cat ~/.xanylabeling/logs/xanylabeling.log

# 3. 检查 ColoredFormatter 无外部引用
grep -r "ColoredFormatter" anylabeling/ --include="*.py" | grep -v "logger.py"

# 4. 运行平台测试
pytest tests/platform/ -x -q
```

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| 幂等检查标记污染根 logger | Low | 使用 `_xanylabeling_configured` 私有属性 |
| `--work-dir` 在 args 解析前调用 | Low | `setup_logging` 已在 args 解析后调用 |

## Acceptance

- [ ] H1: `root.handlers.clear()` 已替换为幂等检查
- [ ] H2: 冗余 `logger.setLevel()` 已清理或注释
- [ ] M1: `ColoredFormatter` 已标记 deprecated
- [ ] M2: `--work-dir` 参数传递给 `setup_logging`
- [ ] M3: docstring 包含使用约束说明
- [ ] 验证通过：日志文件生成、格式正确、平台测试通过
