"""Tests for hdu_library_booking.services.booking — RetryDecision, BookingResult, BookingOrchestrator."""

from unittest.mock import MagicMock

import pytest

from hdu_library_booking import constants as C
from hdu_library_booking.exceptions import HduLibraryError
from hdu_library_booking.models.plan import BookingPlan
from hdu_library_booking.services.booking import (
    BookingOrchestrator,
    BookingResult,
    RetryDecision,
    default_retry_decider,
)
from hdu_library_booking.services.interfaces import CancellationToken
from hdu_library_booking.services.notifications import ConsoleNotification
from hdu_library_booking.strategies.fixed import FixedSeatStrategy


class TestRetryDecision:
    def test_continue(self):
        d = RetryDecision(RetryDecision.CONTINUE, "继续")
        assert d.action == "continue"
        assert d.reason == "继续"

    def test_skip(self):
        d = RetryDecision(RetryDecision.SKIP, "跳过")
        assert d.action == "skip"

    def test_stop(self):
        d = RetryDecision(RetryDecision.STOP, "停止")
        assert d.action == "stop"


class TestDefaultRetryDecider:
    def test_time_out_of_range(self):
        result = {"MESSAGE": C.MSG_TIME_OUT_OF_RANGE}
        decision = default_retry_decider(result)
        assert decision.action == RetryDecision.CONTINUE
        assert "预约窗口" in decision.reason

    def test_duplicate(self):
        result = {"MESSAGE": C.MSG_DUPLICATE}
        decision = default_retry_decider(result)
        assert decision.action == RetryDecision.SKIP

    def test_seat_unavailable(self):
        result = {"MESSAGE": C.MSG_SEAT_UNAVAILABLE}
        decision = default_retry_decider(result)
        assert decision.action == RetryDecision.SKIP

    def test_invalid_request(self):
        result = {"MESSAGE": C.MSG_INVALID_REQUEST}
        decision = default_retry_decider(result)
        assert decision.action == RetryDecision.STOP
        assert "非法请求" in decision.reason

    def test_generic_failure(self):
        # 使用一个已知会返回 failed 的结果
        result = {"CODE": "error", "MESSAGE": "未知错误"}
        decision = default_retry_decider(result)
        assert decision.action == RetryDecision.SKIP

    def test_data_msg_fallback(self):
        """消息在 DATA.msg 字段时也应能识别。"""
        result = {"DATA": {"msg": C.MSG_SEAT_UNAVAILABLE}}
        decision = default_retry_decider(result)
        assert decision.action == RetryDecision.SKIP


class TestBookingResult:
    def test_success_result(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )
        result = BookingResult(plan, success=True, message="预约成功")
        assert result.success is True
        assert "成功" in repr(result)

    def test_failure_result(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )
        result = BookingResult(plan, success=False, message="预约失败")
        assert result.success is False
        assert "失败" in repr(result)

    def test_raw_response_stored(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="001",
            start_hour=8,
            duration_hours=4,
        )
        raw = {"CODE": "ok", "MESSAGE": "done"}
        result = BookingResult(plan, success=True, message="ok", raw_response=raw)
        assert result.raw_response == raw

    def test_timestamp_is_iso(self):
        plan = BookingPlan(
            room_type=1,
            floor_id=1,
            seat_num="1",
            start_hour=1,
            duration_hours=1,
        )
        result = BookingResult(plan, False, "msg")
        assert "T" in result.timestamp  # ISO 格式


