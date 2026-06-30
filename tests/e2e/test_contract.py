"""
契约测试 (Contract Tests) — 验证慧图图书馆 API 响应结构与字段类型。

这些测试发送真实 HTTP 请求并校验返回的 JSON 结构，
一旦 API 契约发生变化（字段改名、类型变更、端点移位），
测试会立即失败，提示需要更新客户端代码。

运行方式：
  pytest tests/test_contract.py -v -m contract
  pytest tests/test_contract.py -v -m "contract and not slow"

凭据通过环境变量覆盖（优先于默认值）：
  HDU_USERNAME   — 学号/登录名
  HDU_PASSWORD   — 密码
  HDU_ORG_ID     — 机构 ID
"""

import os

import pytest

from core import HduLibraryClient, HduLibraryError
from core import constants as C


# ============================================================================
# 凭据 — 环境变量 > 默认值
# ============================================================================
def _credentials():
    return {
        "username": os.environ.get("HDU_USERNAME", "23320116"),
        "password": os.environ.get("HDU_PASSWORD", "Zhuhe@0618"),
        "org_id": os.environ.get("HDU_ORG_ID", C.DEFAULT_ORG_ID),
    }


# ============================================================================
# pytest markers
# ============================================================================
pytestmark = [pytest.mark.contract, pytest.mark.slow]


# ============================================================================
# Fixture — 已认证的客户端（模块级别复用）
# ============================================================================
@pytest.fixture(scope="module")
def authed_client():
    """登录并返回已认证的 HduLibraryClient 实例。

    优先使用 Cookie 文件认证（避免 SSO CSRF 问题）。
    """
    from pathlib import Path

    client = HduLibraryClient(timeout=30)
    cookie_file = os.environ.get(
        "HDU_COOKIE_FILE",
        str(Path(__file__).parent / "cookies.json"),
    )

    # 策略 1: Cookie 文件
    if Path(cookie_file).exists():
        try:
            client.set_cookies_from_json_file(cookie_file)
            client.resolve_uid()
            if client.uid:
                return client
        except Exception:
            pass

    # 策略 2: Cookie 环境变量
    cookie_str = os.environ.get("HDU_COOKIE")
    if cookie_str:
        try:
            client.set_cookie_header(cookie_str)
            client.resolve_uid()
            if client.uid:
                return client
        except Exception:
            pass

    pytest.skip(
        f"SSO 认证需要 Cookie 文件。\n"
        f"请在浏览器中登录 https://hdu.huitu.zhishulib.com\n"
        f"导出 Cookie 保存到: {cookie_file}\n"
        f"或设置环境变量 HDU_COOKIE"
    )


# ============================================================================
# 契约：登录 API
# ============================================================================
class TestLoginContract:
    """POST /User/Index/login 响应契约。"""

    def test_login_response_structure(self):
        """登录成功后响应必须包含 CODE, DATA, uid, user_info。"""
        creds = _credentials()
        client = HduLibraryClient(timeout=30)
        resp = client._request(
            "POST",
            client.urls["login"],
            {
                "login_name": creds["username"],
                "password": creds["password"],
                "org_id": creds["org_id"],
            },
        )

        # 顶层契约
        assert "CODE" in resp, "缺少 CODE 字段"
        assert isinstance(resp["CODE"], str), "CODE 应为字符串"

        if resp["CODE"] == "ok":
            assert "DATA" in resp, "成功时缺少 DATA 字段"
            data = resp["DATA"]
            assert "uid" in data, "DATA 中缺少 uid"
            assert isinstance(data["uid"], int | str), "uid 应为 int 或 str"
            assert "user_info" in data or "name" in data, "DATA 中缺少 user_info 或 name"

    def test_login_bad_password_contract(self):
        """错误密码的响应契约：CODE != ok, 有 MESSAGE。"""
        client = HduLibraryClient(timeout=30)
        resp = client._request(
            "POST",
            client.urls["login"],
            {
                "login_name": _credentials()["username"],
                "password": "wrong_password_12345678",
                "org_id": _credentials()["org_id"],
            },
        )

        assert "CODE" in resp
        assert resp["CODE"] != "ok", "错误密码不应返回 ok"
        # 错误时应有一些提示信息
        has_message = "MESSAGE" in resp or (
            "DATA" in resp and isinstance(resp["DATA"], dict) and "msg" in resp["DATA"]
        )
        assert has_message, "错误响应应包含 MESSAGE 或 DATA.msg"


