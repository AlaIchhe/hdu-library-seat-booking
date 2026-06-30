"""Tests for app.strategies.weekday_rotation — WeekdayRotationStrategy (FR-5.2)。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models.plan import BookingPlan, Weekday
from app.strategies.weekday_rotation import WeekdayRotationStrategy

# ---------------------------------------------------------------------------
# 配置管理测试
# ---------------------------------------------------------------------------


class TestWeekdayConfigManagement:
    """set_weekday / get_weekday / is_enabled 配置管理。"""

    def test_set_and_get_weekday(self):
        strategy = WeekdayRotationStrategy({})
        strategy.set_weekday(Weekday.MONDAY, floor_id=1558, seat_num="296")
        assert strategy.get_weekday(Weekday.MONDAY) == {"floor_id": 1558, "seat_num": "296"}

    def test_get_weekday_unconfigured_returns_none(self):
        strategy = WeekdayRotationStrategy({})
        assert strategy.get_weekday(Weekday.SUNDAY) is None

    def test_is_enabled_configured_and_enabled_by_default(self):
        strategy = WeekdayRotationStrategy({Weekday.MONDAY: {"floor_id": 1558}})
        assert strategy.is_enabled(Weekday.MONDAY) is True

    def test_is_enabled_returns_false_when_disabled(self):
        strategy = WeekdayRotationStrategy({Weekday.MONDAY: {"floor_id": 1558, "enabled": False}})
        assert strategy.is_enabled(Weekday.MONDAY) is False

    def test_is_enabled_returns_false_when_unconfigured(self):
        strategy = WeekdayRotationStrategy({})
        assert strategy.is_enabled(Weekday.MONDAY) is False

    def test_default_config_stored(self):
        strategy = WeekdayRotationStrategy({}, default_config={"floor_id": 9999})
        assert strategy._default == {"floor_id": 9999}


# ---------------------------------------------------------------------------
# select_seat — 显式 weekday 路径
# ---------------------------------------------------------------------------


class TestSelectSeatExplicitWeekday:
    """plan.weekday 已设置时，直接使用该 weekday 的配置。"""

    def _make_plan(self, weekday: Weekday | None = Weekday.MONDAY, **overrides):
        defaults = {
            "room_type": 1,
            "floor_id": 1558,
            "seat_num": "296",
            "start_hour": 13,
            "duration_hours": 9,
        }
        defaults.update(overrides)
        return BookingPlan(weekday=weekday, **defaults)

    def test_select_with_explicit_weekday_config(self):
        gateway = MagicMock()
        floors = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [{"title": "296", "id": "seat_296"}],
                },
            },
        ]
        seat = floors[0]["seatMap"]["POIs"][0]
        gateway.find_seat_in_floors.return_value = (floors[0], seat)

        strategy = WeekdayRotationStrategy(
            {Weekday.MONDAY: {"floor_id": 1558, "seat_num": "296", "enabled": True}}
        )
        plan = self._make_plan(weekday=Weekday.MONDAY)
        result = strategy.select_seat(gateway, plan, floors=floors)

        assert result.is_success
        assert result.value["id"] == "seat_296"
        gateway.find_seat_in_floors.assert_called_once_with(floors, 1558, "296")

    def test_select_falls_back_to_plan_params_when_config_partial(self):
        """配置只提供 floor_id 时，seat_num 回落到 plan。"""
        gateway = MagicMock()
        floors = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [{"title": "296", "id": "seat_296"}],
                },
            },
        ]
        seat = floors[0]["seatMap"]["POIs"][0]
        gateway.find_seat_in_floors.return_value = (floors[0], seat)

        # 只配置 floor_id，不配置 seat_num
        strategy = WeekdayRotationStrategy({Weekday.MONDAY: {"floor_id": 1558, "enabled": True}})
        plan = self._make_plan(weekday=Weekday.MONDAY, seat_num="296")
        result = strategy.select_seat(gateway, plan, floors=floors)

        assert result.is_success
        gateway.find_seat_in_floors.assert_called_once_with(floors, 1558, "296")

    def test_select_fails_when_weekday_disabled(self):
        gateway = MagicMock()
        strategy = WeekdayRotationStrategy({Weekday.MONDAY: {"floor_id": 1558, "enabled": False}})
        plan = self._make_plan(weekday=Weekday.MONDAY)
        result = strategy.select_seat(gateway, plan, floors=[])

        assert result.is_failure
        assert "未配置或已禁用" in result.error
        gateway.find_seat_in_floors.assert_not_called()

    def test_select_fails_when_weekday_not_configured(self):
        gateway = MagicMock()
        strategy = WeekdayRotationStrategy({})  # 无任何配置
        plan = self._make_plan(weekday=Weekday.FRIDAY)
        result = strategy.select_seat(gateway, plan, floors=[])

        assert result.is_failure
        assert "未配置或已禁用" in result.error

    def test_select_propagates_gateway_exception(self):
        gateway = MagicMock()
        gateway.find_seat_in_floors.side_effect = Exception("座位查询失败")
        strategy = WeekdayRotationStrategy(
            {Weekday.MONDAY: {"floor_id": 1558, "seat_num": "296", "enabled": True}}
        )
        plan = self._make_plan(weekday=Weekday.MONDAY)
        result = strategy.select_seat(gateway, plan, floors=[{"dummy": True}])

        assert result.is_failure
        assert "座位查询失败" in result.error


# ---------------------------------------------------------------------------
# select_seat — 隐式 weekday 路径（通过 book_days 计算）
# ---------------------------------------------------------------------------


class TestSelectSeatImplicitWeekday:
    """plan.weekday 为 None 时，通过 now + book_days 计算目标 weekday。"""

    def test_implicit_weekday_from_book_days(self):
        gateway = MagicMock()
        floors = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [{"title": "296", "id": "seat_296"}],
                },
            },
        ]
        seat = floors[0]["seatMap"]["POIs"][0]
        gateway.find_seat_in_floors.return_value = (floors[0], seat)

        # 2026-07-15 是周三；book_days=0 → 周三
        strategy = WeekdayRotationStrategy(
            {Weekday.WEDNESDAY: {"floor_id": 1558, "seat_num": "296", "enabled": True}}
        )
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            book_days=0,
            weekday=None,
        )

        with patch("app.strategies.weekday_rotation.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 7, 15, 10, 0, 0)  # 周三
            result = strategy.select_seat(gateway, plan, floors=floors)

        assert result.is_success
        assert result.value["id"] == "seat_296"

    def test_implicit_weekday_with_book_days_offset(self):
        gateway = MagicMock()
        floors = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [{"title": "296", "id": "seat_296"}],
                },
            },
        ]
        seat = floors[0]["seatMap"]["POIs"][0]
        gateway.find_seat_in_floors.return_value = (floors[0], seat)

        # 2026-07-15 是周三(2)；book_days=2 → 周五(4)
        strategy = WeekdayRotationStrategy(
            {Weekday.FRIDAY: {"floor_id": 2000, "seat_num": "100", "enabled": True}}
        )
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            book_days=2,
            weekday=None,
        )

        with patch("app.strategies.weekday_rotation.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 7, 15, 10, 0, 0)
            result = strategy.select_seat(gateway, plan, floors=floors)

        assert result.is_success
        # 验证使用了周五的配置
        gateway.find_seat_in_floors.assert_called_once_with(floors, 2000, "100")

    def test_implicit_weekday_unconfigured_returns_failure(self):
        gateway = MagicMock()
        # 仅配置周一
        strategy = WeekdayRotationStrategy({Weekday.MONDAY: {"floor_id": 1558, "enabled": True}})
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            book_days=0,
            weekday=None,
        )

        with patch("app.strategies.weekday_rotation.now_cst") as mock_now:
            mock_now.return_value = datetime(2026, 7, 15, 10, 0, 0)  # 周三
            result = strategy.select_seat(gateway, plan, floors=[])

        assert result.is_failure
        assert "未配置或已禁用" in result.error


# ---------------------------------------------------------------------------
# describe 测试
# ---------------------------------------------------------------------------


class TestDescribe:
    def test_describe_with_configured_weekday(self):
        strategy = WeekdayRotationStrategy({Weekday.MONDAY: {"floor_id": 1558, "seat_num": "296"}})
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            weekday=Weekday.MONDAY,
        )
        desc = strategy.describe(plan)
        assert "按星期切换" in desc
        assert "周一" in desc
        assert "1558" in desc
        assert "296" in desc

    def test_describe_with_no_weekday(self):
        strategy = WeekdayRotationStrategy({}, default_config={"floor_id": 9999, "seat_num": "000"})
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            weekday=None,
        )
        desc = strategy.describe(plan)
        assert "按星期切换" in desc
        assert "?" in desc  # weekday label 为 "?"


# ---------------------------------------------------------------------------
# from_plans 工厂方法
# ---------------------------------------------------------------------------


class TestFromPlans:
    def test_from_plans_builds_config_per_weekday(self):
        plans = [
            BookingPlan(
                room_type=1,
                floor_id=1558,
                seat_num="296",
                start_hour=13,
                duration_hours=9,
                weekday=Weekday.MONDAY,
            ),
            BookingPlan(
                room_type=1,
                floor_id=2000,
                seat_num="100",
                start_hour=8,
                duration_hours=4,
                weekday=Weekday.TUESDAY,
            ),
        ]
        strategy = WeekdayRotationStrategy.from_plans(plans)

        assert strategy.is_enabled(Weekday.MONDAY)
        assert strategy.is_enabled(Weekday.TUESDAY)
        assert not strategy.is_enabled(Weekday.WEDNESDAY)

        monday_cfg = strategy.get_weekday(Weekday.MONDAY)
        assert monday_cfg["floor_id"] == 1558
        assert monday_cfg["seat_num"] == "296"
        assert monday_cfg["enabled"] is True

    def test_from_plans_ignores_plans_without_weekday(self):
        """weekday=None 的方案不参与构建。"""
        plans = [
            BookingPlan(
                room_type=1,
                floor_id=1558,
                seat_num="296",
                start_hour=13,
                duration_hours=9,
                weekday=None,  # 通用方案，应被跳过
            ),
            BookingPlan(
                room_type=1,
                floor_id=2000,
                seat_num="100",
                start_hour=8,
                duration_hours=4,
                weekday=Weekday.FRIDAY,
            ),
        ]
        strategy = WeekdayRotationStrategy.from_plans(plans)
        assert not strategy.is_enabled(Weekday.MONDAY)
        assert strategy.is_enabled(Weekday.FRIDAY)

    def test_from_plans_empty_list(self):
        strategy = WeekdayRotationStrategy.from_plans([])
        assert not strategy.is_enabled(Weekday.MONDAY)
        assert strategy.get_weekday(Weekday.MONDAY) is None
