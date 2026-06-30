"""
固定座位策略 (FR-5.1)。

用户明确指定房间、楼层、座位号，系统精确匹配。
"""

from typing import Any

from core.exceptions import SeatQueryError
from core.metrics import ErrorCategory, error_tracker

from ..models.plan import BookingPlan
from ..services.base import ISeatSelectionStrategy


class FixedSeatStrategy(ISeatSelectionStrategy):
    """固定座位选择策略。

    在楼层列表中精准定位 plan 指定的 floor_id + seat_num。
    """

    def select_seat(self, client: Any, plan: BookingPlan, **kwargs) -> dict | None:
        floors = kwargs.get("floors")
        if not floors:
            floors = self._fetch_floors(client, plan)

        try:
            _, seat = client.find_seat_in_floors(floors, plan.floor_id, plan.seat_num)
            return seat  # type: ignore[no-any-return]
        except SeatQueryError as exc:
            error_tracker.record(
                ErrorCategory.STRATEGY,
                f"固定座位策略定位失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            return None

    def describe(self, plan: BookingPlan) -> str:
        return (
            f"固定座位: 楼层 {plan.floor_id}, "
            f"{plan.seat_num} 座, "
            f"{plan.start_hour}:00 开始, "
            f"{plan.duration_hours}h"
        )

    def _fetch_floors(self, client, plan):
        """当外部未提供 floors 时自行查询。"""
        room_types = client.get_room_types()
        detail = client.get_room_detail(room_types[0]["query"])
        cat_id = detail["space_category"]["category_id"]
        con_id = detail["space_category"]["content_id"]
        from core.utils import build_begin_time

        begin = build_begin_time(plan.start_hour, plan.book_days)
        return client.get_seat_map(cat_id, con_id, begin, plan.duration_hours)
