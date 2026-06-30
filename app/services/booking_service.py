"""
预约编排服务。

协调房间查询 → 座位选择 → 预约提交的完整流程，
含智能重试、定时执行、预览模式。
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime

from core import HduLibraryClient
from core import constants as C
from core.exceptions import (
    BookingCancelled,
    HduLibraryError,
)
from core.metrics import ErrorCategory, error_tracker
from core.utils import (
    booking_failed,
    booking_message,
    build_begin_time,
)

from ..models.plan import BookingPlan
from .base import (
    CancellationToken,
    INotificationChannel,
    ISeatSelectionStrategy,
    ITaskCancellation,
)

logger = logging.getLogger(__name__)


# ======================================================================
# 预约结果
# ======================================================================
class BookingResult:
    """一次预约尝试的结果。"""

    def __init__(
        self,
        plan: BookingPlan,
        success: bool = False,
        message: str = "",
        raw_response: dict | None = None,
    ):
        self.plan = plan
        self.success = success
        self.message = message
        self.raw_response = raw_response
        self.timestamp = datetime.now().isoformat()

    def __repr__(self):
        status = "✓ 成功" if self.success else "✗ 失败"
        return f"BookingResult({status}, {self.plan.to_plan_code()}, {self.message})"


# ======================================================================
# 智能重试决策
# ======================================================================
class RetryDecision:
    """服务器错误消息 → 重试行为 的决策结果。"""

    CONTINUE = "continue"  # 继续重试
    SKIP = "skip"  # 跳过当前方案，试下一个
    STOP = "stop"  # 停止全部尝试

    def __init__(self, action: str, reason: str):
        self.action = action
        self.reason = reason


def default_retry_decider(result: dict) -> RetryDecision:
    """默认的服务器错误消息 → 重试决策逻辑。

    根据 requirements FR-4.3 的规则表：
    - 超出可预约时间范围 → 等待后重试
    - 已有预约，请勿重复 → 放弃当前计划
    - 座位无法预约 → 放弃当前方案，尝试下一个
    - 非法请求 → 立即停止
    """
    message = str(result.get("MESSAGE") or (result.get("DATA") or {}).get("msg") or "")

    if C.MSG_TIME_OUT_OF_RANGE in message:
        return RetryDecision(RetryDecision.CONTINUE, "预约窗口尚未开放，等待后重试")
    if C.MSG_DUPLICATE in message:
        return RetryDecision(RetryDecision.SKIP, "已有预约，无需重复")
    if C.MSG_SEAT_UNAVAILABLE in message:
        return RetryDecision(RetryDecision.SKIP, "座位不可用，换下一个方案")
    if C.MSG_INVALID_REQUEST in message:
        return RetryDecision(RetryDecision.STOP, "非法请求 — 请检查系统更新")

    # 默认：若预约失败则跳过当前方案
    if booking_failed(result):
        return RetryDecision(RetryDecision.SKIP, booking_message(result))
    return RetryDecision(RetryDecision.CONTINUE, "")


# ======================================================================
# 预约编排器
# ======================================================================
class BookingOrchestrator:
    """预约流程编排器 (SRP: 只协调预约执行流程)。

    依赖注入：
      - client: HduLibraryClient
      - strategy: ISeatSelectionStrategy
      - notifier: INotificationChannel
      - retry_decider: 重试决策函数
      - cancellation: ITaskCancellation (可选)
    """

    def __init__(
        self,
        client: HduLibraryClient,
        strategy: ISeatSelectionStrategy,
        notifier: INotificationChannel,
        retry_decider: Callable[[dict], RetryDecision] = default_retry_decider,
        cancellation: ITaskCancellation | None = None,
    ):
        self.client = client
        self.strategy = strategy
        self.notifier = notifier
        self.retry_decider = retry_decider
        self.cancellation = cancellation or CancellationToken()

        # 可配置参数
        self.max_trials = C.DEFAULT_MAX_TRIALS
        self.retry_delay = C.DEFAULT_RETRY_DELAY
        self.dry_run = False

    # ------------------------------------------------------------------
    # 单次预约
    # ------------------------------------------------------------------
    def book_single(self, plan: BookingPlan) -> BookingResult:
        """执行单个方案的预约流程。

        流程：
          1. 查询房间类型
          2. 查询房间详情
          3. 查询座位布局
          4. 策略选择座位
          5. 提交预约
        """
        # 1. 查找房间类型匹配的房间
        try:
            room_types = self.client.get_room_types()
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.ROOM_QUERY,
                f"房间类型查询失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            return BookingResult(plan, False, f"房间类型查询失败: {exc}")

        # 匹配 room_type
        matched = [
            r
            for r in room_types
            if str(plan.room_type) in r.get("name", "")
            or C.ROOM_TYPE_MAP.get(str(plan.room_type), "") in r.get("name", "")
        ]
        if not matched:
            # Fallback: use first available
            if not room_types:
                error_tracker.record(
                    ErrorCategory.ROOM_QUERY,
                    f"无可用房间类型 [{plan.to_plan_code()}]",
                    module=__name__,
                )
                return BookingResult(plan, False, "无可用房间类型")
            matched = [room_types[0]]

        # 2. 查询房间详情
        room_item = matched[0]
        try:
            detail = self.client.get_room_detail(room_item["query"])
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.ROOM_QUERY,
                f"房间详情查询失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            return BookingResult(plan, False, f"房间详情查询失败: {exc}")

        cat_id = detail["space_category"]["category_id"]
        con_id = detail["space_category"]["content_id"]

        # 3. 构建查询时间
        begin_time = build_begin_time(plan.start_hour, plan.book_days)

        # 4. 查询座位布局
        try:
            floors = self.client.get_seat_map(cat_id, con_id, begin_time, plan.duration_hours)
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.SEAT_QUERY,
                f"座位地图查询失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            return BookingResult(plan, False, f"座位地图查询失败: {exc}")

        # 5. 策略选择座位
        seat = self.strategy.select_seat(self.client, plan, floors=floors)
        if seat is None:
            error_tracker.record(
                ErrorCategory.STRATEGY,
                f"策略未能选出可用座位 [{plan.to_plan_code()}]",
                module=__name__,
            )
            return BookingResult(plan, False, "策略未能选出可用座位")

        # 6. 提交预约
        if self.dry_run:
            result = self.client.book_seat(
                seat["id"],
                self.client.uid,
                begin_time,
                plan.duration_hours,
                dry_run=True,
            )
            return BookingResult(plan, True, f"[预览模式] 参数已就绪: {result}", result)

        try:
            result = self.client.book_seat(
                seat["id"],
                self.client.uid,
                begin_time,
                plan.duration_hours,
            )
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.BOOKING,
                f"预约请求失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            return BookingResult(plan, False, f"预约请求失败: {exc}")

        if booking_failed(result):
            msg = booking_message(result)
            error_tracker.record(
                ErrorCategory.BOOKING,
                f"预约被服务器拒绝 [{plan.to_plan_code()}]: {msg}",
                module=__name__,
            )
            return BookingResult(plan, False, msg, result)
        return BookingResult(plan, True, booking_message(result), result)

    # ------------------------------------------------------------------
    # 批量预约（含智能重试）
    # ------------------------------------------------------------------
    def book_all(
        self,
        plans: list[BookingPlan],
        max_trials: int | None = None,
        on_progress: Callable[[BookingResult], None] | None = None,
    ) -> list[BookingResult]:
        """依次执行方案列表，含智能重试。

        按 plan 顺序依次尝试，任一成功即停止（FR-4.1）。
        每个 plan 最多重试 max_trials 次。

        Returns
        -------
        list[BookingResult]
            所有尝试的结果记录。
        """
        trials = max_trials if max_trials is not None else self.max_trials
        results: list[BookingResult] = []

        for plan in plans:
            if self.cancellation.is_cancelled():
                results.append(BookingResult(plan, False, "用户取消"))
                break

            for attempt in range(1, trials + 1):
                if self.cancellation.is_cancelled():
                    results.append(BookingResult(plan, False, "用户取消"))
                    break

                logger.info(
                    "尝试方案 [%s] 第 %d/%d 次",
                    plan.to_plan_code(),
                    attempt,
                    trials,
                )
                result = self.book_single(plan)
                results.append(result)

                if on_progress:
                    on_progress(result)

                if result.success:
                    self.notifier.send(
                        "预约成功！",
                        self._format_success_body(result),
                        success=True,
                    )
                    return results

                # 智能重试决策
                if result.raw_response:
                    decision = self.retry_decider(result.raw_response)
                    logger.info("重试决策: %s — %s", decision.action, decision.reason)

                    if decision.action == RetryDecision.STOP:
                        self.notifier.send(
                            "预约中止",
                            f"服务器返回: {decision.reason}\n请检查系统是否需要更新。",
                            success=False,
                        )
                        return results

                    if decision.action == RetryDecision.SKIP:
                        logger.info("跳过方案 %s，尝试下一个", plan.to_plan_code())
                        break  # 跳出重试循环，进入下一个 plan

                # 重试延迟
                if attempt < trials:
                    time.sleep(self.retry_delay)

        # 全部失败
        if results:
            last = results[-1]
            self.notifier.send(
                "预约失败",
                f"已尝试 {len(plans)} 个方案，共 {len(results)} 次请求，均未成功。\n"
                f"最后错误: {last.message}",
                success=False,
            )
        return results

    # ------------------------------------------------------------------
    # 定时预约
    # ------------------------------------------------------------------
    def book_at(
        self,
        plans: list[BookingPlan],
        execute_at: datetime,
        on_countdown: Callable[[int], None] | None = None,
        on_progress: Callable[[BookingResult], None] | None = None,
    ) -> list[BookingResult]:
        """在指定时间执行预约。

        等待期间显示倒计时，可随时取消。

        Parameters
        ----------
        plans : list[BookingPlan]
            方案列表。
        execute_at : datetime
            目标执行时间。
        on_countdown : callable, optional
            每秒回调，接收剩余秒数。
        on_progress : callable, optional
            每次预约尝试的回调。

        Returns
        -------
        list[BookingResult]
        """
        now = datetime.now().astimezone()
        wait_seconds = (execute_at - now).total_seconds()

        if wait_seconds > 0:
            logger.info(
                "定时预约：目标 %s，等待 %.0f 秒",
                execute_at.isoformat(),
                wait_seconds,
            )

        while wait_seconds > 0:
            if self.cancellation.is_cancelled():
                raise BookingCancelled("用户取消定时预约")

            if on_countdown:
                on_countdown(int(wait_seconds))

            sleep_for = min(1.0, wait_seconds)
            time.sleep(sleep_for)
            wait_seconds -= sleep_for

        logger.info("到达预约时间，开始执行")
        return self.book_all(plans, on_progress=on_progress)

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _format_success_body(result: BookingResult) -> str:
        plan = result.plan
        lines = [
            f"方案: {plan.to_plan_code()}",
            f"房间类型: {plan.room_type}",
            f"楼层: {plan.floor_id}",
            f"座位号: {plan.seat_num}",
            f"预约人: {plan.booker_name or '(未设置)'}",
            f"开始时间: {build_begin_time(plan.start_hour, plan.book_days).isoformat()}",
            f"时长: {plan.duration_hours} 小时",
            f"服务器响应: {result.message}",
        ]
        return "\n".join(lines)