# ============================================================================
# 契约：房间查询 API
# ============================================================================
class TestRoomQueryContract:
    """GET /Space/Category/list 响应契约。"""

    def test_room_list_structure(self, authed_client):
        """房间列表必须包含 name, query 字段。"""
        rooms = authed_client.get_room_types()
        assert isinstance(rooms, list), "房间列表应为 list"
        assert len(rooms) > 0, "房间列表不应为空"

        for room in rooms:
            assert "name" in room, f"房间缺少 name: {room}"
            assert "query" in room, f"房间缺少 query: {room}"
            assert isinstance(room["name"], str)
            assert isinstance(room["query"], str)
            assert "space_category" in room["query"], (
                f"query 应包含 space_category 参数: {room['query']}"
            )

    def test_known_room_types_present(self, authed_client):
        """应包含自习室、阅览室等已知房间类型。"""
        rooms = authed_client.get_room_types()
        names = [r["name"] for r in rooms]
        known = ["自习室", "阅览室", "讨论室", "教师休息室"]
        found = [k for k in known if any(k in n for n in names)]
        assert len(found) >= 1, f"未找到任何已知房间类型，现有: {names}"


# ============================================================================
# 契约：房间详情 & 座位地图 API
# ============================================================================
class TestSeatMapContract:
    """GET/POST /Seat/Index/searchSeats 响应契约。"""

    @pytest.fixture(scope="module")
    def first_room_detail(self, authed_client):
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        return detail

    def test_room_detail_structure(self, first_room_detail):
        """房间详情必须包含 space_category。"""
        assert "space_category" in first_room_detail, "缺少 space_category 字段"
        sc = first_room_detail["space_category"]
        assert "category_id" in sc, "缺少 category_id"
        assert "content_id" in sc, "缺少 content_id"
        assert isinstance(sc["category_id"], int | str)
        assert isinstance(sc["content_id"], int | str)

    def test_seat_map_structure(self, authed_client, first_room_detail):
        """座位地图响应必须包含楼层 seats 数据结构。"""
        from datetime import datetime

        sc = first_room_detail["space_category"]
        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )

        assert isinstance(floors, list), "楼层应为 list"
        assert len(floors) > 0, "楼层列表不应为空"

        for floor in floors:
            assert "roomName" in floor, "楼层缺少 roomName"
            assert "seatMap" in floor, "楼层缺少 seatMap"
            sm = floor["seatMap"]
            assert "info" in sm, "seatMap 缺少 info"
            assert "POIs" in sm, "seatMap 缺少 POIs"
            assert isinstance(sm["POIs"], list), "POIs 应为 list"

            info = sm["info"]
            assert "id" in info, "seatMap.info 缺少 id (楼层ID)"

            for poi in sm["POIs"]:
                assert "title" in poi, "座位 POI 缺少 title (座位号)"
                assert "id" in poi, "座位 POI 缺少 id"


