"""
通知服务。

提供多渠道通知能力：控制台输出、日志文件、微信推送（可选）。
"""

import logging
from datetime import datetime

from core.metrics import ErrorCategory, error_tracker

from .base import INotificationChannel

logger = logging.getLogger(__name__)


# ======================================================================
# 控制台通知通道
# ======================================================================
class ConsoleNotification(INotificationChannel):
    """将通知打印到控制台（支持 ANSI 颜色）。"""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def __init__(self, use_colors: bool = True):
        self.colors = use_colors

    def send(self, title: str, body: str, success: bool = True) -> None:
        if self.colors:
            color = self.GREEN if success else self.RED
            print(f"\n{color}{self.BOLD}══ {title} ══{self.RESET}")
            print(f"{color}{body}{self.RESET}\n")
        else:
            print(f"\n══ {title} ══")
            print(f"{body}\n")


# ======================================================================
# 日志文件通知通道
# ======================================================================
class LogFileNotification(INotificationChannel):
    """将通知写入日志文件。"""

    def __init__(self, file_path: str = "booking.log"):
        self._path = file_path

    def send(self, title: str, body: str, success: bool = True) -> None:
        status = "SUCCESS" if success else "FAILED"
        timestamp = datetime.now().isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{status}] {title}\n")
            f.write(f"  {body}\n")
            f.write("-" * 50 + "\n")


# ======================================================================
# 微信推送通知通道 (Webhook 方式)
# ======================================================================
class WeChatNotification(INotificationChannel):
    """通过 Webhook（如 Server酱 / PushPlus）发送微信通知。

    这是可选功能（FR-6.3），需要用户自行配置 Webhook 地址。
    """

    def __init__(self, webhook_url: str | None = None):
        self.url = webhook_url

    def send(self, title: str, body: str, success: bool = True) -> None:
        if not self.url:
            return
        try:
            import requests

            requests.post(
                self.url,
                json={"title": title, "content": body},
                timeout=10,
            )
        except Exception:
            error_tracker.record(
                ErrorCategory.NOTIFICATION,
                "微信推送失败",
                module=__name__,
            )
            logger.warning("微信推送失败，已忽略", exc_info=True)


# ======================================================================
# 通知聚合器 (Composite Pattern)
# ======================================================================
class NotificationAggregator(INotificationChannel):
    """聚合多个通知通道，一次发送广播到所有通道。"""

    def __init__(self, channels: list[INotificationChannel] | None = None):
        self.channels: list[INotificationChannel] = channels or []

    def add_channel(self, channel: INotificationChannel) -> None:
        self.channels.append(channel)

    def send(self, title: str, body: str, success: bool = True) -> None:
        for ch in self.channels:
            try:
                ch.send(title, body, success)
            except Exception:
                error_tracker.record(
                    ErrorCategory.NOTIFICATION,
                    f"通知通道 {type(ch).__name__} 发送失败",
                    module=__name__,
                )
                logger.warning(f"通知通道 {type(ch).__name__} 发送失败", exc_info=True)
