"""Tests for hdu_library_booking.services.notifications — notification channels."""

import os
import tempfile

from hdu_library_booking.services.interfaces import INotificationChannel
from hdu_library_booking.services.notifications import (
    ConsoleNotification,
    LogFileNotification,
    NotificationAggregator,
    WeChatNotification,
)


class TestConsoleNotification:
    def test_implements_interface(self):
        assert isinstance(ConsoleNotification(), INotificationChannel)

    def test_send_success(self, capsys):
        notifier = ConsoleNotification(use_colors=False)
        notifier.send("成功", "预约完成", success=True)
        captured = capsys.readouterr()
        assert "成功" in captured.out

    def test_send_failure(self, capsys):
        notifier = ConsoleNotification(use_colors=False)
        notifier.send("失败", "预约失败", success=False)
        captured = capsys.readouterr()
        assert "失败" in captured.out

    def test_colors_enabled(self, capsys):
        notifier = ConsoleNotification(use_colors=True)
        notifier.send("测试", "内容", success=True)
        captured = capsys.readouterr()
        # 应包含 ANSI 转义码
        assert "\033" in captured.out


class TestLogFileNotification:
    def test_send_writes_to_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            notifier = LogFileNotification(path)
            notifier.send("测试标题", "测试正文", success=True)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "测试标题" in content
            assert "测试正文" in content
            assert "SUCCESS" in content
        finally:
            os.unlink(path)

    def test_send_failure_writes_to_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            notifier = LogFileNotification(path)
            notifier.send("失败通知", "错误详情", success=False)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "FAILED" in content
        finally:
            os.unlink(path)


class TestWeChatNotification:
    def test_empty_url_does_nothing(self):
        """无 webhook URL 时，send 应为空操作。"""
        notifier = WeChatNotification()
        # 不应抛出异常
        notifier.send("title", "body", success=True)

    def test_send_with_url_no_error(self):
        """有 URL 时发送不应抛出异常（即使网络不可达）。"""
        notifier = WeChatNotification("https://example.com/webhook")
        # 实际网络调用会失败但被静默忽略
        notifier.send("test", "body", success=True)


class TestNotificationAggregator:
    def test_empty_aggregator(self):
        """无通道的聚合器不应抛出异常。"""
        agg = NotificationAggregator()
        agg.send("title", "body")

    def test_multiple_channels(self, capsys):
        agg = NotificationAggregator()
        agg.add_channel(ConsoleNotification(use_colors=False))
        agg.add_channel(ConsoleNotification(use_colors=False))
        agg.send("测试", "消息", success=True)
        captured = capsys.readouterr()
        # 两条通道都输出了
        assert captured.out.count("测试") == 2

    def test_channel_error_does_not_block_others(self, capsys):
        """一个通道出错不影响其他通道。"""

        class BadChannel(INotificationChannel):
            def send(self, title, body, success=True):
                raise RuntimeError("boom")

        agg = NotificationAggregator()
        agg.add_channel(BadChannel())
        agg.add_channel(ConsoleNotification(use_colors=False))
        # 不应抛出异常
        agg.send("测试", "消息")
        captured = capsys.readouterr()
        assert "测试" in captured.out

    def test_add_channel_fluent(self):
        agg = NotificationAggregator()
        agg.add_channel(ConsoleNotification())
        assert len(agg.channels) == 1
