"""Tests for hdu_library_booking.strategies — FixedSeatStrategy, RandomRangeStrategy."""

from unittest.mock import MagicMock

from hdu_library_booking.exceptions import SeatQueryError
from hdu_library_booking.models.plan import BookingPlan
from hdu_library_booking.services.booking import BookingOrchestrator
from hdu_library_booking.services.notifications import ConsoleNotification
from hdu_library_booking.strategies.fixed import FixedSeatStrategy
from hdu_library_booking.strategies.random_range import RandomRangeStrategy


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
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_success
        assert result.value["id"] == "seat_296"
        assert result.value["title"] == "296"

    def test_select_seat_not_found(self):
        client = MagicMock()
        plan = self.make_plan(seat_num="999")
        floors = self.build_floors()
        client.find_seat_in_floors.side_effect = SeatQueryError("找不到座位")

        strategy = FixedSeatStrategy()
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_failure
        assert "找不到座位" in result.error

    def test_select_seat_floor_not_found(self):
        client = MagicMock()
        plan = self.make_plan(floor_id=9999)
        floors = self.build_floors()
        client.find_seat_in_floors.side_effect = SeatQueryError("找不到楼层")

        strategy = FixedSeatStrategy()
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_failure
        assert "找不到楼层" in result.error

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
        client.get_room_types.return_value = [{"name": "自习室", "query": "q"}]
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
        result = strategy.select_seat(client, plan)
        # 应调用 get_seat_map
        assert result.is_success
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
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_success
        num = int(result.value["title"])
        assert 100 <= num <= 160

    def test_select_seat_out_of_range(self):
        client = MagicMock()
        plan = self.make_plan()
        floors = self.build_floors()

        strategy = RandomRangeStrategy(seat_range=(500, 600))
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_failure

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
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_success
        # 首次尝试应在偏好范围内
        assert result.value["title"] in ("150", "151")

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
        result = strategy.select_seat(client, plan, floors=floors)  # attempt 2 (random)
        # 第二次可能在偏好之外
        assert result.is_success

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
        result = strategy.select_seat(client, plan, floors=floors)
        assert result.is_success
        assert result.value["title"] == "150"


class TestFixedSeatStrategyFetchFloors:
    """FixedSeatStrategy._fetch_floors 测试。"""

    def test_fetch_floors_uses_room_query(self):
        """plan 带 room_query 时，应直接使用它查询 room_detail。"""
        client = MagicMock()
        query_str = "space_category[category_id]=10&space_category[content_id]=20"
        client.get_room_detail.return_value = {
            "space_category": {"category_id": "10", "content_id": "20"}
        }
        client.get_seat_map.return_value = [{"roomName": "3楼"}]

        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            room_query=query_str,
        )
        strategy = FixedSeatStrategy()
        floors = strategy._fetch_floors(client, plan)

        # 应使用 room_query 调用 get_room_detail，而非 get_room_types
        client.get_room_detail.assert_called_once_with(query_str)
        client.get_room_types.assert_not_called()
        assert len(floors) == 1

    def test_fetch_floors_fallback_without_room_query(self):
        """plan 不带 room_query 时，回退到使用 get_room_types()[0]。"""
        client = MagicMock()
        client.get_room_types.return_value = [
            {"name": "自习室", "query": "q1"},
        ]
        client.get_room_detail.return_value = {
            "space_category": {"category_id": "10", "content_id": "20"}
        }
        client.get_seat_map.return_value = [{"roomName": "3楼"}]

        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )
        strategy = FixedSeatStrategy()
        floors = strategy._fetch_floors(client, plan)

        client.get_room_types.assert_called_once()
        assert len(floors) == 1


class TestBackoffDelayMinimum:
    """BookingOrchestrator._backoff_delay 最小延迟测试。"""

    def test_backoff_delay_has_minimum(self):
        """指数退避延迟不应小于 0.1 秒。"""
        orchestrator = BookingOrchestrator(
            gateway=MagicMock(),
            strategy=FixedSeatStrategy(),
            notifier=ConsoleNotification(use_colors=False),
        )
        orchestrator.retry_delay = 0.05  # 很小的 base delay

        # 多次调用，验证最小值
        for _ in range(50):
            delay = orchestrator._backoff_delay(attempt=1)
            assert delay >= 0.1, f"delay {delay} 小于最小值 0.1"

    def test_backoff_delay_increases_with_attempts(self):
        """延迟应随 attempt 增加（整体趋势）。"""
        orchestrator = BookingOrchestrator(
            gateway=MagicMock(),
            strategy=FixedSeatStrategy(),
            notifier=ConsoleNotification(use_colors=False),
        )
        orchestrator.retry_delay = 1.0

        # attempt=10 的平均延迟应远大于 attempt=1
        avg_1 = sum(orchestrator._backoff_delay(1) for _ in range(100)) / 100
        avg_10 = sum(orchestrator._backoff_delay(10) for _ in range(100)) / 100
        assert avg_10 > avg_1 * 10
