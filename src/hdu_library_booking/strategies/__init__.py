"""座位选择策略 — 固定座位、范围随机、按星期自动切换."""

from hdu_library_booking.strategies.fixed import FixedSeatStrategy
from hdu_library_booking.strategies.random_range import RandomRangeStrategy
from hdu_library_booking.strategies.weekday import WeekdayRotationStrategy

__all__ = [
    "FixedSeatStrategy",
    "RandomRangeStrategy",
    "WeekdayRotationStrategy",
]
