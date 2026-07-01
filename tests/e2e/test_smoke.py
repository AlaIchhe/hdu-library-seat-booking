"""
冒烟测试 (Smoke Tests) — 使用真实凭据验证端到端核心流程。

冒烟测试覆盖图书馆预约系统的关键用户路径：
  1. 登录认证（Cookie 验证 + 密码登录 fallback）
  2. 房间类型查询
  3. 房间详情获取
  4. 座位地图查询
  5. 座位定位
  6. 预约方案创建 & 校验
  7. 预约预览（dry-run）
  8. 预约编排器全流程（dry-run）
  9. 房间缓存完整刷新
  10. Api-Token 签名一致性

运行方式：
  # 仅冒烟测试
  pytest tests/test_smoke.py -v -m smoke

  # 冒烟测试 + 详细输出
  pytest tests/test_smoke.py -v -m smoke -s

  # 跳过慢速测试
  pytest tests/test_smoke.py -v -m "smoke and not slow"

凭据来源：
  - Cookie 文件 (tests/cookies.json)
  - 环境变量 HDU_COOKIE

注意：密码认证已移至 hdu_library_booking.api.password_auth 模块，不纳入主流程。
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import dotenv
import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 加载项目根目录的 .env（不覆盖已有环境变量）
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

from hdu_library_booking.api import HduLibraryClient, RoomCache
from hdu_library_booking.auth import generate_api_token
from hdu_library_booking.models.plan import BookingPlan, PlanStatus, Weekday
from hdu_library_booking.services.auth import AuthService
from hdu_library_booking.services.booking import BookingOrchestrator, default_retry_decider
from hdu_library_booking.services.notifications import ConsoleNotification
from hdu_library_booking.services.plan import PlanService
from hdu_library_booking.services.yaml_plan import YamlPlanRepository
from hdu_library_booking.strategies.fixed import FixedSeatStrategy

# ============================================================================
# 凭据
# ============================================================================


# ============================================================================
# markers
# ============================================================================
pytestmark = [pytest.mark.smoke, pytest.mark.slow]


# ============================================================================
# Fixtures
# ============================================================================
@pytest.fixture(scope="module")
def client():
    """未认证的客户端。"""
    return HduLibraryClient(timeout=30)


@pytest.fixture(scope="module")
def authed_client(client):
    """已登录认证的客户端（仅 Cookie 认证，密码认证已分离）。

    认证策略（按优先级）：
      1. Cookie 文件 — 加载后发起真实 API 请求验证有效性
      2. 环境变量中的 Cookie 字符串 — 同样验证有效性

    注意：密码认证已移至 core.password_auth 模块，不在此流程中。
    """
    cookie_file = os.environ.get(
        "HDU_COOKIE_FILE",
        str(Path(__file__).resolve().parent.parent.parent / "tests" / "cookies.json"),
    )

    # 策略 1: 从 Cookie 文件加载 + 验证
    if Path(cookie_file).exists():
        try:
            client.set_cookies_from_json_file(cookie_file)
            client.resolve_uid()
            # 关键：验证 Cookie 是否真正有效（发起真实 API 请求）
            if client.uid and client.validate_cookie():
                return client
            # Cookie 已过期，继续下一策略
        except Exception:
            pass  # Cookie 加载失败，尝试下一策略

    # 策略 2: 环境变量中的 Cookie 字符串 + 验证
    cookie_str = os.environ.get("HDU_COOKIE")
    if cookie_str:
        try:
            client.set_cookie_header(cookie_str)
            client.resolve_uid()
            if client.uid and client.validate_cookie():
                return client
        except Exception:
            pass

    # 所有策略均失败
    missing = []
    if not Path(cookie_file).exists():
        missing.append(f"Cookie 文件不存在: {cookie_file}")
    if not cookie_str:
        missing.append("未设置 HDU_COOKIE 环境变量")

    pytest.fail(
        "所有 Cookie 认证方式均失败。\n"
        + "\n".join(f"  - {m}" for m in missing)
        + "\n请:\n"
        + "  1) 在浏览器中登录 https://hdu.huitu.zhishulib.com\n"
        + "  2) 导出 Cookies 为 JSON 保存到 "
        + cookie_file
        + "\n"
        + "  3) 或设置环境变量 HDU_COOKIE=uid=xxx;auth=yyy"
    )


# ============================================================================
# 冒烟测试 1: 登录认证 — 每条路径独立测试
# ============================================================================


class TestSmokeAuthCookieFile:
    """Cookie 文件认证。"""

    def test_cookie_file_loads_and_validates(self):
        """Cookie 文件存在时，应加载并通过真实 API 验证。"""
        cookie_file = Path(__file__).parent / "cookies.json"
        if not cookie_file.exists():
            pytest.skip(f"Cookie 文件不存在: {cookie_file}")

        client = HduLibraryClient(timeout=30)
        client.set_cookies_from_json_file(str(cookie_file))
        client.resolve_uid()
        assert client.uid, "Cookie 加载后 UID 不应为空"
        # 关键：发起真实 API 请求验证 Cookie 未过期
        assert client.validate_cookie(), "Cookie 已过期或无效（API 验证失败）"

    def test_invalid_cookie_file_raises(self):
        """不存在的 Cookie 文件应抛出 CookieError。"""
        from hdu_library_booking.exceptions import CookieError

        client = HduLibraryClient(timeout=30)
        auth = AuthService(client)
        # 不存在的文件应抛出 CookieError
        with pytest.raises(CookieError):
            auth.authenticate_with_cookie_file("/nonexistent/cookies.json")


class TestSmokeAuthCookieString:
    """环境变量 Cookie 字符串认证。"""

    def test_cookie_string_authenticates(self):
        """HDU_COOKIE 环境变量非空时应能认证。"""
        cookie_str = os.environ.get("HDU_COOKIE", "")
        if not cookie_str:
            pytest.skip("未设置 HDU_COOKIE 环境变量")

        client = HduLibraryClient(timeout=30)
        auth = AuthService(client)
        ok = auth.authenticate_with_cookie(cookie_str)
        assert ok, "Cookie 字符串认证应成功"
        assert client.uid, "认证后 UID 不应为空"

    def test_empty_cookie_string_raises(self):
        """空 Cookie 字符串应抛出 CookieError。"""
        from hdu_library_booking.exceptions import CookieError

        client = HduLibraryClient(timeout=30)
        auth = AuthService(client)
        with pytest.raises(CookieError):
            auth.authenticate_with_cookie("   ")


class TestSmokeAuthIntegration:
    """认证后状态一致性。"""

    def test_uid_resolved_after_login(self, authed_client):
        """登录后 UID 应被正确解析。"""
        assert authed_client.uid, "UID 不应为空"

    def test_name_available_after_login(self, authed_client):
        """登录后姓名应可用（若 API 返回的话）。"""
        if not authed_client.name:
            pytest.skip("API 响应中未包含用户名（新版 UI 格式）")

    def test_auth_service_integration(self, authed_client):
        """AuthService 封装层应正确反映认证状态。"""
        auth = AuthService(authed_client)
        assert auth.is_authenticated()
        assert auth.uid == authed_client.uid
        assert auth.name == authed_client.name


# ============================================================================
# 冒烟测试 2: 房间查询
# ============================================================================
class TestSmokeRoomQuery:
    """房间查询流程冒烟。"""

    def test_get_room_types_returns_data(self, authed_client):
        """查询房间类型应返回非空列表。"""
        rooms = authed_client.get_room_types()
        assert len(rooms) > 0, "应至少有一个房间"
        for r in rooms:
            assert r["name"], "房间名不应为空"
            assert r["query"], "query 不应为空"

    def test_get_room_detail_for_all_rooms(self, authed_client):
        """每个房间类型都应能获取详情。"""
        rooms = authed_client.get_room_types()
        for r in rooms:
            detail = authed_client.get_room_detail(r["query"])
            assert "space_category" in detail, f"{r['name']} 缺少 space_category"
            sc = detail["space_category"]
            assert sc.get("category_id"), f"{r['name']} 缺少 category_id"
            assert sc.get("content_id"), f"{r['name']} 缺少 content_id"


# ============================================================================
# 冒烟测试 3: 座位查询与定位
# ============================================================================
@pytest.fixture(scope="module")
def first_room_floors(authed_client):
    """模块级 fixture：获取第一个房间的楼层座位数据，供所有冒烟测试类共享。"""
    rooms = authed_client.get_room_types()
    detail = authed_client.get_room_detail(rooms[0]["query"])
    sc = detail["space_category"]
    return authed_client.get_seat_map(
        str(sc["category_id"]),
        str(sc["content_id"]),
        datetime.now(),
        1,
    )


class TestSmokeSeatQuery:
    """座位地图查询 & 座位定位冒烟。"""

    def test_seat_map_has_floors(self, first_room_floors):
        """座位地图应有至少一个楼层。"""
        assert len(first_room_floors) > 0

    def test_each_floor_has_seats(self, first_room_floors):
        """每个楼层应包含座位 POI 列表。"""
        for floor in first_room_floors:
            pois = floor.get("seatMap", {}).get("POIs", [])
            assert len(pois) > 0, f"{floor.get('roomName')} 应有座位"

    def test_find_seat_in_floors(self, authed_client, first_room_floors):
        """应能在楼层中精准定位座位。"""
        # 取第一个楼层和第一个座位
        first_floor = first_room_floors[0]
        floor_id = str(first_floor["seatMap"]["info"]["id"])
        first_seat = first_floor["seatMap"]["POIs"][0]
        seat_num = str(first_seat["title"])

        found_floor, found_seat = authed_client.find_seat_in_floors(
            first_room_floors, floor_id, seat_num
        )
        assert found_floor is not None
        assert found_seat is not None
        assert found_seat.get("id") == first_seat.get("id")

    def test_find_seat_invalid_floor(self, authed_client, first_room_floors):
        """查询不存在的楼层应抛出 SeatQueryError。"""
        from hdu_library_booking.exceptions import SeatQueryError

        with pytest.raises(SeatQueryError, match="找不到楼层"):
            authed_client.find_seat_in_floors(first_room_floors, "99999", "001")

    def test_find_seat_invalid_seat(self, authed_client, first_room_floors):
        """查询不存在的座位应抛出 SeatQueryError。"""
        from hdu_library_booking.exceptions import SeatQueryError

        first_floor = first_room_floors[0]
        floor_id = str(first_floor["seatMap"]["info"]["id"])
        with pytest.raises(SeatQueryError, match="找不到"):
            authed_client.find_seat_in_floors(first_room_floors, floor_id, "99999")


# ============================================================================
# 冒烟测试 4: 预约方案模型
# ============================================================================
class TestSmokeBookingPlan:
    """BookingPlan 模型冒烟。"""

    def test_create_valid_plan(self, authed_client, first_room_floors):
        """创建一个有效的预约方案应通过校验。"""
        # 重新获取数据
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        sc = detail["space_category"]
        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )

        first_floor = floors[0]
        floor_id = int(first_floor["seatMap"]["info"]["id"])
        first_seat = str(first_floor["seatMap"]["POIs"][0]["title"])

        plan = BookingPlan(
            room_type=1,
            floor_id=floor_id,
            seat_num=first_seat,
            start_hour=13,
            duration_hours=9,
            booker_name=authed_client.name,
            book_days=1,
            weekday=Weekday.MONDAY,
            tags=["冒烟测试"],
        )

        errors = plan.validate()
        assert errors == [], f"方案校验应通过，实际错误: {errors}"

    def test_plan_serialization_roundtrip(self):
        """方案序列化/反序列化往返。"""
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            booker_name="测试",
            book_days=1,
            status=PlanStatus.ENABLED,
            weekday=Weekday.FRIDAY,
            tags=["smoke"],
        )
        d = plan.to_dict()
        restored = BookingPlan.from_dict(d)
        assert restored.room_type == plan.room_type
        assert restored.weekday == plan.weekday
        assert restored.validate() == []

    def test_plan_code_encoding(self):
        """方案编码往返测试。"""
        code = "1:1558:296:13:9"
        plan = BookingPlan.from_plan_code(code)
        assert plan.to_plan_code() == code


# ============================================================================
# 冒烟测试 5: 预约预览（Dry-Run）
# ============================================================================
class TestSmokeBookingDryRun:
    """预约预览（dry-run）—— 不实际提交预约。"""

    def test_dry_run_produces_valid_payload(self, authed_client):
        """dry_run 应生成有效的签名 payload。"""
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        sc = detail["space_category"]
        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )

        first_seat = floors[0]["seatMap"]["POIs"][0]
        seat_id = str(first_seat.get("id"))

        begin = datetime.now() + timedelta(days=1)
        begin = begin.replace(hour=13, minute=0, second=0, microsecond=0)

        result = authed_client.book_seat(
            seat_id=seat_id,
            uid=authed_client.uid,
            begin_time=begin,
            duration_hours=1,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert "api_token" in result
        assert "payload" in result

        payload = result["payload"]
        # 校验必要字段
        required = [
            "beginTime",
            "duration",
            "is_recommend",
            "api_time",
            "seats[0]",
            "seatBookers[0]",
        ]
        for field in required:
            assert field in payload, f"payload 缺少 {field}"

    def test_orchestrator_dry_run(self, authed_client):
        """BookingOrchestrator 在 dry_run 模式下应返回预览结果。"""
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        sc = detail["space_category"]
        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )

        first_floor = floors[0]
        floor_id = int(first_floor["seatMap"]["info"]["id"])
        first_seat = str(first_floor["seatMap"]["POIs"][0]["title"])

        plan = BookingPlan(
            room_type=1,
            floor_id=floor_id,
            seat_num=first_seat,
            start_hour=13,
            duration_hours=1,
            book_days=1,
        )

        strategy = FixedSeatStrategy()
        notifier = ConsoleNotification(use_colors=False)
        orchestrator = BookingOrchestrator(
            authed_client,
            strategy,
            notifier,
        )
        orchestrator.dry_run = True

        result = orchestrator.book_single(plan)
        assert result.success is True
        assert "预览模式" in result.message


# ============================================================================
# 冒烟测试 6: 房间缓存完整刷新
# ============================================================================
class TestSmokeRoomCache:
    """RoomCache 完整刷新冒烟。"""

    def test_full_cache_refresh(self, authed_client):
        """update_rooms() 应完成房间+座位完整刷新。"""
        cache = RoomCache(authed_client, delay=0.5)
        room_names = cache.update_rooms()

        assert len(room_names) > 0, "应有至少一个房间"
        assert cache.rooms is not None

        # 至少有一个房间包含楼层和座位
        rooms_with_floors = 0
        for name in room_names:
            assert "floors" in cache.rooms[name], f"{name} 缺少 floors"
            floors = cache.rooms[name]["floors"]
            if len(floors) > 0:
                rooms_with_floors += 1
                for fname, fdata in floors.items():
                    assert "seats" in fdata, f"{name}/{fname} 缺少 seats"
                    assert len(fdata["seats"]) > 0, f"{name}/{fname} 应有座位"

        assert rooms_with_floors > 0, f"至少一个房间应有楼层，现有房间: {room_names}"

    def test_get_floor_names_and_seats(self, authed_client):
        """get_floor_names 和 get_seats 应返回正确数据。"""
        cache = RoomCache(authed_client, delay=0.5)
        cache.update_rooms()
        room_names = list(cache.rooms.keys())

        # 找一个有楼层的房间测试
        found = False
        for name in room_names:
            floor_names = cache.get_floor_names(name)
            if len(floor_names) > 0:
                found = True
                for fn in floor_names:
                    seats = cache.get_seats(name, fn)
                    assert len(seats) > 0
                    assert "title" in seats[0]
                break

        assert found, f"未找到有楼层的房间，现有: {room_names}"


# ============================================================================
# 冒烟测试 7: Api-Token 签名
# ============================================================================
class TestSmokeApiToken:
    """Api-Token 签名生成冒烟。"""

    def test_token_generation(self, authed_client):
        """生成的 token 应为 base64 编码字符串。"""
        import base64

        token, _api_time = generate_api_token(
            seat_id="296",
            uid=authed_client.uid,
            begin_time=int(datetime.now().timestamp()),
            duration=3600,
        )
        assert len(token) > 0
        # 应可被 base64 解码
        decoded = base64.b64decode(token.encode()).decode()
        assert len(decoded) == 32  # MD5 hex

    def test_token_deterministic(self, authed_client):
        """相同参数生成相同 token。"""
        params = {
            "seat_id": "296",
            "uid": authed_client.uid,
            "begin_time": 1700000000,
            "duration": 3600,
            "api_time": 1700000000,
        }
        t1, _ = generate_api_token(**params)
        t2, _ = generate_api_token(**params)
        assert t1 == t2


# ============================================================================
# 冒烟测试 8: 预约编排器完整流程（dry-run）
# ============================================================================
class TestSmokeOrchestratorEndToEnd:
    """BookingOrchestrator 端到端冒烟。"""

    def test_orchestrator_full_flow_dry_run(self, authed_client):
        """预约编排器完整流程（dry-run 模式）应成功。"""
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        sc = detail["space_category"]
        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )

        first_floor = floors[0]
        floor_id = int(first_floor["seatMap"]["info"]["id"])
        first_seat = str(first_floor["seatMap"]["POIs"][0]["title"])

        # 构建方案
        plan = BookingPlan(
            room_type=1,
            floor_id=floor_id,
            seat_num=first_seat,
            start_hour=13,
            duration_hours=1,
            book_days=1,
        )

        strategy = FixedSeatStrategy()
        notifier = ConsoleNotification(use_colors=False)
        orchestrator = BookingOrchestrator(
            authed_client,
            strategy,
            notifier,
            retry_decider=default_retry_decider,
        )
        orchestrator.dry_run = True
        orchestrator.max_trials = 1

        result = orchestrator.book_single(plan)
        assert result.success is True, f"dry-run 应成功: {result.message}"
        assert "预览模式" in result.message

    def test_multiple_plans_batch_dry_run(self, authed_client):
        """批量方案 dry-run 应在首个方案成功后停止。"""
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        sc = detail["space_category"]
        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )

        first_floor = floors[0]
        floor_id = int(first_floor["seatMap"]["info"]["id"])
        all_seats = first_floor["seatMap"]["POIs"]

        plans = []
        for _i, seat in enumerate(all_seats[:2]):  # 最多 2 个方案
            plans.append(
                BookingPlan(
                    room_type=1,
                    floor_id=floor_id,
                    seat_num=str(seat["title"]),
                    start_hour=13,
                    duration_hours=1,
                    book_days=1,
                )
            )

        strategy = FixedSeatStrategy()
        notifier = ConsoleNotification(use_colors=False)
        orchestrator = BookingOrchestrator(
            authed_client,
            strategy,
            notifier,
        )
        orchestrator.dry_run = True
        orchestrator.max_trials = 1

        results = orchestrator.book_all(plans)
        assert len(results) >= 1
        assert all(r.success for r in results)


# ============================================================================
# 冒烟测试 9: 方案持久化
# ============================================================================
class TestSmokePlanPersistence:
    """方案仓库 YAML 持久化冒烟。"""

    def test_plan_repository_crud(self, tmp_path):
        """完整的 CRUD 生命周期测试。"""
        repo = YamlPlanRepository(str(tmp_path / "smoke_plans.yaml"))

        # Create
        plan = BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            booker_name="冒烟测试",
            book_days=1,
        )
        repo.add(plan)
        assert plan.plan_id is not None

        # Read
        loaded = repo.load_all()
        assert len(loaded) == 1
        assert loaded[0].plan_id == plan.plan_id

        # Read by ID
        fetched = repo.get(plan.plan_id)
        assert fetched is not None

        # Delete
        assert repo.remove(plan.plan_id) is True
        assert repo.load_all() == []

    def test_plan_service_integration(self, tmp_path):
        """PlanService + Repository 集成测试。"""
        repo = YamlPlanRepository(str(tmp_path / "service_plans.yaml"))
        service = PlanService(repo)

        plan = BookingPlan(
            room_type=2,
            floor_id=1000,
            seat_num="050",
            start_hour=8,
            duration_hours=4,
        )
        service.add(plan)
        assert service.count() == 1
        assert service.count_enabled() == 1

        # 按星期筛选
        monday_plans = service.list_by_weekday(Weekday.MONDAY)
        # 通用方案（weekday=None）应被返回
        assert len(monday_plans) >= 1

        # 禁用
        service.disable_all()
        assert service.count_enabled() == 0

        # 启用
        service.enable_all()
        assert service.count_enabled() == 1


# ============================================================================
# 冒烟测试 10: 重试决策
# ============================================================================
class TestSmokeRetryDecision:
    """智能重试决策冒烟。"""

    def test_retry_decision_seat_unavailable(self):
        """座位不可用时返回 SKIP。"""
        decision = default_retry_decider(
            {"MESSAGE": "选择的座位无法预约，可能座位不可用或已经被其他人锁定或占用，请换一个再试"}
        )
        assert decision.action == "skip"

    def test_retry_decision_time_out_of_range(self):
        """超出时间范围时返回 CONTINUE。"""
        decision = default_retry_decider({"MESSAGE": "超出可预约座位时间范围"})
        assert decision.action == "continue"

    def test_retry_decision_duplicate(self):
        """重复预约时返回 SKIP。"""
        decision = default_retry_decider({"MESSAGE": "已有预约，请勿重复预约！"})
        assert decision.action == "skip"

    def test_retry_decision_invalid_request(self):
        """非法请求时返回 STOP。"""
        decision = default_retry_decider({"MESSAGE": "非法请求"})
        assert decision.action == "stop"
