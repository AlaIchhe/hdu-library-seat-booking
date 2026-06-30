"""
命令行一次性执行界面 (FR-7.3)。

支持通过命令行参数直接指定所有预约参数，
适用于脚本调用、cron 定时任务或环境变量配置。
"""

import argparse
import os
import sys

from core import HduLibraryClient
from core.metrics import ErrorCategory, error_tracker
from core.utils import (
    build_begin_time,
    build_execute_datetime,
)

from ..models.plan import BookingPlan
from ..services.auth_service import AuthService
from ..services.booking_service import (
    BookingOrchestrator,
    BookingResult,
    default_retry_decider,
)
from ..services.notification_service import (
    ConsoleNotification,
    LogFileNotification,
    NotificationAggregator,
    WeChatNotification,
)
from ..services.plan_service import PlanService
from ..strategies.fixed_seat import FixedSeatStrategy


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

        # 环境变量合并
        self._merge_env(args)

        # 构建客户端
        client = self._build_client(args)
        auth = AuthService(client)

        # 认证
        if not self._authenticate(args, auth):
            error_tracker.record(
                ErrorCategory.AUTH,
                "CLI 认证失败",
                module=__name__,
            )
            print("认证失败，退出")
            return 1

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
        strategy = FixedSeatStrategy()

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
            client,
            strategy,
            notifier,
            retry_decider=default_retry_decider,
        )
        orchestrator.max_trials = args.max_trials
        orchestrator.retry_delay = args.retry_delay

        def on_progress(result: BookingResult):
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
  hdu-book --user 21012345 --passwd mypass --plan "1:1558:130:8:9"
  hdu-book --cookie "..." --plan-file plans.yaml --dry-run
  hdu-book --cookie "..." --plan "..." --at "19:59:30" --max-trials 30

环境变量:
  HDU_COOKIE, HDU_USERNAME, HDU_PASSWORD, HDU_ORG_ID
  HDU_PLAN, HDU_PLAN_FILE, HDU_AT, HDU_MAX_TRIALS
            """,
        )

        # 认证
        auth_group = p.add_argument_group("认证")
        auth_group.add_argument("--cookie", help="Cookie 字符串")
        auth_group.add_argument("--cookie-file", help="Netscape JSON Cookie 文件路径")
        auth_group.add_argument("--user", dest="username", help="学号/登录名")
        auth_group.add_argument("--passwd", dest="password", help="密码")
        auth_group.add_argument("--org-id", default=None, help="机构 ID (默认: 104)")

        # 方案
        plan_group = p.add_argument_group("预约方案")
        plan_group.add_argument(
            "--plan",
            action="append",
            dest="plans",
            help="方案编码 roomType:floorId:seatNum:startHour:durationHours（可重复）",
        )
        plan_group.add_argument("--plan-file", help="YAML 方案文件路径")

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
    def _merge_env(self, args) -> None:
        """将环境变量合并到 args。"""
        env_map = {
            "cookie": "HDU_COOKIE",
            "username": "HDU_USERNAME",
            "password": "HDU_PASSWORD",
            "org_id": "HDU_ORG_ID",
            "execute_at": "HDU_AT",
        }
        for attr, env_var in env_map.items():
            if not getattr(args, attr, None):
                setattr(args, attr, os.environ.get(env_var))

        if not args.plans:
            env_plan = os.environ.get("HDU_PLAN")
            if env_plan:
                args.plans = [env_plan]

        if not args.plan_file:
            args.plan_file = os.environ.get("HDU_PLAN_FILE")

        if args.max_trials == 5:  # default
            env_trials = os.environ.get("HDU_MAX_TRIALS")
            if env_trials:
                args.max_trials = int(env_trials)

    def _build_client(self, args) -> HduLibraryClient:
        return HduLibraryClient()

    def _authenticate(self, args, auth: AuthService) -> bool:
        if args.cookie:
            return auth.authenticate_with_cookie(args.cookie)
        if args.cookie_file:
            return auth.authenticate_with_cookie_file(args.cookie_file)
        if args.username:
            return auth.authenticate_with_password(
                username=args.username,
                password=args.password or "",
                org_id=args.org_id,
            )
        # 尝试从 config 登录
        if auth.client.config.get("user_info", {}).get("login_name"):
            return auth.authenticate_with_password()
        print("未提供认证信息（--cookie / --user --passwd）")
        return False

    def _resolve_plans(self, args) -> list[BookingPlan]:
        plans = []

        # 从文件加载
        if args.plan_file:
            from ..services.plan_repository import YamlPlanRepository

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

    def _build_notifier(self, args) -> NotificationAggregator:
        agg = NotificationAggregator()
        agg.add_channel(ConsoleNotification(use_colors=True))
        agg.add_channel(LogFileNotification(args.log_file))
        if args.wechat_webhook:
            agg.add_channel(WeChatNotification(args.wechat_webhook))
        return agg


# ======================================================================
# 入口
# ======================================================================
def main():
    """CLI 主入口。"""
    cli = CLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()