# ============================================================================
# 契约：预约 API
# ============================================================================
class TestBookingContract:
    """POST /Seat/Index/bookSeats 响应契约（dry-run/失败场景）。"""

    @pytest.fixture(scope="module")
    def seat_info(self, authed_client):
        """获取一个真实座位用于预约测试。"""
        rooms = authed_client.get_room_types()
        detail = authed_client.get_room_detail(rooms[0]["query"])
        sc = detail["space_category"]
        from datetime import datetime

        floors = authed_client.get_seat_map(
            str(sc["category_id"]),
            str(sc["content_id"]),
            datetime.now(),
            1,
        )
        # 提取第一个座位
        first_poi = floors[0]["seatMap"]["POIs"][0]
        return {
            "seat_id": str(first_poi.get("id")),
            "seat_num": str(first_poi.get("title")),
            "floor_id": str(floors[0]["seatMap"]["info"]["id"]),
            "floor_name": floors[0].get("roomName", ""),
        }

    def test_dry_run_response_structure(self, authed_client, seat_info):
        """dry_run 模式下返回签名后的 payload 结构。"""
        from datetime import datetime

        result = authed_client.book_seat(
            seat_id=seat_info["seat_id"],
            uid=authed_client.uid,
            begin_time=datetime.now(),
            duration_hours=1,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert "payload" in result
        assert "api_token" in result
        payload = result["payload"]
        assert "beginTime" in payload
        assert "duration" in payload
        assert "seats[0]" in payload
        assert "seatBookers[0]" in payload
        assert isinstance(payload["api_time"], int)

    def test_booking_response_structure(self, authed_client, seat_info):
        """实际预约请求的响应契约（即使被拒绝也要验证结构）。"""
        from datetime import datetime, timedelta

        # 使用明天的同一时间，大概率不在预约窗口内
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=13, minute=0, second=0, microsecond=0)

        try:
            result = authed_client.book_seat(
                seat_id=seat_info["seat_id"],
                uid=authed_client.uid,
                begin_time=tomorrow,
                duration_hours=1,
            )
        except HduLibraryError:
            pytest.skip("网络错误，跳过契约校验")

        # 响应结构契约（无论成功或失败）
        assert isinstance(result, dict), "预约响应应为 dict"
        assert "CODE" in result, "缺少 CODE"
        assert isinstance(result["CODE"], str), "CODE 应为字符串"

        if "MESSAGE" in result:
            assert isinstance(result["MESSAGE"], str)
        if "DATA" in result:
            assert isinstance(result["DATA"], dict)


# ============================================================================
# 契约：用户信息 API
# ============================================================================
class TestUserInfoContract:
    """用户中心 API 响应契约。"""

    def test_user_base_info_structure(self, authed_client):
        """GET /User/Center/baseInfo 响应应为字典。"""
        try:
            data = authed_client._request("GET", authed_client.urls["user_base_info"])
        except HduLibraryError:
            pytest.skip("用户信息端点不可达")

        assert isinstance(data, dict), "用户信息响应应为 dict"

    def test_user_center_structure(self, authed_client):
        """GET /User/Center/index 响应应为字典。"""
        try:
            data = authed_client._request("GET", authed_client.urls["user_center"])
        except HduLibraryError:
            pytest.skip("用户中心端点不可达")

        assert isinstance(data, dict), "用户中心响应应为 dict"


# ============================================================================
# 契约：错误响应格式
# ============================================================================
class TestErrorResponseContract:
    """各类错误场景的响应格式一致性校验。"""

    def test_404_or_error_on_bad_endpoint(self, authed_client):
        """访问不存在的端点应有明确的错误响应。"""
        import requests

        try:
            resp = authed_client.session.get(
                "https://hdu.huitu.zhishulib.com/Nonexistent/Endpoint",
                timeout=10,
            )
            # 无论返回什么状态码，都应有响应体
            assert resp.status_code in (200, 302, 404, 500), f"意外状态码: {resp.status_code}"
        except requests.RequestException:
            pytest.skip("网络不可达")

    def test_booking_with_invalid_seat_contract(self, authed_client):
        """无效座位号的预约响应格式应与正常失败一致。"""
        from datetime import datetime, timedelta

        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow = tomorrow.replace(hour=13, minute=0, second=0, microsecond=0)

        try:
            result = authed_client.book_seat(
                seat_id="999999",
                uid=authed_client.uid,
                begin_time=tomorrow,
                duration_hours=1,
            )
        except HduLibraryError:
            pytest.skip("网络错误，跳过契约校验")

        # 应当返回某种错误结构
        assert isinstance(result, dict)
        assert "CODE" in result
