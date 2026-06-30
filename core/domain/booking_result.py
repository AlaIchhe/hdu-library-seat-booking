"""预约结果解析 — 纯领域逻辑，零基础设施依赖。

将 API 响应字典解析为领域层可理解的结果。
"""

from ..constants import (
    MSG_DUPLICATE,
    MSG_INVALID_REQUEST,
    MSG_SEAT_UNAVAILABLE,
    MSG_TIME_OUT_OF_RANGE,
)
from ..types import Json


def _get_message(result: Json) -> str:
    """从 API 响应中提取错误消息字符串。"""
    data = _get_data(result)
    return str(result.get("MESSAGE") or data.get("msg") or "")


def is_time_out_of_range(result: Json) -> bool:
    """判断预约结果是否为"超出时间范围"错误。"""
    return MSG_TIME_OUT_OF_RANGE in _get_message(result)


def is_duplicate(result: Json) -> bool:
    """判断预约结果是否为"重复预约"错误。"""
    return MSG_DUPLICATE in _get_message(result)


def is_seat_unavailable(result: Json) -> bool:
    """判断预约结果是否为"座位不可用"错误。"""
    return MSG_SEAT_UNAVAILABLE in _get_message(result)


def is_invalid_request(result: Json) -> bool:
    """判断预约结果是否为"非法请求"错误。"""
    return MSG_INVALID_REQUEST in _get_message(result)


def _get_data(result: Json) -> Json:
    """安全提取 DATA 字段为 dict。"""
    data = result.get("DATA")
    return data if isinstance(data, dict) else {}


def booking_failed(result: object) -> bool:
    """判断预约是否失败。"""
    if not isinstance(result, dict):
        return True
    data = _get_data(result)
    code = str(result.get("CODE") or "").strip().lower()
    status = str(data.get("result") or "").strip().lower()
    return status == "fail" or code in {"paramerror", "error", "fail", "failed"}


def booking_message(result: object) -> str:
    """提取预约结果的文本消息。"""
    if not isinstance(result, dict):
        return "预约接口返回失败"
    data = _get_data(result)
    return str(result.get("MESSAGE") or data.get("msg") or "预约接口返回失败").strip()
