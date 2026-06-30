"""
日志与进度工具。
"""

import logging
import sys
import threading
import time
from typing import ClassVar


def setup_logging(level: int = logging.INFO, log_file: str = "") -> logging.Logger:
    """配置应用日志。

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
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    root = logging.getLogger()
    root.setLevel(level)
    for h in handlers:
        h.setFormatter(fmt)
        root.addHandler(h)

    return root


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
