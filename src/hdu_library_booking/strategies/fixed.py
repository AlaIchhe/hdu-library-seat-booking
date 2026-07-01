"""
固定座位策略 (FR-5.1)。

用户明确指定房间、楼层、座位号，系统精确匹配。
"""

from typing import Any

from hdu_library_booking.exceptions import SeatQueryError
from hdu_library_booking.gateways.protocols import ILibraryGateway
from hdu_library_booking.observability._error_tracker import ErrorCategory, error_tracker
from hdu_library_booking.types import Result, SeatPoi

from ..models.plan import BookingPlan
from ..services.interfaces import ISeatSelectionStrategy


class FixedSeatStrategy(ISeatSelectionStrategy):
    """固定座位选择策略。

    在楼层列表中精准定位 plan 指定的 floor_id + seat_num。
    """

    def select_seat(
        self, gateway: ILibraryGateway, plan: BookingPlan, **kwargs: object
    ) -> Result[SeatPoi, str]:
        floors = kwargs.get("floors")
        if not floors:
            floors = self._fetch_floors(gateway, plan)

        try:
            _, seat = gateway.find_seat_in_floors(floors, plan.floor_id, plan.seat_num)  # type: ignore[arg-type]
            return Result.success(seat)
        except SeatQueryError as exc:
            error_tracker.record(
                ErrorCategory.STRATEGY,
                f"固定座位策略定位失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            return Result.failure(str(exc))

    def describe(self, plan: BookingPlan) -> str:
        return (
            f"固定座位: 楼层 {plan.floor_id}, "
            f"{plan.seat_num} 座, "
            f"{plan.start_hour}:00 开始, "
            f"{plan.duration_hours}h"
        )

    def _fetch_floors(self, gateway: ILibraryGateway, plan: BookingPlan) -> list[dict[str, Any]]:
        """当外部未提供 floors 时自行查询。"""
        room_types = gateway.get_room_types()
        first_room = room_types[0]
        detail = gateway.get_room_detail(str(first_room["query"]))
        space = detail["space_category"]
        cat_id = str(space["category_id"])
        con_id = str(space["content_id"])
        from hdu_library_booking.models.time_utils import build_begin_time

        begin = build_begin_time(plan.start_hour, plan.book_days)
        return gateway.get_seat_map(cat_id, con_id, begin, plan.duration_hours)
