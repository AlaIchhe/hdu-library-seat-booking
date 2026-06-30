"""
终端交互界面 (FR-7.2)。

菜单驱动的 TUI：管理方案、修改时间、立即抢座、定时预约。
"""

import os
import subprocess
import sys

from core import HduLibraryClient
from core.metrics import ErrorCategory, error_tracker
from core.room_cache import RoomCache
from core.utils import (
    build_begin_time,
    build_execute_datetime,
)

from ..models.plan import BookingPlan, PlanStatus
from ..services.auth_service import AuthService
from ..services.booking_service import (
    BookingOrchestrator,
    BookingResult,
)
from ..services.notification_service import ConsoleNotification
from ..services.plan_service import PlanService
from ..strategies.fixed_seat import FixedSeatStrategy
from ..utils.logger import format_countdown


class TerminalUI:
    """终端菜单驱动交互界面。

    符合 IUserInterface 语义（duck-typing），run() 启动主循环。
    """

    def __init__(
        self,
        client: HduLibraryClient,
        plan_service: PlanService,
        auth_service: AuthService | None = None,
    ):
        self.client = client
        self.plans = plan_service
        self.auth = auth_service or AuthService(client)
        self.cache: RoomCache | None = None
        self.cancel_flag = False

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(self, context: dict | None = None) -> int:
        """启动终端主菜单。"""
        self._clear()
        self._print_banner()

        if not self.auth.is_authenticated():
            self._handle_auth()

        self._load_cache()

        while True:
            self._show_menu()
            choice = input("\n请选择 [0-7]: ").strip()

            handlers = {
                "0": self._handle_exit,
                "1": self._handle_list_plans,
                "2": self._handle_create_plan,
                "3": self._handle_modify_time,
                "4": self._handle_delete_plan,
                "5": self._handle_book_now,
                "6": self._handle_book_scheduled,
                "7": self._handle_browse_rooms,
            }

            handler = handlers.get(choice)
            if handler:
                try:
                    result = handler()
                    if result is False:  # exit signal
                        break
                except KeyboardInterrupt:
                    print("\n\n操作已取消")
                except Exception as exc:
                    error_tracker.record(
                        ErrorCategory.UI,
                        f"终端操作异常 [{choice}]: {exc}",
                        exc,
                        module=__name__,
                    )
                    print(f"\n[错误] {exc}")
            else:
                print(f"\n无效选择: {choice}")

            input("\n按 Enter 继续...")
            self._clear()

        print("\n再见！\n")
        return 0

    # ------------------------------------------------------------------
    # 菜单
    # ------------------------------------------------------------------
    def _print_banner(self) -> None:
        print("=" * 52)
        print("   📚  HDU 图书馆座位预约系统")
        print("=" * 52)
        if self.auth.is_authenticated():
            print(f"   已登录: {self.auth.name} (UID: {self.auth.uid})")
        print(f"   当前方案数: {self.plans.count()} (启用: {self.plans.count_enabled()})")

    def _show_menu(self) -> None:
        print()
        print("─" * 40)
        print("  1. 📋 查看方案列表")
        print("  2. ➕ 创建预约方案")
        print("  3. 🕐 批量修改时间")
        print("  4. 🗑  删除方案")
        print("  5. 🚀 立即抢座")
        print("  6. ⏰ 定时预约")
        print("  7. 🔍 浏览房间与座位")
        print("  0. ❌ 退出")
        print("─" * 40)

    # ------------------------------------------------------------------
    # 0 — 认证
    # ------------------------------------------------------------------
    def _handle_auth(self) -> None:
        print("\n请先完成认证：")
        print("  [C] Cookie 字符串认证")
        print("  [P] 密码登录认证")
        choice = input("选择 [C/P]: ").strip().lower()

        if choice == "c":
            cookie = input("粘贴 Cookie 字符串: ").strip()
            self.auth.authenticate_with_cookie(cookie)
        elif choice == "p":
            print(
                "密码认证已停用。请使用 Cookie 认证 [C]。\n"
                "如需密码认证，请手动调用 core.password_auth 模块。"
            )
        else:
            print("无效选择，请重新运行并选择 [C]")

        if not self.auth.is_authenticated():
            print("认证失败，部分功能可能不可用")

    def _load_cache(self) -> None:
        print("\n正在加载房间信息...")
        try:
            self.cache = RoomCache(self.client, delay=0.5)
            rooms = self.cache.update_rooms()
            print(f"已加载 {len(rooms)} 个房间: {', '.join(rooms)}")
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.ROOM_QUERY,
                f"终端房间缓存加载失败: {exc}",
                exc,
                module=__name__,
            )
            print(f"房间信息加载失败: {exc}")

    # ------------------------------------------------------------------
    # 1 — 方案列表
    # ------------------------------------------------------------------
    def _handle_list_plans(self) -> None:
        plans = self.plans.list_all()
        if not plans:
            print("\n暂无预约方案，请先创建。")
            return

        self._print_plan_table(plans)

    def _print_plan_table(self, plans: list[BookingPlan]) -> None:
        print(
            f"\n{'#':<3} {'ID':<12} {'房间':<6} {'楼层':<6} {'座位':<6} "
            f"{'开始':<6} {'时长':<6} {'预约人':<8} {'状态':<6} {'星期':<6}"
        )
        print("-" * 75)
        for i, p in enumerate(plans, 1):
            wday = p.weekday.name if p.weekday else "-"
            begin = f"{p.start_hour:02d}:00"
            status = "✓" if p.status == PlanStatus.ENABLED else "✗"
            print(
                f"{i:<3} {p.plan_id or '-':<12} {p.room_type:<6} {p.floor_id:<6} "
                f"{p.seat_num:<6} {begin:<6} {p.duration_hours}h{'':<4} "
                f"{p.booker_name or '-':<8} {status:<6} {wday:<6}"
            )

    # ------------------------------------------------------------------
    # 2 — 创建方案 (交互式引导 FR-3.1)
    # ------------------------------------------------------------------
    def _handle_create_plan(self) -> None:
        print("\n══ 创建预约方案 ══\n")

        # Step 1: 房间类型
        room_types = self.client.get_room_types()
        print("可用房间类型:")
        for i, r in enumerate(room_types, 1):
            print(f"  {i}. {r['name']}")
        rt_idx = self._input_int(f"选择房间 [1-{len(room_types)}]", 1, len(room_types))
        selected_room = room_types[rt_idx - 1]

        # Step 2: 楼层 & 座位
        detail = self.client.get_room_detail(selected_room["query"])
        cat_id = detail["space_category"]["category_id"]
        con_id = detail["space_category"]["content_id"]

        begin = build_begin_time(13, 0)
        floors = self.client.get_seat_map(cat_id, con_id, begin, 1)

        print("\n可用楼层:")
        floor_list = []
        for f in floors:
            info = f.get("seatMap", {}).get("info", {})
            fid = info.get("id", "?")
            fname = f.get("roomName", "?")
            floor_list.append((fid, fname))
            seat_count = len(f.get("seatMap", {}).get("POIs", []))
            print(f"  ID {fid}: {fname} ({seat_count} 座)")

        floor_id = input("\n输入楼层 ID: ").strip()

        # Step 3: 座位号
        seat_num = input("输入座位号: ").strip()

        # Step 4: 时间
        start_hour = self._input_int("开始小时 (0-23)", 0, 23, default=13)
        duration_hours = self._input_int("使用时长 (小时)", 1, 15, default=9)
        book_days = self._input_int("天数偏移 (0=今天,1=明天)", 0, 7, default=1)

        # Step 5: 预约人
        booker = input(f"预约人 (默认: {self.auth.name}): ").strip()
        if not booker:
            booker = self.auth.name

        plan = BookingPlan(
            room_type=self._extract_room_type(selected_room["name"]),
            floor_id=int(floor_id),
            seat_num=seat_num,
            start_hour=start_hour,
            duration_hours=duration_hours,
            booker_name=booker,
            book_days=book_days,
        )

        errors = plan.validate()
        if errors:
            print("\n⚠ 方案校验失败:")
            for e in errors:
                print(f"  - {e}")
            if input("\n仍然保存? [y/N]: ").strip().lower() != "y":
                return

        self.plans.add(plan)
        print(f"\n✓ 方案已创建 (ID: {plan.plan_id})")

    # ------------------------------------------------------------------
    # 3 — 批量修改时间
    # ------------------------------------------------------------------
    def _handle_modify_time(self) -> None:
        plans = self.plans.list_all()
        if not plans:
            print("\n暂无方案。")
            return

        self._print_plan_table(plans)
        sel = input("\n输入要修改的方案序号（多个用逗号分隔，all=全部）: ").strip()

        if sel.lower() == "all":
            ids = [p.plan_id for p in plans if p.plan_id is not None]
        else:
            try:
                indices = [int(x.strip()) - 1 for x in sel.split(",")]
                _mod_ids: list[str] = []
                for i in indices:
                    if 0 <= i < len(plans):
                        pid = plans[i].plan_id
                        if pid is not None:
                            _mod_ids.append(pid)
                ids = _mod_ids
            except (ValueError, IndexError):
                print("输入无效")
                return

        if not ids:
            print("未选中任何方案")
            return

        print("\n输入新值（留空保持原值）:")
        sh = input("  开始小时 (0-23): ").strip()
        dh = input("  使用时长 (小时): ").strip()
        bd = input("  天数偏移: ").strip()

        kwargs = {}
        if sh:
            kwargs["start_hour"] = int(sh)
        if dh:
            kwargs["duration_hours"] = int(dh)
        if bd:
            kwargs["book_days"] = int(bd)

        if kwargs:
            modified = self.plans.batch_set_time(ids, **kwargs)
            print(f"✓ 已修改 {modified} 个方案")
        else:
            print("未做任何修改")

    # ------------------------------------------------------------------
    # 4 — 删除方案
    # ------------------------------------------------------------------
    def _handle_delete_plan(self) -> None:
        plans = self.plans.list_all()
        if not plans:
            print("\n暂无方案。")
            return

        self._print_plan_table(plans)
        sel = input("\n输入要删除的方案序号（多个用逗号分隔）: ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in sel.split(",")]
            _del_ids: list[str] = []
            for i in indices:
                if 0 <= i < len(plans):
                    pid = plans[i].plan_id
                    if pid is not None:
                        _del_ids.append(pid)
            ids = _del_ids
        except (ValueError, IndexError):
            print("输入无效")
            return

        if ids:
            count = self.plans.remove_many(ids)
            print(f"✓ 已删除 {count} 个方案")
        else:
            print("未选中任何方案")

    # ------------------------------------------------------------------
    # 5 — 立即抢座
    # ------------------------------------------------------------------
    def _handle_book_now(self) -> None:
        plans = self.plans.list_enabled()
        if not plans:
            print("\n没有启用的方案。")
            return

        self._print_plan_table(plans)
        print(f"\n将对 {len(plans)} 个方案依次尝试预约")
        if input("确认开始? [Y/n]: ").strip().lower() == "n":
            return

        strategy = FixedSeatStrategy()
        notifier = ConsoleNotification(use_colors=True)
        orchestrator = BookingOrchestrator(
            self.client,
            strategy,
            notifier,
        )

        print("\n开始预约...")
        self.cancel_flag = False

        def on_progress(result: BookingResult):
            icon = "✓" if result.success else "✗"
            print(f"  {icon} [{result.plan.to_plan_code()}] {result.message}")

        results = orchestrator.book_all(plans, on_progress=on_progress)

        # 汇总
        succeeded = [r for r in results if r.success]
        if succeeded:
            print(f"\n✓ 预约成功！共尝试 {len(results)} 次")
        else:
            print(f"\n✗ 预约失败。共尝试 {len(results)} 次")

    # ------------------------------------------------------------------
    # 6 — 定时预约
    # ------------------------------------------------------------------
    def _handle_book_scheduled(self) -> None:
        plans = self.plans.list_enabled()
        if not plans:
            print("\n没有启用的方案。")
            return

        self._print_plan_table(plans)
        time_str = input("\n目标执行时间 (HH:MM 或 HH:MM:SS): ").strip()
        try:
            execute_at = build_execute_datetime(time_str)
        except ValueError as exc:
            print(f"时间格式错误: {exc}")
            return

        if execute_at is None:
            print("请输入有效时间")
            return

        print(f"\n将在 {execute_at.strftime('%Y-%m-%d %H:%M:%S')} 开始执行")
        if input("确认? [Y/n]: ").strip().lower() == "n":
            return

        strategy = FixedSeatStrategy()
        notifier = ConsoleNotification(use_colors=True)
        orchestrator = BookingOrchestrator(
            self.client,
            strategy,
            notifier,
        )
        self.cancel_flag = False

        print("\n等待中... (按 Ctrl+C 取消)\n")

        def on_countdown(remaining: int):
            sys.stdout.write(f"\r⏳ 倒计时: {format_countdown(remaining)}  ")
            sys.stdout.flush()

        def on_progress(result: BookingResult):
            icon = "✓" if result.success else "✗"
            print(f"\n  {icon} [{result.plan.to_plan_code()}] {result.message}")

        try:
            results = orchestrator.book_at(
                plans,
                execute_at,
                on_countdown=on_countdown,
                on_progress=on_progress,
            )
            sys.stdout.write("\n")
            succeeded = [r for r in results if r.success]
            if succeeded:
                print("✓ 定时预约成功！")
            else:
                print("✗ 定时预约失败")
        except KeyboardInterrupt:
            print("\n\n定时预约已取消")

    # ------------------------------------------------------------------
    # 7 — 浏览房间与座位
    # ------------------------------------------------------------------
    def _handle_browse_rooms(self) -> None:
        if self.cache is None or self.cache.rooms is None:
            print("\n房间缓存为空，正在加载...")
            self._load_cache()

        if self.cache is None or self.cache.rooms is None:
            print("房间信息不可用")
            return

        rooms = self.cache.rooms
        print("\n══ 房间与座位浏览 ══\n")
        for room_name, detail in rooms.items():
            floors = detail.get("floors", {})
            print(f"📁 {room_name}")
            for floor_name, floor_data in floors.items():
                seats = floor_data.get("seats", [])
                seat_nums = sorted(s.get("title", "") for s in seats if s.get("title"))
                preview = ", ".join(seat_nums[:10])
                if len(seat_nums) > 10:
                    preview += f" ... (+{len(seat_nums) - 10})"
                print(f"   ├─ {floor_name}: [{preview}]")
            print()

    # ------------------------------------------------------------------
    # 0 — 退出
    # ------------------------------------------------------------------
    def _handle_exit(self):
        self.cancel_flag = True
        return False

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _clear() -> None:
        subprocess.run(
            ["cmd", "/c", "cls"] if os.name == "nt" else ["clear"],
            check=False,
            shell=False,
        )

    @staticmethod
    def _input_int(prompt: str, lo: int, hi: int, default: int | None = None) -> int:
        default_hint = f" [{default}]" if default is not None else ""
        while True:
            val = input(f"{prompt}{default_hint}: ").strip()
            if not val and default is not None:
                return default
            try:
                n = int(val)
                if lo <= n <= hi:
                    return n
                print(f"  请输入 {lo}-{hi} 之间的数字")
            except ValueError:
                print("  请输入有效数字")

    @staticmethod
    def _extract_room_type(name: str) -> int:
        """从房间名中提取房间类型编号。"""
        for num, label in {"1": "自习", "2": "教师", "3": "阅览", "4": "讨论"}.items():
            if label in name:
                return int(num)
        return 1  # 默认自习室
