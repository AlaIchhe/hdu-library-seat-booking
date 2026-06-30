"""Tests for app.services.plan_service — PlanService CRUD、批量操作、按星期筛选。"""

from __future__ import annotations

import pytest

from app.models.plan import BookingPlan, PlanStatus, Weekday

# ---------------------------------------------------------------------------
# 查询测试
# ---------------------------------------------------------------------------


class TestPlanServiceQuery:
    def test_list_all_returns_all(self, populated_service):
        assert populated_service.count() == 4

    def test_list_enabled_excludes_disabled(self, populated_service):
        enabled = populated_service.list_enabled()
        # 4 个方案中 1 个 DISABLED → 3 个 ENABLED
        assert len(enabled) == 3
        assert all(p.status == PlanStatus.ENABLED for p in enabled)

    def test_list_by_weekday_returns_specific(self, populated_service):
        monday_plans = populated_service.list_by_weekday(Weekday.MONDAY)
        assert len(monday_plans) == 1
        assert monday_plans[0].weekday == Weekday.MONDAY

    def test_list_by_weekday_falls_back_to_generic(self, populated_service):
        """当指定星期无配置时，回落至 weekday=None 的通用方案。"""
        # WEDNESDAY 无专门配置
        wed_plans = populated_service.list_by_weekday(Weekday.WEDNESDAY)
        assert len(wed_plans) == 1
        assert wed_plans[0].weekday is None

    def test_list_by_weekday_prefers_specific_over_generic(self, populated_service):
        """有专门配置时，不回落到通用方案。"""
        tue_plans = populated_service.list_by_weekday(Weekday.TUESDAY)
        assert len(tue_plans) == 1
        assert tue_plans[0].weekday == Weekday.TUESDAY

    def test_get_existing_plan(self, populated_service):
        plan = populated_service.list_all()[0]
        fetched = populated_service.get(plan.plan_id)
        assert fetched is not None
        assert fetched.plan_id == plan.plan_id

    def test_get_nonexistent_returns_none(self, populated_service):
        assert populated_service.get("nonexistent-id") is None


# ---------------------------------------------------------------------------
# 增删测试
# ---------------------------------------------------------------------------


class TestPlanServiceAddRemove:
    def test_add_valid_plan(self, plan_service):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )
        plan_service.add(plan)
        assert plan_service.count() == 1

    def test_add_invalid_plan_raises(self, plan_service):
        plan = BookingPlan(
            room_type=99,
            floor_id=1558,
            seat_num="296",  # 无效 room_type
            start_hour=13,
            duration_hours=9,
        )
        with pytest.raises(ValueError, match="校验失败"):
            plan_service.add(plan)

    def test_remove_existing(self, populated_service):
        plan = populated_service.list_all()[0]
        assert populated_service.remove(plan.plan_id) is True
        assert populated_service.count() == 3

    def test_remove_nonexistent(self, populated_service):
        assert populated_service.remove("nonexistent") is False

    def test_remove_many(self, populated_service):
        ids = [p.plan_id for p in populated_service.list_all()[:2]]
        count = populated_service.remove_many(ids)
        assert count == 2
        assert populated_service.count() == 2


# ---------------------------------------------------------------------------
# update 测试（部分更新 + 校验）
# ---------------------------------------------------------------------------


class TestPlanServiceUpdate:
    def test_update_single_field(self, populated_service):
        plan = populated_service.list_all()[0]
        original_id = plan.plan_id
        updated = populated_service.update(original_id, seat_num="999")
        assert updated is not None
        assert updated.seat_num == "999"
        # 其他字段不变
        assert updated.floor_id == plan.floor_id

    def test_update_multiple_fields(self, populated_service):
        plan = populated_service.list_all()[0]
        updated = populated_service.update(
            plan.plan_id, start_hour=8, duration_hours=2, booker_name="新名字"
        )
        assert updated is not None
        assert updated.start_hour == 8
        assert updated.duration_hours == 2
        assert updated.booker_name == "新名字"

    def test_update_returns_none_for_nonexistent(self, populated_service):
        assert populated_service.update("nonexistent", seat_num="1") is None

    def test_update_validates(self, populated_service):
        plan = populated_service.list_all()[0]
        # start_hour=99 超出范围
        with pytest.raises(ValueError, match="校验失败"):
            populated_service.update(plan.plan_id, start_hour=99)

    def test_update_ignores_unknown_keys(self, populated_service):
        plan = populated_service.list_all()[0]
        # unknown_field 不在 allowed 集合中，应被忽略
        updated = populated_service.update(plan.plan_id, unknown_field="xxx", floor_id=9999)
        assert updated is not None
        assert updated.floor_id == 9999

    def test_update_persists(self, populated_service):
        plan = populated_service.list_all()[0]
        populated_service.update(plan.plan_id, seat_num="777")
        # 重新获取确认持久化
        reloaded = populated_service.get(plan.plan_id)
        assert reloaded is not None
        assert reloaded.seat_num == "777"

    def test_update_preserves_plan_id(self, populated_service):
        plan = populated_service.list_all()[0]
        updated = populated_service.update(plan.plan_id, seat_num="100")
        assert updated is not None
        assert updated.plan_id == plan.plan_id


# ---------------------------------------------------------------------------
# batch_set_time 测试
# ---------------------------------------------------------------------------


class TestPlanServiceBatchSetTime:
    def test_batch_set_time_modifies_matching(self, populated_service):
        ids = [p.plan_id for p in populated_service.list_all()[:2]]
        modified = populated_service.batch_set_time(ids, start_hour=7, duration_hours=1)
        assert modified == 2
        for pid in ids:
            p = populated_service.get(pid)
            assert p is not None
            assert p.start_hour == 7
            assert p.duration_hours == 1

    def test_batch_set_time_ignores_non_matching(self, populated_service):
        modified = populated_service.batch_set_time(["nonexistent"], start_hour=7)
        assert modified == 0

    def test_batch_set_time_only_set_fields(self, populated_service):
        plan = populated_service.list_all()[0]
        original_duration = plan.duration_hours
        modified = populated_service.batch_set_time(
            [plan.plan_id],
            start_hour=6,  # 只设置 start_hour
        )
        assert modified == 1
        updated = populated_service.get(plan.plan_id)
        assert updated is not None
        assert updated.start_hour == 6
        assert updated.duration_hours == original_duration  # 不变

    def test_batch_set_time_book_days(self, populated_service):
        plan = populated_service.list_all()[0]
        modified = populated_service.batch_set_time([plan.plan_id], book_days=3)
        assert modified == 1
        updated = populated_service.get(plan.plan_id)
        assert updated is not None
        assert updated.book_days == 3


# ---------------------------------------------------------------------------
# enable_all / disable_all 测试
# ---------------------------------------------------------------------------


class TestPlanServiceEnableDisableAll:
    def test_enable_all(self, populated_service):
        # populated_service 有 1 个 DISABLED
        count = populated_service.enable_all()
        assert count == 4
        assert populated_service.count_enabled() == 4

    def test_disable_all(self, populated_service):
        count = populated_service.disable_all()
        assert count == 4
        assert populated_service.count_enabled() == 0

    def test_enable_then_disable(self, populated_service):
        populated_service.enable_all()
        assert populated_service.count_enabled() == 4
        populated_service.disable_all()
        assert populated_service.count_enabled() == 0


# ---------------------------------------------------------------------------
# count 测试
# ---------------------------------------------------------------------------


class TestPlanServiceCount:
    def test_count(self, populated_service):
        assert populated_service.count() == 4

    def test_count_enabled(self, populated_service):
        assert populated_service.count_enabled() == 3
