"""Tests for hdu_library_booking.cli.helpers — format_countdown 纯函数。"""

from __future__ import annotations

from hdu_library_booking.cli.helpers import format_countdown


class TestFormatCountdown:
    """format_countdown 将秒数格式化为倒计时字符串。"""

    def test_zero_seconds(self):
        assert format_countdown(0) == "00:00"

    def test_seconds_only(self):
        assert format_countdown(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert format_countdown(125) == "02:05"

    def test_exactly_one_minute(self):
        assert format_countdown(60) == "01:00"

    def test_one_hour(self):
        assert format_countdown(3600) == "01:00:00"

    def test_hours_minutes_seconds(self):
        assert format_countdown(3661) == "01:01:01"

    def test_large_value(self):
        # 10 小时 5 分 9 秒
        assert format_countdown(36309) == "10:05:09"

    def test_leading_zeros(self):
        assert format_countdown(1) == "00:01"
        assert format_countdown(600) == "10:00"

    def test_under_one_hour_no_hour_segment(self):
        """不足 1 小时不应出现小时段。"""
        result = format_countdown(3599)
        assert result == "59:59"
        assert ":" in result
        # 只有 1 个冒号（MM:SS 格式）
        assert result.count(":") == 1

    def test_exactly_on_hour_boundary(self):
        """恰好在 1 小时边界应显示小时段。"""
        assert format_countdown(3600) == "01:00:00"
        assert format_countdown(3599) == "59:59"
