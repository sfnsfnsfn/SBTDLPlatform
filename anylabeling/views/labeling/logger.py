import logging
import sys
from functools import wraps
from typing import Callable, Dict

import termcolor

# @deprecated — 已由 anylabeling.logging_config 全局配置替代
COLORS: Dict[str, str] = {
    "WARNING": "yellow",
    "INFO": "white",
    "DEBUG": "blue",
    "CRITICAL": "red",
    "ERROR": "red",
}


def singleton(cls):
    instances = {}

    @wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance


# @deprecated — 已由 anylabeling.logging_config 全局配置替代
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt: str, use_color: bool = True):
        super().__init__(fmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if self.use_color and record.levelname in COLORS:
            record = self._color_record(record)
        record.asctime = self.formatTime(record, self.datefmt)
        return super().format(record)

    def _color_record(self, record: logging.LogRecord) -> logging.LogRecord:
        def colored(text, color):
            return termcolor.colored(text, color=color, attrs={"bold": True})

        record.levelname2 = colored(
            f"{record.levelname:<7}", COLORS[record.levelname]
        )
        record.message2 = colored(record.msg, COLORS[record.levelname])
        record.asctime2 = termcolor.colored(
            self.formatTime(record, self.datefmt), color="green"
        )
        record.module2 = termcolor.colored(record.module, color="cyan")
        record.funcName2 = termcolor.colored(record.funcName, color="cyan")
        record.lineno2 = termcolor.colored(record.lineno, color="cyan")

        return record


@singleton
class AppLogger:
    def __init__(self, name="X-AnyLabeling"):
        self.logger = logging.getLogger(name)
        # 允许日志传播到根 logger，由全局配置统一处理
        self.logger.propagate = True
        self._setup_handler()

    def _setup_handler(self):
        # 不再添加独立 handler，使用全局日志配置（anylabeling.logging_config）
        pass

    def __getattr__(self, name: str) -> Callable:
        return getattr(self.logger, name)

    def set_level(self, level: str):
        self.logger.setLevel(level)


logger = AppLogger()
