"""Tests for core.domain.booking_result — 预约结果谓词函数。"""

from __future__ import annotations

from core import constants as C
from core.domain.booking_result import (
    _get_data,
    _get_message,
    booking_failed,
    booking_message,
    is_duplicate,
    is_invalid_request,
    is_seat_unavailable,
    is_time_out_of_range,
)

# ---------------------------------------------------------------------------
# 谓词函数测试
# ---------------------------------------------------------------------------


class TestIsDuplicate:
    def test_duplicate_message(self):
        result = {"MESSAGE": C.MSG_DUPLICATE}
        assert is_duplicate(result) is True

    def test_not_duplicate(self):
        result = {"MESSAGE": "其他错误"}
        assert is_duplicate(result) is False

    def test_duplicate_in_data_msg(self):
        """重复预约消息在 DATA.msg 字段时也应识别。"""
        result = {"DATA": {"msg": C.MSG_DUPLICATE}}
        assert is_duplicate(result) is True


class TestIsSeatUnavailable:
    def test_seat_unavailable(self):
        result = {"MESSAGE": C.MSG_SEAT_UNAVAILABLE}
        assert is_seat_unavailable(result) is True

    def test_not_seat_unavailable(self):
        result = {"MESSAGE": "其他错误"}
        assert is_seat_unavailable(result) is False

    def test_seat_unavailable_in_data_msg(self):
        result = {"DATA": {"msg": C.MSG_SEAT_UNAVAILABLE}}
        assert is_seat_unavailable(result) is True


class TestIsTimeOutOfRange:
    def test_time_out_of_range(self):
        result = {"MESSAGE": C.MSG_TIME_OUT_OF_RANGE}
        assert is_time_out_of_range(result) is True

    def test_not_time_out_of_range(self):
        result = {"MESSAGE": "其他错误"}
        assert is_time_out_of_range(result) is False


class TestIsInvalidRequest:
    def test_invalid_request(self):
        result = {"MESSAGE": C.MSG_INVALID_REQUEST}
        assert is_invalid_request(result) is True

    def test_not_invalid_request(self):
        result = {"MESSAGE": "其他错误"}
        assert is_invalid_request(result) is False


# ---------------------------------------------------------------------------
# booking_failed 测试
# ---------------------------------------------------------------------------


class TestBookingFailed:
    def test_not_dict(self):
        assert booking_failed("string") is True
        assert booking_failed(None) is True
        assert booking_failed(123) is True

    def test_code_error(self):
        assert booking_failed({"CODE": "error"}) is True

    def test_code_paramerror(self):
        assert booking_failed({"CODE": "paramerror"}) is True

    def test_code_fail(self):
        assert booking_failed({"CODE": "fail"}) is True

    def test_code_failed(self):
        assert booking_failed({"CODE": "failed"}) is True

    def test_data_result_fail(self):
        assert booking_failed({"DATA": {"result": "fail"}}) is True

    def test_success(self):
        assert booking_failed({"CODE": "ok"}) is False

    def test_empty_dict(self):
        assert booking_failed({}) is False


# ---------------------------------------------------------------------------
# booking_message 测试
# ---------------------------------------------------------------------------


class TestBookingMessage:
    def test_not_dict(self):
        assert booking_message("fail") == "预约接口返回失败"

    def test_message_field(self):
        assert booking_message({"MESSAGE": "成功"}) == "成功"

    def test_data_msg_fallback(self):
        assert booking_message({"DATA": {"msg": "详情"}}) == "详情"

    def test_default_message(self):
        assert booking_message({}) == "预约接口返回失败"

    def test_message_takes_precedence(self):
        """MESSAGE 字段优先于 DATA.msg。"""
        result = {"MESSAGE": "顶层消息", "DATA": {"msg": "数据消息"}}
        assert booking_message(result) == "顶层消息"


# ---------------------------------------------------------------------------
# _get_data / _get_message 内部工具
# ---------------------------------------------------------------------------


class TestGetData:
    def test_returns_dict_data(self):
        result = {"DATA": {"uid": "123"}}
        assert _get_data(result) == {"uid": "123"}

    def test_non_dict_data_returns_empty(self):
        result = {"DATA": "string"}
        assert _get_data(result) == {}

    def test_missing_data_returns_empty(self):
        assert _get_data({}) == {}


class TestGetMessage:
    def test_message_from_top_level(self):
        assert _get_message({"MESSAGE": "错误"}) == "错误"

    def test_message_from_data_msg(self):
        assert _get_message({"DATA": {"msg": "错误"}}) == "错误"

    def test_empty_message(self):
        assert _get_message({}) == ""
