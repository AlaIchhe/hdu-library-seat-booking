"""Tests for app.strategies — FixedSeatStrategy, RandomRangeStrategy."""

from unittest.mock import MagicMock

from app.models.plan import BookingPlan
from app.strategies.fixed_seat import FixedSeatStrategy
from app.strategies.random_range import RandomRangeStrategy
from core.exceptions import SeatQueryError


class TestFixedSeatStrategy:
    def make_plan(self, **overrides):
        defaults = {
            "room_type": 1,
            "floor_id": 1558,
            "seat_num": "296",
            "start_hour": 13,
            "duration_hours": 9,
        }
        defaults.update(overrides)
        return BookingPlan(**defaults)

    def build_floors(self):
        return [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [
                        {"title": "296", "id": "seat_296"},
                        {"title": "297", "id": "seat_297"},
                    ],
                },
            },
            {
                "roomName": "4楼",
                "seatMap": {
                    "info": {"id": "2000"},
                    "POIs": [
                        {"title": "100", "id": "seat_100"},
                    ],
                },
            },
        ]

    def test_select_seat_found(self):
        client = MagicMock()
        plan = self.make_plan()
        floors = self.build_floors()
        # 设置 find_seat_in_floors 返回正确的元组
        client.find_seat_in_floors.return_value = (
            floors[0],
            floors[0]["seatMap"]["POIs"][0],
        )

        strategy = FixedSeatStrategy()
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is not None
        assert seat["id"] == "seat_296"
        assert seat["title"] == "296"

    def test_select_seat_not_found(self):
        client = MagicMock()
        plan = self.make_plan(seat_num="999")
        floors = self.build_floors()
        client.find_seat_in_floors.side_effect = SeatQueryError("找不到座位")

        strategy = FixedSeatStrategy()
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is None

    def test_select_seat_floor_not_found(self):
        client = MagicMock()
        plan = self.make_plan(floor_id=9999)
        floors = self.build_floors()
        client.find_seat_in_floors.side_effect = SeatQueryError("找不到楼层")

        strategy = FixedSeatStrategy()
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is None

    def test_describe(self):
        plan = self.make_plan()
        strategy = FixedSeatStrategy()
        desc = strategy.describe(plan)
        assert "固定座位" in desc
        assert "1558" in desc
        assert "296" in desc

    def test_select_seat_without_floors_fetches(self):
        """未传入 floors 时，策略应自行查询。"""
        client = MagicMock()
        client.get_room_types.return_value = [{"name": "自习室(1)", "query": "q"}]
        client.get_room_detail.return_value = {
            "space_category": {"category_id": "10", "content_id": "20"}
        }
        floor = {
            "roomName": "3楼",
            "seatMap": {
                "info": {"id": "1558"},
                "POIs": [{"title": "296", "id": "seat_296"}],
            },
        }
        client.get_seat_map.return_value = [floor]
        client.find_seat_in_floors.return_value = (floor, floor["seatMap"]["POIs"][0])

        plan = self.make_plan()
        strategy = FixedSeatStrategy()
        _seat = strategy.select_seat(client, plan)
        # 应调用 get_seat_map
        assert client.get_seat_map.called


class TestRandomRangeStrategy:
    def make_plan(self, **overrides):
        defaults = {
            "room_type": 1,
            "floor_id": 1558,
            "seat_num": "150",
            "start_hour": 13,
            "duration_hours": 9,
        }
        defaults.update(overrides)
        return BookingPlan(**defaults)

    def build_floors(self):
        pois = [{"title": str(i), "id": f"seat_{i}"} for i in range(100, 161)]
        return [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": pois,
                },
            },
        ]

    def test_select_seat_in_range(self):
        client = MagicMock()
        plan = self.make_plan()
        floors = self.build_floors()

        strategy = RandomRangeStrategy(seat_range=(100, 160))
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is not None
        num = int(seat["title"])
        assert 100 <= num <= 160

    def test_select_seat_out_of_range(self):
        client = MagicMock()
        plan = self.make_plan()
        floors = self.build_floors()

        strategy = RandomRangeStrategy(seat_range=(500, 600))
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is None

    def test_preferred_seats_attempt(self):
        client = MagicMock()
        plan = self.make_plan()
        floors = self.build_floors()

        strategy = RandomRangeStrategy(
            seat_range=(100, 160),
            preferred_seats=["150", "151"],
            preferred_attempts=100,  # 确保偏好期
        )
        strategy.reset()
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is not None
        # 首次尝试应在偏好范围内
        assert seat["title"] in ("150", "151")

    def test_after_preferred_attempts(self):
        client = MagicMock()
        plan = self.make_plan()
        floors = self.build_floors()

        strategy = RandomRangeStrategy(
            seat_range=(100, 160),
            preferred_seats=["150"],
            preferred_attempts=1,
        )
        strategy.reset()
        strategy.select_seat(client, plan, floors=floors)  # attempt 1 (preferred)
        seat = strategy.select_seat(client, plan, floors=floors)  # attempt 2 (random)
        # 第二次可能在偏好之外
        assert seat is not None

    def test_describe(self):
        plan = self.make_plan()
        strategy = RandomRangeStrategy(
            seat_range=(100, 160),
            preferred_seats=["120", "130"],
        )
        desc = strategy.describe(plan)
        assert "范围随机" in desc
        assert "100-160" in desc
        assert "120" in desc

    def test_reset(self):
        strategy = RandomRangeStrategy((1, 10))
        plan = self.make_plan()
        floors = self.build_floors()
        strategy.select_seat(MagicMock(), plan, floors=floors)
        assert strategy._attempt == 1
        strategy.reset()
        assert strategy._attempt == 0

    def test_non_numeric_titles_ignored(self):
        """非数字的 title 应被忽略。"""
        client = MagicMock()
        plan = self.make_plan()
        floors = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [
                        {"title": "A01", "id": "a01"},
                        {"title": "150", "id": "seat_150"},
                    ],
                },
            },
        ]

        strategy = RandomRangeStrategy(seat_range=(100, 200))
        seat = strategy.select_seat(client, plan, floors=floors)
        assert seat is not None
        assert seat["title"] == "150"
