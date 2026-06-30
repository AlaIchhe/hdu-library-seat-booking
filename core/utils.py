"""向后兼容 re-export — 所有函数已迁移至 core/domain/。

此文件保留以避免破坏外部导入。新代码请直接从 core.domain 导入:
  from core.domain.time import now_cst, parse_plan_code, ...
  from core.domain.seat_lookup import get_seat_lookup_time
  from core.domain.booking_result import booking_failed, booking_message, ...
"""

from .domain.booking_result import (
    booking_failed,
    booking_message,
    is_time_out_of_range,
)
from .domain.seat_lookup import get_seat_lookup_time
from .domain.time import (
    build_begin_time,
    build_execute_datetime,
    normalize_execute_time,
    now_cst,
    parse_execute_time,
    parse_plan_code,
)

__all__ = [
    "booking_failed",
    "booking_message",
    "build_begin_time",
    "build_execute_datetime",
    "get_seat_lookup_time",
    "is_time_out_of_range",
    "normalize_execute_time",
    "now_cst",
    "parse_execute_time",
    "parse_plan_code",
]
