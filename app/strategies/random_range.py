"""
范围随机策略 (FR-5.3)。

在用户指定的座位号范围内随机选取，前几次尝试倾向偏好座位。
"""

import random
from typing import Any

from ..models.plan import BookingPlan
from ..services.base import ISeatSelectionStrategy


class RandomRangeStrategy(ISeatSelectionStrategy):
    """范围随机座位选择策略。

    参数
    ----
    seat_range : tuple[int, int]
        座位号范围（含两端），如 (100, 150)。
    preferred_seats : list[str]
        偏好的座位号列表，前几次尝试优先选取。
    preferred_attempts : int
        偏好座位优先尝试的次数，默认 3。
    """

    def __init__(
        self,
        seat_range: tuple[int, int],
        preferred_seats: list[str] | None = None,
        preferred_attempts: int = 3,
    ):
        self.low, self.high = seat_range
        self.preferred = preferred_seats or []
        self.preferred_attempts = preferred_attempts
        self._attempt = 0

    # ------------------------------------------------------------------
    # ISeatSelectionStrategy 实现
    # ------------------------------------------------------------------
    def select_seat(self, client: Any, plan: BookingPlan, **kwargs) -> dict | None:
        self._attempt += 1
        floors = kwargs.get("floors", [])

        # 收集范围内所有座位
        all_seats = []
        for floor in floors:
            pois = floor.get("seatMap", {}).get("POIs", [])
            for seat in pois:
                try:
                    num = int(seat.get("title", "0"))
                except (ValueError, TypeError):
                    continue
                if self.low <= num <= self.high:
                    all_seats.append((floor, seat))

        if not all_seats:
            return None

        # 选择逻辑：前 N 次倾向偏好座位
        candidate = self._pick_seat(all_seats)
        if candidate is None:
            return None
        return candidate[1]  # type: ignore[no-any-return]  # seat POI

    def describe(self, plan: BookingPlan) -> str:
        prefs = ",".join(self.preferred) if self.preferred else "无"
        return f"范围随机: {self.low}-{self.high} 号, 偏好: [{prefs}], 第 {self._attempt} 次尝试"

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _pick_seat(self, all_seats: list) -> tuple | None:
        """从座位列表中按策略选取。"""
        if self._attempt <= self.preferred_attempts and self.preferred:
            # 尝试在范围内匹配偏好座位
            pref_set = set(self.preferred)
            matched = [s for s in all_seats if str(s[1].get("title")) in pref_set]
            if matched:
                return random.choice(matched)  # type: ignore[no-any-return]

        return random.choice(all_seats)  # type: ignore[no-any-return]

    def reset(self) -> None:
        """重置尝试计数（新一轮预约前调用）。"""
        self._attempt = 0
