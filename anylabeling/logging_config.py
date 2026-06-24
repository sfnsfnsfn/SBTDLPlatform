"""集中式日志配置 — 应用启动时调用一次 setup_logging()。

所有模块使用标准 ``logging.getLogger(__name__)`` 获取 logger，
无需额外配置即可自动继承全局设置。

注意: 不要在模块中创建独立的 handler，所有 handler 由 setup_logging() 统一管理。
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_DEFAULT_LOG_DIR = Path.home() / ".xanylabeling" / "logs"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 5
_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s:%(lineno)d"
    " - %(message)s"
)
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_dir: str | Path | None = None,
    app_name: str = "xanylabeling",
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> Path:
    """初始化全局日志配置（幂等，可安全重复调用）。

    Args:
        level: 根日志级别（如 ``logging.INFO``）。
        log_dir: 日志文件目录，默认 ``~/.xanylabeling/logs/``。
        app_name: 日志文件名前缀。
        max_bytes: 单个日志文件最大字节数，默认 10 MB。
        backup_count: 轮转备份数量，默认 5。

    Returns:
        日志文件路径。
    """
    root = logging.getLogger()

    # 幂等检查：防止重复初始化，保留第三方库的 handler
    if getattr(root, '_xanylabeling_configured', False):
        return Path(getattr(root, '_xanylabeling_log_file', _DEFAULT_LOG_DIR / f"{app_name}.log"))

    root.setLevel(level)
    root._xanylabeling_configured = True

    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)

    # 控制台 handler（stderr）
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # 文件 handler（轮转）
    log_dir = Path(log_dir) if log_dir is not None else _DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{app_name}.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # 存储日志文件路径，供幂等检查返回
    root._xanylabeling_log_file = log_file

    return log_file


__all__ = ["setup_logging"]
