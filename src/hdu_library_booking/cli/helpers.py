"""
日志与进度工具。

提供结构化日志配置（基于 structlog）和终端进度动画。

setup_logging() 保留为向后兼容的委托函数，新代码应使用
core.observability.configure_logging()。
"""

import logging
import sys
import threading
import time
from typing import ClassVar


def setup_logging(level: int = logging.INFO, log_file: str = "") -> logging.Logger:
    """配置应用日志（向后兼容委托）。

    新代码请使用 ``core.observability.configure_logging()``。

    Parameters
    ----------
    level : int
        日志级别。
    log_file : str
        日志文件路径；空字符串表示仅控制台输出。

    Returns
    -------
    logging.Logger
        根 logger。
    """
    from core.observability import configure_logging

    level_name = logging.getLevelName(level)
    configure_logging(level=level_name, log_file=log_file, json_format=False)

    return logging.getLogger()


# ======================================================================
# 简单的进度动画
# ======================================================================
class ProgressSpinner:
    """终端旋转进度指示器。"""

    SPINNER: ClassVar[list[str]] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "处理中"):
        self.message = message
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, done_message: str = "") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # 清除当前行
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        if done_message:
            sys.stdout.write(f"{done_message}\n")
        sys.stdout.flush()

    def _spin(self) -> None:
        idx = 0
        while self._running:
            symbol = self.SPINNER[idx % len(self.SPINNER)]
            sys.stdout.write(f"\r{symbol} {self.message}...")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)


def format_countdown(seconds: int) -> str:
    """将秒数格式化为倒计时字符串。"""
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
