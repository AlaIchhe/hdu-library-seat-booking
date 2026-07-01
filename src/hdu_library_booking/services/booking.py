"""
预约编排服务。

协调房间查询 → 座位选择 → 预约提交的完整流程，
含智能重试、定时执行、预览模式。

容错策略：
  - 应用层：指数退避 + 抖动重试（仅重试瞬时错误）
  - 熔断器：连续失败后暂停，防止雪崩
  - 整体超时：墙钟超时保护
  - Transport 层：连接池 + 5xx 自动重试
"""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

from core import constants as C
from core.domain.booking_result import booking_failed, booking_message
from core.domain.time import build_begin_time
from core.exceptions import (
    BookingCancelled,
    HduLibraryError,
)
from core.infrastructure.protocols import ILibraryGateway
from core.metrics import ErrorCategory, error_tracker
from core.observability import get_logger, metrics_collector, set_correlation_id
from core.resilience import (
    CircuitBreaker,
    TimeoutConfig,
    deadline,
)

from ..models.plan import BookingPlan
from .base import (
    CancellationToken,
    INotificationChannel,
    ISeatSelectionStrategy,
    ITaskCancellation,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 计时器辅助
# ---------------------------------------------------------------------------


@contextmanager
def _timer(operation: str, labels: dict[str, str] | None = None) -> Iterator[None]:
    """自动记录操作耗时的上下文管理器。"""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        metrics_collector.observe_latency(
            "booking_operation_duration_seconds",
            elapsed,
            labels={"operation": operation, **(labels or {})},
        )


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

    def __repr__(self) -> str:
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
      - circuit_breaker: 熔断器（可选）
      - timeout_config: 超时配置（可选）

    容错策略：
      - 熔断器：连续 N 次失败后暂停 M 秒
      - 整体超时：墙钟超时保护
      - 智能重试：基于服务器消息的 CONTINUE/SKIP/STOP 决策
    """

    def __init__(
        self,
        gateway: ILibraryGateway,
        strategy: ISeatSelectionStrategy,
        notifier: INotificationChannel,
        retry_decider: Callable[[dict], RetryDecision] = default_retry_decider,
        cancellation: ITaskCancellation | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout_config: TimeoutConfig | None = None,
    ):
        self.client = gateway
        self.strategy = strategy
        self.notifier = notifier
        self.retry_decider = retry_decider
        self.cancellation = cancellation or CancellationToken()
        self.circuit_breaker = circuit_breaker
        self.timeout_config = timeout_config or TimeoutConfig()

        # 可配置参数（向后兼容）
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
        logger.info(
            "booking_attempt_started",
            plan=plan.to_plan_code(),
            room_type=plan.room_type,
            floor_id=plan.floor_id,
            seat_num=plan.seat_num,
        )

        # 1. 查找房间类型匹配的房间
        try:
            with _timer("get_room_types"):
                room_types = self.client.get_room_types()
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.ROOM_QUERY,
                f"房间类型查询失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            logger.warning(
                "room_type_query_failed",
                plan=plan.to_plan_code(),
                error=str(exc),
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
                logger.warning("no_room_types_available", plan=plan.to_plan_code())
                return BookingResult(plan, False, "无可用房间类型")
            matched = [room_types[0]]

        # 2. 查询房间详情
        room_item = matched[0]
        try:
            with _timer("get_room_detail"):
                detail = self.client.get_room_detail(room_item["query"])
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.ROOM_QUERY,
                f"房间详情查询失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            logger.warning(
                "room_detail_query_failed",
                plan=plan.to_plan_code(),
                error=str(exc),
            )
            return BookingResult(plan, False, f"房间详情查询失败: {exc}")

        cat_id = detail["space_category"]["category_id"]
        con_id = detail["space_category"]["content_id"]

        # 3. 构建查询时间
        begin_time = build_begin_time(plan.start_hour, plan.book_days)

        # 4. 查询座位布局
        try:
            with _timer("get_seat_map"):
                floors = self.client.get_seat_map(cat_id, con_id, begin_time, plan.duration_hours)
        except HduLibraryError as exc:
            error_tracker.record(
                ErrorCategory.SEAT_QUERY,
                f"座位地图查询失败 [{plan.to_plan_code()}]: {exc}",
                exc,
                module=__name__,
            )
            logger.warning(
                "seat_map_query_failed",
                plan=plan.to_plan_code(),
                error=str(exc),
            )
            return BookingResult(plan, False, f"座位地图查询失败: {exc}")

        # 5. 策略选择座位
        with _timer("select_seat"):
            seat_result = self.strategy.select_seat(self.client, plan, floors=floors)
        if seat_result.is_failure:
            reason = seat_result.error
            error_tracker.record(
                ErrorCategory.STRATEGY,
                f"策略未能选出可用座位 [{plan.to_plan_code()}]: {reason}",
                module=__name__,
            )
            logger.warning(
                "seat_selection_failed",
                plan=plan.to_plan_code(),
                reason=reason,
            )
            return BookingResult(plan, False, f"策略未能选出可用座位: {reason}")

        # 6. 提交预约
        seat_id = str(seat_result.value["id"])
        if self.dry_run:
            result = self.client.book_seat(
                seat_id,
                self.client.uid,
                begin_time,
                plan.duration_hours,
                dry_run=True,
            )
            logger.info("dry_run_completed", plan=plan.to_plan_code(), seat_id=seat_id)
            return BookingResult(plan, True, f"[预览模式] 参数已就绪: {result}", result)

        try:
            with _timer("book_seat"):
                result = self.client.book_seat(
                    seat_id,
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
            logger.error(
                "booking_request_failed",
                plan=plan.to_plan_code(),
                seat_id=seat_id,
                error=str(exc),
            )
            return BookingResult(plan, False, f"预约请求失败: {exc}")

        if booking_failed(result):
            msg = booking_message(result)
            error_tracker.record(
                ErrorCategory.BOOKING,
                f"预约被服务器拒绝 [{plan.to_plan_code()}]: {msg}",
                module=__name__,
            )
            logger.warning(
                "booking_rejected_by_server",
                plan=plan.to_plan_code(),
                message=msg,
            )
            return BookingResult(plan, False, msg, result)

        logger.info(
            "booking_succeeded",
            plan=plan.to_plan_code(),
            seat_id=seat_id,
            message=booking_message(result),
        )
        metrics_collector.increment(
            "booking_requests_total",
            labels={"status": "success"},
        )
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

        容错特性：
        - 整体墙钟超时（通过 timeout_config.overall_timeout）
        - 熔断器检查（连续失败后暂停）
        - 关联 ID 自动传播到所有日志

        Returns
        -------
        list[BookingResult]
            所有尝试的结果记录。
        """
        trials = max_trials if max_trials is not None else self.max_trials
        results: list[BookingResult] = []

        # 为本次预约流程设置关联 ID，所有日志自动携带
        with set_correlation_id():
            # 整体墙钟超时保护
            if self.timeout_config.overall_timeout:
                try:
                    with deadline(self.timeout_config.overall_timeout):
                        return self._book_all_internal(plans, trials, results, on_progress)
                except TimeoutError:
                    logger.error(
                        "booking_flow_timeout",
                        timeout=self.timeout_config.overall_timeout,
                        plans_attempted=len(plans),
                        results_count=len(results),
                    )
                    if results:
                        last = results[-1]
                        self.notifier.send(
                            "预约超时",
                            f"操作超时（{self.timeout_config.overall_timeout:.0f}秒），"
                            f"已尝试 {len(results)} 次。最后状态: {last.message}",
                            success=False,
                        )
                    return results

            return self._book_all_internal(plans, trials, results, on_progress)

    def _book_all_internal(
        self,
        plans: list[BookingPlan],
        trials: int,
        results: list[BookingResult],
        on_progress: Callable[[BookingResult], None] | None,
    ) -> list[BookingResult]:
        """批量预约的内部实现（在整体超时保护内执行）。"""
        logger.info(
            "booking_flow_started",
            plan_count=len(plans),
            max_trials=trials,
        )
        metrics_collector.increment("booking_flows_started_total")

        for plan in plans:
            if self.cancellation.is_cancelled():
                logger.info("booking_cancelled_by_user", plan=plan.to_plan_code())
                results.append(BookingResult(plan, False, "用户取消"))
                break

            # 熔断器检查
            if self.circuit_breaker and not self.circuit_breaker.can_execute():
                logger.warning(
                    "circuit_breaker_open",
                    plan=plan.to_plan_code(),
                    state=self.circuit_breaker.state.value,
                )
                self.notifier.send(
                    "预约中止",
                    "服务暂时不可用（熔断器已打开），请稍后重试。",
                    success=False,
                )
                return results

            for attempt in range(1, trials + 1):
                if self.cancellation.is_cancelled():
                    logger.info(
                        "booking_cancelled_by_user_mid_attempt",
                        plan=plan.to_plan_code(),
                        attempt=attempt,
                    )
                    results.append(BookingResult(plan, False, "用户取消"))
                    break

                logger.info(
                    "booking_attempt",
                    plan=plan.to_plan_code(),
                    attempt=attempt,
                    max_trials=trials,
                )
                result = self.book_single(plan)
                results.append(result)

                if on_progress:
                    on_progress(result)

                if result.success:
                    # 通知熔断器成功
                    if self.circuit_breaker:
                        self.circuit_breaker.record_success()
                    self.notifier.send(
                        "预约成功！",
                        self._format_success_body(result),
                        success=True,
                    )
                    logger.info(
                        "booking_flow_completed",
                        attempts=len(results),
                        plan=plan.to_plan_code(),
                    )
                    return results

                # 通知熔断器失败
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure()

                # 智能重试决策
                if result.raw_response:
                    decision = self.retry_decider(result.raw_response)
                    logger.info(
                        "retry_decision",
                        action=decision.action,
                        reason=decision.reason,
                        plan=plan.to_plan_code(),
                    )

                    if decision.action == RetryDecision.STOP:
                        self.notifier.send(
                            "预约中止",
                            f"服务器返回: {decision.reason}\n请检查系统是否需要更新。",
                            success=False,
                        )
                        logger.error(
                            "booking_flow_aborted",
                            reason=decision.reason,
                            plan=plan.to_plan_code(),
                        )
                        return results

                    if decision.action == RetryDecision.SKIP:
                        logger.info(
                            "plan_skipped",
                            plan=plan.to_plan_code(),
                            reason=decision.reason,
                        )
                        break  # 跳出重试循环，进入下一个 plan

                # 重试延迟（使用指数退避替代固定延迟）
                if attempt < trials:
                    delay = self._backoff_delay(attempt)
                    logger.debug("retry_delay", delay=delay, attempt=attempt)
                    time.sleep(delay)

        # 全部失败
        if results:
            last = results[-1]
            self.notifier.send(
                "预约失败",
                f"已尝试 {len(plans)} 个方案，共 {len(results)} 次请求，均未成功。\n"
                f"最后错误: {last.message}",
                success=False,
            )
            logger.warning(
                "booking_flow_failed",
                plans_attempted=len(plans),
                total_attempts=len(results),
                last_error=last.message,
            )
            metrics_collector.increment(
                "booking_requests_total",
                labels={"status": "failed"},
            )

        return results

    def _backoff_delay(self, attempt: int) -> float:
        """计算指数退避延迟（带抖动）。

        Parameters
        ----------
        attempt : int
            当前尝试次数（从 1 开始）。

        Returns
        -------
        float
            延迟秒数。
        """
        import random

        # 指数退避: delay * 2^(attempt-1)
        delay = self.retry_delay * (2 ** (attempt - 1))
        # 全抖动: [0, delay]
        jitter = random.uniform(0, delay)
        return jitter

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
                "scheduled_booking_waiting",
                execute_at=execute_at.isoformat(),
                wait_seconds=round(wait_seconds),
            )

        while wait_seconds > 0:
            if self.cancellation.is_cancelled():
                logger.info("scheduled_booking_cancelled", plan_count=len(plans))
                raise BookingCancelled("用户取消定时预约")

            if on_countdown:
                on_countdown(int(wait_seconds))

            sleep_for = min(1.0, wait_seconds)
            time.sleep(sleep_for)
            wait_seconds -= sleep_for

        logger.info("scheduled_booking_executing", plan_count=len(plans))
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
