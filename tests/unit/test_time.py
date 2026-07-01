"""Tests for hdu_library_booking.models — time utilities, plan parsing, booking helpers."""

from datetime import datetime, time
from unittest.mock import patch

import pytest

from hdu_library_booking.models import (
    booking_failed,
    booking_message,
    build_begin_time,
    build_execute_datetime,
    get_seat_lookup_time,
    is_time_out_of_range,
    normalize_execute_time,
    now_cst,
    parse_execute_time,
    parse_plan_code,
)


class TestNowCst:
    def test_returns_datetime(self):
        result = now_cst()
        assert isinstance(result, datetime)


class TestBuildBeginTime:
    def test_today(self):
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 10, 30, 0)
            result = build_begin_time(13, book_days=0)
            assert result.hour == 13
            assert result.minute == 0
            assert result.day == 30

    def test_tomorrow(self):
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 10, 0, 0)
            result = build_begin_time(8, book_days=1)
            assert result.day == 1  # 7月1日
            assert result.hour == 8

    def test_day_after_tomorrow(self):
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 10, 0, 0)
            result = build_begin_time(9, book_days=2)
            assert result.hour == 9


class TestParsePlanCode:
    def test_valid_code(self):
        result = parse_plan_code("1:1558:296:13:9")
        assert result["room_type"] == 1
        assert result["floor_id"] == 1558
        assert result["seat_num"] == "296"
        assert result["start_hour"] == 13
        assert result["duration_hours"] == 9

    def test_seat_num_as_string(self):
        result = parse_plan_code("1:1558:001:13:9")
        assert result["seat_num"] == "001"

    def test_invalid_format_raises_value_error(self):
        with pytest.raises(ValueError, match="plan 格式"):
            parse_plan_code("1:1558:296")

    def test_invalid_colon_count(self):
        with pytest.raises(ValueError):
            parse_plan_code("1:1558:296:13:9:extra")

    def test_non_numeric_fields(self):
        with pytest.raises(ValueError):
            parse_plan_code("abc:1558:296:13:9")


class TestParseExecuteTime:
    def test_hhmm(self):
        result = parse_execute_time("19:58")
        assert isinstance(result, time)
        assert result.hour == 19
        assert result.minute == 58

    def test_hhmmss(self):
        result = parse_execute_time("19:58:30")
        assert result.hour == 19
        assert result.minute == 58
        assert result.second == 30

    def test_empty_returns_none(self):
        assert parse_execute_time("") is None
        assert parse_execute_time("   ") is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="execute_at"):
            parse_execute_time("abc")

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_execute_time("25:00")


class TestBuildExecuteDatetime:
    def test_future_time_same_day(self):
        """目标时间在现在之后，应返回今天。"""
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 10, 0, 0)
            result = build_execute_datetime("19:58")
            assert result.day == 30
            assert result.hour == 19
            assert result.minute == 58

    def test_past_time_next_day(self):
        """目标时间已过，应返回明天。"""
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 22, 0, 0)
            result = build_execute_datetime("19:58")
            assert result.day == 1  # 7月1日

    def test_empty_returns_none(self):
        assert build_execute_datetime("") is None

    def test_explicit_now(self):
        result = build_execute_datetime("08:00", now=datetime(2026, 6, 30, 10, 0, 0))
        assert result.day == 1  # 已过，推到明天


class TestNormalizeExecuteTime:
    def test_hhmm_normalized(self):
        assert normalize_execute_time("8:5") == "08:05:00"

    def test_hhmmss_normalized(self):
        assert normalize_execute_time("08:05:30") == "08:05:30"

    def test_empty(self):
        assert normalize_execute_time("") == ""


class TestIsTimeOutOfRange:
    def test_match_in_message(self):
        assert is_time_out_of_range({"MESSAGE": "超出可预约座位时间范围"}) is True

    def test_match_in_data_msg(self):
        assert is_time_out_of_range({"DATA": {"msg": "超出可预约座位时间范围"}}) is True

    def test_no_match(self):
        assert is_time_out_of_range({"MESSAGE": "其他错误"}) is False

    def test_empty_result(self):
        assert is_time_out_of_range({}) is False


class TestBookingFailed:
    def test_data_result_fail(self):
        assert booking_failed({"CODE": "ok", "DATA": {"result": "fail"}}) is True

    def test_code_paramerror(self):
        assert booking_failed({"CODE": "paramerror"}) is True

    def test_code_error(self):
        assert booking_failed({"CODE": "error"}) is True

    def test_code_ok(self):
        assert booking_failed({"CODE": "ok"}) is False

    def test_non_dict(self):
        assert booking_failed("not a dict") is True

    def test_success_case(self):
        assert booking_failed({"CODE": "ok", "DATA": {"result": "success"}}) is False


class TestBookingMessage:
    def test_message_field(self):
        assert booking_message({"MESSAGE": "预约成功"}) == "预约成功"

    def test_data_msg_field(self):
        assert booking_message({"DATA": {"msg": "座位已锁定"}}) == "座位已锁定"

    def test_non_dict(self):
        assert "失败" in booking_message("error")

    def test_empty_returns_default(self):
        assert "失败" in booking_message({})


class TestGetSeatLookupTime:
    def test_late_night_returns_next_morning(self):
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 22, 30, 0)
            result = get_seat_lookup_time()
            assert result.day == 1  # 次日
            assert result.hour == 8

    def test_early_morning_returns_same_morning(self):
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 6, 30, 5, 0, 0)
            result = get_seat_lookup_time()
            assert result.day == 30
            assert result.hour == 8

    def test_daytime_returns_now(self):
        with patch("hdu_library_booking.models.time_utils.now_cst") as mock_now:
            expected = datetime(2026, 6, 30, 14, 30, 0)
            mock_now.return_value = expected
            result = get_seat_lookup_time()
            assert result == expected
