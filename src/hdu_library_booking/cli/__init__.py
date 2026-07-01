"""
命令行一次性执行界面 (FR-7.3)。

支持通过命令行参数直接指定所有预约参数，
适用于脚本调用、cron 定时任务或环境变量配置。
"""

import argparse
import sys

from hdu_library_booking.api import HduLibraryClient
from hdu_library_booking.config import get_settings
from hdu_library_booking.models.time_utils import build_begin_time, build_execute_datetime
from hdu_library_booking.observability._error_tracker import ErrorCategory, error_tracker

from ..models.plan import BookingPlan
from ..services.auth import AuthService
from ..services.booking import (
    BookingOrchestrator,
    BookingResult,
    default_retry_decider,
)
from ..services.interfaces import ISeatSelectionStrategy
from ..services.notifications import (
    ConsoleNotification,
    LogFileNotification,
    NotificationAggregator,
    WeChatNotification,
)
from ..services.plan import PlanService
from ..strategies.fixed import FixedSeatStrategy
from ..strategies.random_range import RandomRangeStrategy
from ..strategies.weekday import WeekdayRotationStrategy


class CLI:
    """一次性命令行预约执行器。"""

    def __init__(self) -> None:
        self.exit_code: int = 0

    def run(self, context: dict | None = None) -> int:
        """解析命令行参数并执行预约。"""
        parser = self._build_parser()
        args = parser.parse_args()

        # --report / --report-json：打印错误追踪报告后退出
        if args.report:
            print(error_tracker.summary())
            return 0
        if args.report_json:
            error_tracker.export_json(args.report_json)
            print(f"错误报告已导出至: {args.report_json}")
            print(f"共 {error_tracker.total()} 条错误记录")
            return 0

        # 加载统一配置 (默认值 < .env < config.yaml < 环境变量)
        settings = get_settings()

        # CLI 参数覆盖
        settings = settings.with_cli_overrides(
            auth__cookie=args.cookie,
            auth__cookie_file=args.cookie_file,
            booking__max_trials=args.max_trials,
            booking__retry_delay=args.retry_delay,
            booking__dry_run=args.dry_run,
            strategy__type=args.strategy,
            notification__wechat_webhook=args.wechat_webhook,
            logging__file=args.log_file,
        )

        # 构建客户端
        client = HduLibraryClient(settings=settings)
        auth = AuthService(client)

        # 认证
        self._authenticate(args, auth)

        # 解析方案
        plans = self._resolve_plans(args)
        if not plans:
            error_tracker.record(
                ErrorCategory.BOOKING_VALIDATION,
                "CLI 无可用的预约方案",
                module=__name__,
            )
            print("没有可用的预约方案")
            return 1

        # 构建策略
        strategy = self._build_strategy(args)

        # 构建通知
        notifier = self._build_notifier(args)

        # 预览模式
        if args.dry_run:
            print("[预览模式] 将生成预约请求但不实际提交\n")
            for plan in plans:
                print(f"  方案: {plan.to_plan_code()}")
                print(f"    房间类型: {plan.room_type}")
                print(f"    楼层 ID: {plan.floor_id}")
                print(f"    座位号: {plan.seat_num}")
                print(f"    开始时间: {build_begin_time(plan.start_hour, plan.book_days)}")
                print(f"    时长: {plan.duration_hours}h")
                print()
            print("参数检查完毕，退出预览模式。")
            return 0

        # 执行
        orchestrator = BookingOrchestrator(
            gateway=client,
            strategy=strategy,
            notifier=notifier,
            retry_decider=default_retry_decider,
        )
        orchestrator.max_trials = args.max_trials
        orchestrator.retry_delay = args.retry_delay

        def on_progress(result: BookingResult) -> None:
            icon = "OK" if result.success else "FAIL"
            print(f"[{icon}] {result.plan.to_plan_code()} → {result.message}")

        # 定时 or 立即
        if args.execute_at:
            execute_at = build_execute_datetime(args.execute_at)
            if execute_at is None:
                print(f"无效的执行时间: {args.execute_at}")
                return 1
            print(f"定时预约: {execute_at.isoformat()}")
            results = orchestrator.book_at(plans, execute_at, on_progress=on_progress)
        else:
            results = orchestrator.book_all(plans, on_progress=on_progress)

        # 退出码
        if any(r.success for r in results):
            self.exit_code = 0
        else:
            self.exit_code = 1
        return self.exit_code

    # ------------------------------------------------------------------
    # 参数解析
    # ------------------------------------------------------------------
    def _build_parser(self) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(
            prog="hdu-book",
            description="HDU 图书馆座位预约 — 命令行模式",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  hdu-book --cookie "uid=xxx;auth=yyy" --plan "1:1558:296:13:9"
  hdu-book --cookie-file cookies.json --plan "1:1558:296:13:9"
  hdu-book --cookie "..." --plan-file plans.yaml --dry-run
  hdu-book --cookie "..." --plan "..." --at "19:59:30" --max-trials 30

环境变量:
  HDU_COOKIE, HDU_COOKIE_FILE
  HDU_PLAN, HDU_PLAN_FILE, HDU_AT, HDU_MAX_TRIALS
            """,
        )

        # 认证
        auth_group = p.add_argument_group("认证")
        auth_group.add_argument("--cookie", help="Cookie 字符串")
        auth_group.add_argument("--cookie-file", help="Netscape JSON Cookie 文件路径")

        # 方案
        plan_group = p.add_argument_group("预约方案")
        plan_group.add_argument(
            "--plan",
            action="append",
            dest="plans",
            help="方案编码 roomType:floorId:seatNum:startHour:durationHours（可重复）",
        )
        plan_group.add_argument("--plan-file", help="YAML 方案文件路径")

        # 策略
        strategy_group = p.add_argument_group("策略")
        strategy_group.add_argument(
            "--strategy",
            choices=["fixed", "random", "weekday"],
            default="fixed",
            help="座位选择策略 (默认: fixed)",
        )

        # 执行
        exec_group = p.add_argument_group("执行")
        exec_group.add_argument("--at", dest="execute_at", help="定时执行时间 (HH:MM 或 HH:MM:SS)")
        exec_group.add_argument("--max-trials", type=int, default=5, help="最大重试次数 (默认: 5)")
        exec_group.add_argument(
            "--retry-delay", type=float, default=1.0, help="重试间隔秒数 (默认: 1.0)"
        )
        exec_group.add_argument("--dry-run", action="store_true", help="预览模式，不实际提交")

        # 通知
        notif_group = p.add_argument_group("通知")
        notif_group.add_argument("--wechat-webhook", help="微信推送 Webhook URL")
        notif_group.add_argument("--log-file", default="booking.log", help="日志文件路径")

        # 诊断
        diag_group = p.add_argument_group("诊断")
        diag_group.add_argument(
            "--report",
            action="store_true",
            help="打印错误追踪报告并退出",
        )
        diag_group.add_argument(
            "--report-json",
            metavar="PATH",
            help="将错误追踪报告导出为 JSON 文件",
        )

        return p

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _authenticate(self, args: argparse.Namespace, auth: AuthService) -> None:
        """认证失败时抛出异常而非返回 bool。"""
        if args.cookie:
            auth.authenticate_with_cookie(args.cookie)
            return
        if args.cookie_file:
            auth.authenticate_with_cookie_file(args.cookie_file)
            return
        print("未提供认证信息（--cookie / --cookie-file）")
        sys.exit(1)

    def _build_strategy(self, args: argparse.Namespace) -> ISeatSelectionStrategy:
        """根据参数构建座位选择策略。"""
        strategy_name = getattr(args, "strategy", "fixed")
        if strategy_name == "random":
            return RandomRangeStrategy(seat_range=(1, 500))
        if strategy_name == "weekday":
            return WeekdayRotationStrategy(weekday_configs={})
        return FixedSeatStrategy()

    def _resolve_plans(self, args: argparse.Namespace) -> list[BookingPlan]:
        plans = []

        # 从文件加载
        if args.plan_file:
            from ..services.yaml_plan import YamlPlanRepository

            repo = YamlPlanRepository(args.plan_file)
            plan_service = PlanService(repo)
            plans.extend(plan_service.list_enabled())

        # 从 --plan 参数
        if args.plans:
            for code in args.plans:
                try:
                    plans.append(BookingPlan.from_plan_code(code))
                except ValueError as exc:
                    error_tracker.record(
                        ErrorCategory.BOOKING_VALIDATION,
                        f"CLI 方案编码解析失败: {code}",
                        exc,
                        module=__name__,
                    )
                    print(f"方案编码 '{code}' 解析失败: {exc}")

        return plans

    def _build_notifier(self, args: argparse.Namespace) -> NotificationAggregator:
        agg = NotificationAggregator()
        agg.add_channel(ConsoleNotification(use_colors=True))
        agg.add_channel(LogFileNotification(args.log_file))
        if args.wechat_webhook:
            agg.add_channel(WeChatNotification(args.wechat_webhook))
        return agg


# ======================================================================
# 入口
# ======================================================================
def main() -> None:
    """CLI 主入口。"""
    _configure_observability()
    cli = CLI()
    sys.exit(cli.run())


def _configure_observability() -> None:
    """初始化结构化日志。"""
    from hdu_library_booking.config import get_settings
    from hdu_library_booking.observability import configure_from_config

    settings = get_settings()
    configure_from_config(settings.logging_cfg)


if __name__ == "__main__":
    main()
