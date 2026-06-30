"""Tests for app.models.plan — BookingPlan, Weekday, PlanStatus."""

from app.models.plan import (
    BookingPlan,
    PlanStatus,
    Weekday,
)


class TestWeekday:
    def test_enum_values(self):
        assert Weekday.MONDAY == 0
        assert Weekday.SUNDAY == 6

    def test_labels(self):
        assert Weekday.label(Weekday.MONDAY) == "周一"
        assert Weekday.label(Weekday.FRIDAY) == "周五"
        assert Weekday.label(Weekday.SUNDAY) == "周日"

    def test_invalid_label(self):
        # 传入无效值应返回 "?"
        class FakeDay:
            pass

        assert "?" in Weekday.label(FakeDay())


class TestPlanStatus:
    def test_enum_values(self):
        assert PlanStatus.ENABLED == "enabled"
        assert PlanStatus.DISABLED == "disabled"


class TestBookingPlanValidation:
    """BookingPlan.validate() 测试。"""

    def make_plan(self, **overrides):
        defaults = {
            "room_type": 1,
            "floor_id": 1558,
            "seat_num": "296",
            "start_hour": 13,
            "duration_hours": 9,
            "booker_name": "测试",
            "book_days": 1,
        }
        defaults.update(overrides)
        return BookingPlan(**defaults)

    def test_valid_plan(self):
        plan = self.make_plan()
        assert plan.validate() == []

    def test_invalid_room_type(self):
        plan = self.make_plan(room_type=99)
        errors = plan.validate()
        assert any("房间类型" in e for e in errors)

    def test_invalid_floor_id(self):
        plan = self.make_plan(floor_id=0)
        errors = plan.validate()
        assert any("楼层" in e for e in errors)

    def test_empty_seat_num(self):
        plan = self.make_plan(seat_num="")
        errors = plan.validate()
        assert any("座位号" in e for e in errors)

    def test_start_hour_out_of_range(self):
        plan = self.make_plan(start_hour=25)
        errors = plan.validate()
        assert any("开始小时" in e for e in errors)

    def test_negative_start_hour(self):
        plan = self.make_plan(start_hour=-1)
        errors = plan.validate()
        assert any("开始小时" in e for e in errors)

    def test_zero_duration(self):
        plan = self.make_plan(duration_hours=0)
        errors = plan.validate()
        assert any("时长" in e for e in errors)

    def test_negative_duration(self):
        plan = self.make_plan(duration_hours=-5)
        errors = plan.validate()
        assert any("时长" in e for e in errors)

    def test_negative_book_days(self):
        plan = self.make_plan(book_days=-1)
        errors = plan.validate()
        assert any("天数偏移" in e for e in errors)

    def test_multiple_errors(self):
        plan = self.make_plan(room_type=99, floor_id=-1, seat_num="")
        errors = plan.validate()
        assert len(errors) >= 3


class TestBookingPlanSerialization:
    def test_to_dict_basic(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )
        d = plan.to_dict()
        assert d["room_type"] == 1
        assert d["floor_id"] == 1558
        assert d["seat_num"] == "296"
        assert d["start_hour"] == 13
        assert d["duration_hours"] == 9
        assert d["status"] == "enabled"

    def test_to_dict_with_tags(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="001",
            start_hour=8,
            duration_hours=4,
            tags=["窗口", "安静"],
        )
        d = plan.to_dict()
        assert d["tags"] == ["窗口", "安静"]

    def test_to_dict_with_weekday(self):
        plan = BookingPlan(
            room_type=2,
            floor_id=1000,
            seat_num="050",
            start_hour=9,
            duration_hours=3,
            weekday=Weekday.MONDAY,
        )
        d = plan.to_dict()
        assert d["weekday"] == 0  # Weekday.MONDAY.value

    def test_from_dict_roundtrip(self):
        original = BookingPlan(
            room_type=3,
            floor_id=2000,
            seat_num="100",
            start_hour=14,
            duration_hours=6,
            booker_name="张三",
            book_days=2,
            status=PlanStatus.DISABLED,
            weekday=Weekday.WEDNESDAY,
            tags=["tag1"],
        )
        d = original.to_dict()
        restored = BookingPlan.from_dict(d)
        assert restored.room_type == original.room_type
        assert restored.floor_id == original.floor_id
        assert restored.seat_num == original.seat_num
        assert restored.start_hour == original.start_hour
        assert restored.duration_hours == original.duration_hours
        assert restored.booker_name == original.booker_name
        assert restored.status == PlanStatus.DISABLED
        assert restored.weekday == Weekday.WEDNESDAY
        assert restored.tags == ["tag1"]

    def test_from_dict_defaults(self):
        """空字典应使用默认值（通过 dataclass field defaults）"""
        plan = BookingPlan.from_dict(
            {
                "room_type": 1,
                "floor_id": 1,
                "seat_num": "1",
                "start_hour": 1,
                "duration_hours": 1,
            }
        )
        assert plan.status == PlanStatus.ENABLED
        assert plan.weekday is None
        assert plan.tags == []


class TestBookingPlanCode:
    def test_to_plan_code(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )
        assert plan.to_plan_code() == "1:1558:296:13:9"

    def test_from_plan_code(self):
        plan = BookingPlan.from_plan_code("2:1000:050:8:4")
        assert plan.room_type == 2
        assert plan.floor_id == 1000
        assert plan.seat_num == "050"
        assert plan.start_hour == 8
        assert plan.duration_hours == 4

    def test_code_roundtrip(self):
        original = "3:2000:100:14:6"
        plan = BookingPlan.from_plan_code(original)
        assert plan.to_plan_code() == original