class TestBookingOrchestrator:
    """预约编排器测试（含 mock）。"""

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

    def make_orchestrator(self, client=None, **kwargs):
        gateway = client or MagicMock()
        strategy = kwargs.pop("strategy", FixedSeatStrategy())
        notifier = kwargs.pop("notifier", ConsoleNotification(use_colors=False))
        return BookingOrchestrator(
            gateway=gateway,
            strategy=strategy,
            notifier=notifier,
            **kwargs,
        )

    @staticmethod
    def _setup_mock_for_full_booking(client, seat_title="296", seat_id="seat_296"):
        """设置 mock client 以完成完整预约流程。"""
        floor = {
            "roomName": "3楼",
            "seatMap": {
                "info": {"id": "1558"},
                "POIs": [{"title": seat_title, "id": seat_id}],
            },
        }
        client.get_room_types.return_value = [
            {
                "name": "自习室",
                "query": "space_category[category_id]=10&space_category[content_id]=20",
            }
        ]
        client.get_room_detail.return_value = {
            "space_category": {"category_id": "10", "content_id": "20"}
        }
        client.get_seat_map.return_value = [floor]
        # FixedSeatStrategy 会调用 client.find_seat_in_floors
        client.find_seat_in_floors.return_value = (floor, floor["seatMap"]["POIs"][0])
        client.uid = "12345"

    # ------------------------------------------------------------------
    # 单次预约成功路径
    # ------------------------------------------------------------------
    def test_book_single_success_flow(self):
        """完整成功路径：房间查询 → 详情 → 座位图 → 策略 → 预约。"""
        client = MagicMock()
        self._setup_mock_for_full_booking(client)
        client.book_seat.return_value = {"CODE": "ok", "MESSAGE": "预约成功"}

        orchestrator = self.make_orchestrator(client)
        plan = self.make_plan()
        result = orchestrator.book_single(plan)

        assert result.success is True
        assert "成功" in result.message

    # ------------------------------------------------------------------
    # 单次预约失败路径
    # ------------------------------------------------------------------
    def test_book_single_room_type_failure(self):
        client = MagicMock()
        client.get_room_types.side_effect = HduLibraryError("网络错误")

        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(self.make_plan())
        assert result.success is False
        assert "房间类型查询失败" in result.message

    def test_book_single_room_detail_failure(self):
        client = MagicMock()
        client.get_room_types.return_value = [{"name": "自习室", "query": "q"}]
        client.get_room_detail.side_effect = HduLibraryError("详情查询失败")

        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(self.make_plan())
        assert result.success is False
        assert "房间详情查询失败" in result.message

    def test_book_single_seat_map_failure(self):
        client = MagicMock()
        client.get_room_types.return_value = [{"name": "自习室", "query": "q"}]
        client.get_room_detail.return_value = {
            "space_category": {"category_id": "10", "content_id": "20"}
        }
        client.get_seat_map.side_effect = HduLibraryError("座位地图错误")

        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(self.make_plan())
        assert result.success is False
        assert "座位地图查询失败" in result.message

    def test_book_single_no_rooms_available(self):
        client = MagicMock()
        client.get_room_types.return_value = []

        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(self.make_plan())
        assert result.success is False

    def test_book_single_booking_request_failure(self):
        client = MagicMock()
        self._setup_mock_for_full_booking(client)
        client.book_seat.side_effect = HduLibraryError("预约提交失败")

        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(self.make_plan())
        assert result.success is False
        assert "预约请求失败" in result.message

    def test_book_single_server_rejects(self):
        """服务器返回 CODE!=ok 应识别为失败。"""
        client = MagicMock()
        self._setup_mock_for_full_booking(client)
        client.book_seat.return_value = {"CODE": "error", "MESSAGE": "预约失败"}

        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(self.make_plan())
        assert result.success is False

    # ------------------------------------------------------------------
    # 预览模式
    # ------------------------------------------------------------------
    def test_dry_run_mode(self):
        client = MagicMock()
        self._setup_mock_for_full_booking(client)

        orchestrator = self.make_orchestrator(client)
        orchestrator.dry_run = True
        result = orchestrator.book_single(self.make_plan())
        assert result.success is True
        assert "预览模式" in result.message

    # ------------------------------------------------------------------
    # 批量预约
    # ------------------------------------------------------------------
    def test_book_all_first_plan_succeeds(self):
        """首个方案成功即停止。"""
        client = MagicMock()
        self._setup_mock_for_full_booking(client, seat_title="296", seat_id="seat_296")
        client.book_seat.return_value = {"CODE": "ok", "MESSAGE": "预约成功"}

        orchestrator = self.make_orchestrator(client)
        plans = [
            self.make_plan(seat_num="296"),
            self.make_plan(seat_num="297"),
        ]
        results = orchestrator.book_all(plans, max_trials=1)
        # 仅应有 1 条结果（第一个成功即返回）
        assert len(results) == 1
        assert results[0].success is True

    def test_book_all_cancellation(self):
        """取消令牌应在迭代中生效。"""
        client = MagicMock()
        cancellation = CancellationToken()
        cancellation.cancel()

        orchestrator = self.make_orchestrator(client, cancellation=cancellation)
        plans = [self.make_plan()]
        results = orchestrator.book_all(plans, max_trials=3)
        assert len(results) >= 1
        assert "取消" in results[0].message

    def test_book_all_stop_on_invalid_request(self):
        """非法请求应触发 STOP 并立即返回。"""
        client = MagicMock()
        self._setup_mock_for_full_booking(client, seat_title="296", seat_id="seat_296")
        client.book_seat.return_value = {"MESSAGE": C.MSG_INVALID_REQUEST}

        orchestrator = self.make_orchestrator(client)
        plans = [
            self.make_plan(seat_num="296"),
            self.make_plan(seat_num="297"),
        ]
        results = orchestrator.book_all(plans, max_trials=3)
        # 非法请求应立即停止
        assert len(results) == 1

    # ------------------------------------------------------------------
    # format_success_body
    # ------------------------------------------------------------------
    def test_format_success_body(self):
        plan = self.make_plan()
        result = BookingResult(plan, True, "预约成功")
        body = BookingOrchestrator._format_success_body(result)
        assert "1:1558:296:13:9" in body
        assert "预约成功" in body

    # ------------------------------------------------------------------
    # 定时预约
    # ------------------------------------------------------------------
    def test_book_at_already_passed(self):
        """执行时间已过时，应立即执行。"""
        from datetime import datetime, timedelta

        client = MagicMock()
        self._setup_mock_for_full_booking(client)
        client.book_seat.return_value = {"CODE": "ok", "MESSAGE": "成功"}

        orchestrator = self.make_orchestrator(client)
        past_time = datetime.now().astimezone() - timedelta(hours=1)
        plans = [self.make_plan()]
        results = orchestrator.book_at(plans, past_time)
        assert len(results) >= 1

    def test_book_at_cancelled(self):
        """定时等待期间取消应抛出 BookingCancelled。"""
        from datetime import datetime, timedelta

        from hdu_library_booking.exceptions import BookingCancelled

        cancellation = CancellationToken()
        orchestrator = self.make_orchestrator(
            MagicMock(),
            cancellation=cancellation,
        )
        future = datetime.now().astimezone() + timedelta(seconds=10)
        plans = [self.make_plan()]

        # 在后台取消
        import threading

        def cancel_soon():
            import time

            time.sleep(0.1)
            cancellation.cancel()

        threading.Thread(target=cancel_soon, daemon=True).start()

        with pytest.raises(BookingCancelled, match="用户取消"):
            orchestrator.book_at(plans, future)


