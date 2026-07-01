"""领域模型 — 座位预订计划、预订结果解析、时间工具、座位查询规则."""

from hdu_library_booking.models.booking_result import (
    _get_data,
    _get_message,
    booking_failed,
    booking_message,
    is_duplicate,
    is_invalid_request,
    is_seat_unavailable,
    is_time_out_of_range,
)
from hdu_library_booking.models.plan import BookingPlan, PlanStatus, Weekday
from hdu_library_booking.models.seat_lookup import get_seat_lookup_time
from hdu_library_booking.models.time_utils import (
    build_begin_time,
    build_execute_datetime,
    normalize_execute_time,
    now_cst,
    parse_execute_time,
    parse_plan_code,
)

__all__ = [
    "BookingPlan",
    "PlanStatus",
    "Weekday",
    "_get_data",
    "_get_message",
    "booking_failed",
    "booking_message",
    "build_begin_time",
    "build_execute_datetime",
    "get_seat_lookup_time",
    "is_duplicate",
    "is_invalid_request",
    "is_seat_unavailable",
    "is_time_out_of_range",
    "normalize_execute_time",
    "now_cst",
    "parse_execute_time",
    "parse_plan_code",
]