class TestBookSingleRoomTypeMatching:
    """book_single 房间类型精确匹配测试。"""

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

    def make_orchestrator(self, client=None, **kwargs):
        gateway = client or MagicMock()
        strategy = kwargs.pop("strategy", FixedSeatStrategy())
        notifier = kwargs.pop("notifier", ConsoleNotification(use_colors=False))
        return BookingOrchestrator(
            gateway=gateway,
            strategy=strategy,
            notifier=notifier,
            **kwargs,
        )

    def test_match_by_room_query(self):
        """plan 带 room_query 时，应精确匹配 query 字符串。"""
        client = MagicMock()
        target_query = "space_category[category_id]=10&space_category[content_id]=20"
        client.get_room_types.return_value = [
            {"name": "自习室", "query": target_query},
            {
                "name": "阅览室",
                "query": "space_category[category_id]=30&space_category[content_id]=40",
            },
        ]
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
        client.uid = "12345"
        client.book_seat.return_value = {"CODE": "ok", "MESSAGE": "预约成功"}

        plan = self.make_plan(room_query=target_query)
        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(plan)

        assert result.success is True
        # 验证 get_room_detail 使用了正确的 query
        client.get_room_detail.assert_called_once_with(target_query)

    def test_match_by_name_exact(self):
        """plan 不带 room_query 时，用 ROOM_TYPE_MAP 精确名字匹配。"""
        client = MagicMock()
        client.get_room_types.return_value = [
            {"name": "自习室", "query": "q1"},
            {"name": "阅览室", "query": "q2"},
        ]
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
        client.uid = "12345"
        client.book_seat.return_value = {"CODE": "ok", "MESSAGE": "预约成功"}

        plan = self.make_plan(room_type=1)  # room_type=1 → "自习室"
        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(plan)

        assert result.success is True

    def test_no_match_returns_failure(self):
        """无匹配房间类型时，应返回失败（而非静默回退到第一个）。"""
        client = MagicMock()
        client.get_room_types.return_value = [
            {"name": "自习室", "query": "q1"},
        ]
        client.uid = "12345"

        # room_type=4（讨论室），但 API 只返回"自习室"
        plan = self.make_plan(room_type=4)
        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(plan)

        assert result.success is False
        assert "未找到匹配的房间类型" in result.message

    def test_no_match_does_not_fallback_to_first(self):
        """验证无匹配时不会错误地使用第一个房间类型。"""
        client = MagicMock()
        client.get_room_types.return_value = [
            {"name": "自习室", "query": "q_study"},
        ]
        client.uid = "12345"

        plan = self.make_plan(room_type=3)  # 阅览室
        orchestrator = self.make_orchestrator(client)
        result = orchestrator.book_single(plan)

        # 不应调用 get_room_detail（说明没有回退到第一个房间）
        client.get_room_detail.assert_not_called()
        assert result.success is False


class TestOnProgressExceptionHandling:
    """on_progress 回调异常不中断预约流程测试。"""

    def test_on_progress_exception_does_not_abort(self):
        """on_progress 抛异常时，book_all 应继续执行。"""
        from hdu_library_booking.exceptions import HduLibraryError

        client = MagicMock()
        client.get_room_types.side_effect = HduLibraryError("网络错误")

        orchestrator = BookingOrchestrator(
            gateway=client,
            strategy=FixedSeatStrategy(),
            notifier=ConsoleNotification(use_colors=False),
        )

        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
        )

        # on_progress 抛异常
        def bad_callback(result):
            raise RuntimeError("UI 崩溃")

        results = orchestrator.book_all([plan], max_trials=1, on_progress=bad_callback)

        # 虽然失败，但不应因 on_progress 异常而中断
        assert len(results) == 1
        assert results[0].success is False
