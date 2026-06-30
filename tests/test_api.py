"""Tests for core.api — HduLibraryClient HTTP client (with mocking)."""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.api import HduLibraryClient
from core.exceptions import (
    CookieError,
    HduLibraryError,
    LoginError,
    RoomQueryError,
    SeatQueryError,
)


class TestHduLibraryClientInit:
    def test_default_init(self):
        client = HduLibraryClient()
        assert client.timeout == 10
        assert isinstance(client.session, requests.Session)
        assert client.uid == ""

    def test_init_with_config(self):
        config = {
            "request": {"timeout": 30},
            "user_info": {"uid": "999", "name": "test"},
        }
        client = HduLibraryClient(config=config)
        assert client.timeout == 30
        assert client.uid == "999"
        assert client.name == "test"

    def test_init_with_explicit_timeout(self):
        client = HduLibraryClient(timeout=60)
        assert client.timeout == 60

    def test_config_override_timeout(self):
        """显式 timeout 参数优先于 config。"""
        config = {"request": {"timeout": 5}}
        client = HduLibraryClient(config=config, timeout=30)
        assert client.timeout == 5  # config 优先


class TestHduLibraryClientRequest:
    def test_get_request_success(self):
        client = HduLibraryClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"CODE": "ok"}
        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            result = client._request("GET", "https://test.com/api")
            assert result == {"CODE": "ok"}
            mock_get.assert_called_once()

    def test_post_request_success(self):
        client = HduLibraryClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"CODE": "ok"}
        with patch.object(client.session, "post", return_value=mock_resp) as _mock_post:
            result = client._request("POST", "https://test.com/api", {"key": "val"})
            assert result == {"CODE": "ok"}

    def test_request_exception_wraps(self):
        client = HduLibraryClient()
        with patch.object(
            client.session, "get", side_effect=requests.ConnectionError("connection refused")
        ):
            with pytest.raises(HduLibraryError, match="请求失败"):
                client._request("GET", "https://test.com/api")

    def test_bad_status_code(self):
        client = HduLibraryClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(HduLibraryError, match="HTTP 500"):
                client._request("GET", "https://test.com/api")

    def test_json_parse_error(self):
        client = HduLibraryClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(HduLibraryError, match="JSON 解析失败"):
                client._request("GET", "https://test.com/api")

    def test_302_is_ok(self):
        """302 重定向也应视为成功状态码。"""
        client = HduLibraryClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.json.return_value = {"redirect": True}
        with patch.object(client.session, "get", return_value=mock_resp):
            result = client._request("GET", "https://test.com/api")
            assert result == {"redirect": True}


class TestHduLibraryClientCookie:
    def test_set_cookie_header_valid(self):
        client = HduLibraryClient()
        client.set_cookie_header("uid=12345; auth=abcdef")
        cookies = client.session.cookies
        assert cookies.get("uid", domain="hdu.huitu.zhishulib.com") == "12345"
        assert cookies.get("auth", domain="hdu.huitu.zhishulib.com") == "abcdef"

    def test_set_cookie_header_empty(self):
        client = HduLibraryClient()
        with pytest.raises(CookieError, match="没有有效的键值对"):
            client.set_cookie_header("")

    def test_set_cookie_header_no_valid_pairs(self):
        client = HduLibraryClient()
        with pytest.raises(CookieError, match="没有有效的键值对"):
            client.set_cookie_header(";;")

    def test_set_cookies_from_json_file(self):
        cookie_data = {
            "cookies": [
                {"name": "uid", "value": "12345", "domain": "example.com", "path": "/"},
                {"name": "auth", "value": "token123"},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(cookie_data, f)
            path = f.name
        try:
            client = HduLibraryClient()
            client.set_cookies_from_json_file(path)
            assert client.session.cookies.get("uid") == "12345"
        finally:
            os.unlink(path)

    def test_set_cookies_from_json_file_missing(self):
        client = HduLibraryClient()
        with pytest.raises(CookieError, match="不存在"):
            client.set_cookies_from_json_file("/nonexistent/cookies.json")

    def test_set_cookies_from_json_invalid_format(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"not_cookies": []}, f)
            path = f.name
        try:
            client = HduLibraryClient()
            with pytest.raises(CookieError, match="格式无效"):
                client.set_cookies_from_json_file(path)
        finally:
            os.unlink(path)


class TestHduLibraryClientLogin:
    def test_login_success(self):
        client = HduLibraryClient()
        mock_resp = {
            "CODE": "ok",
            "DATA": {
                "uid": "12345",
                "user_info": {"name": "测试用户"},
            },
        }
        with patch.object(client, "_request", return_value=mock_resp):
            result = client.login("user", "pass")
            assert result is True
            assert client.uid == "12345"
            assert client.name == "测试用户"

    def test_login_failure(self):
        client = HduLibraryClient()
        mock_resp = {"CODE": "error", "MESSAGE": "密码错误"}
        with patch.object(client, "_request", return_value=mock_resp):
            result = client.login("user", "wrong")
            assert result is False

    def test_login_missing_credentials(self):
        client = HduLibraryClient()
        with pytest.raises(LoginError, match="登录名或密码"):
            client.login(None, None)

    def test_login_from_config(self):
        config = {"user_info": {"login_name": "cfguser", "password": "cfgpass"}}
        client = HduLibraryClient(config=config)
        mock_resp = {"CODE": "ok", "DATA": {"uid": "999"}}
        with patch.object(client, "_request", return_value=mock_resp):
            assert client.login() is True


class TestHduLibraryClientResolveUid:
    def test_already_has_uid(self):
        client = HduLibraryClient()
        client.uid = "12345"
        assert client.resolve_uid() == "12345"

    def test_resolve_from_user_base_info(self):
        client = HduLibraryClient()
        mock_data = {
            "DATA": {"name": {"name": "currentUser", "value": '{"uid": "888", "name": "张三"}'}}
        }
        with patch.object(client, "_request", return_value=mock_data):
            uid = client.resolve_uid()
            assert uid == "888"
            assert client.name == "张三"

    def test_resolve_failure(self):
        client = HduLibraryClient()
        with patch.object(client, "_request", side_effect=HduLibraryError("fail")):
            with pytest.raises(HduLibraryError, match="未能识别"):
                client.resolve_uid()


class TestHduLibraryClientRoomQuery:
    def test_get_room_types(self):
        client = HduLibraryClient()
        mock_data = {
            "content": {
                "children": [
                    {},
                    {
                        "defaultItems": [
                            {
                                "name": "自习室",
                                "link": {"url": "/search?space_category%5Bcategory_id%5D=10"},
                            },
                            {
                                "name": "阅览室",
                                "link": {"url": "/search?space_category%5Bcategory_id%5D=20"},
                            },
                        ]
                    },
                ]
            }
        }
        with patch.object(client, "_request", return_value=mock_data):
            rooms = client.get_room_types()
            assert len(rooms) == 2
            assert rooms[0]["name"] == "自习室"
            assert "query" in rooms[0]

    def test_get_room_detail_empty(self):
        client = HduLibraryClient()
        with patch.object(client, "_request", return_value={"data": None}):
            with pytest.raises(RoomQueryError, match="房间信息为空"):
                client.get_room_detail("some_query")

    def test_get_seat_map(self):
        client = HduLibraryClient()
        mock_resp = {
            "allContent": {
                "children": [
                    {},
                    {},
                    {"children": {"children": [{"roomName": "3F"}]}},
                ]
            }
        }
        with patch.object(client, "_request", return_value=mock_resp):
            floors = client.get_seat_map("10", "20", datetime.now(), 1)
            assert floors == [{"roomName": "3F"}]

    def test_get_seat_map_parse_error(self):
        client = HduLibraryClient()
        with patch.object(client, "_request", return_value={"bad": "structure"}):
            with pytest.raises(SeatQueryError, match="座位分布解析失败"):
                client.get_seat_map("10", "20", datetime.now(), 1)


class TestHduLibraryClientFindSeat:
    def build_floors(self):
        return [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [
                        {"title": "296", "id": "seat_296"},
                        {"title": "297", "id": "seat_297"},
                    ],
                },
            },
        ]

    def test_find_seat_success(self):
        client = HduLibraryClient()
        floors = self.build_floors()
        floor, seat = client.find_seat_in_floors(floors, "1558", "296")
        assert floor["roomName"] == "3楼"
        assert seat["id"] == "seat_296"

    def test_find_seat_floor_not_found(self):
        client = HduLibraryClient()
        with pytest.raises(SeatQueryError, match="找不到楼层"):
            client.find_seat_in_floors(self.build_floors(), "9999", "296")

    def test_find_seat_not_found(self):
        client = HduLibraryClient()
        with pytest.raises(SeatQueryError, match="找不到"):
            client.find_seat_in_floors(self.build_floors(), "1558", "999")

    def test_multiple_matches(self):
        floors = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [
                        {"title": "100", "id": "a"},
                        {"title": "100", "id": "b"},
                    ],
                },
            },
        ]
        client = HduLibraryClient()
        with pytest.raises(SeatQueryError, match="多个"):
            client.find_seat_in_floors(floors, "1558", "100")


class TestHduLibraryClientBookSeat:
    def test_dry_run(self):
        client = HduLibraryClient()
        client.uid = "12345"
        begin = datetime(2026, 7, 1, 13, 0, 0)
        result = client.book_seat("296", "12345", begin, 9, dry_run=True)
        assert result["dry_run"] is True
        assert "payload" in result
        assert "api_token" in result

    def test_book_seat_submits(self):
        client = HduLibraryClient()
        client.uid = "12345"
        begin = datetime(2026, 7, 1, 13, 0, 0)
        mock_resp = {"CODE": "ok", "MESSAGE": "预约成功"}
        with patch.object(client, "_request", return_value=mock_resp) as _mock_req:
            result = client.book_seat("296", "12345", begin, 9)
            assert result == mock_resp
            assert "Api-Token" in client.session.headers


class TestHduLibraryClientFindUserInfo:
    def test_user_info_from_dict(self):
        client = HduLibraryClient()
        result = client._user_info_from_dict({"uid": "123", "name": "张三"}, hint="currentUser")
        assert result is not None
        assert result["uid"] == "123"
        assert result["name"] == "张三"

    def test_no_match_returns_none(self):
        client = HduLibraryClient()
        result = client._user_info_from_dict({"foo": "bar"})
        assert result is None

    def test_score_boosts_for_relevant_hints(self):
        client = HduLibraryClient()
        r1 = client._user_info_from_dict({"uid": "1"}, hint="something")
        r2 = client._user_info_from_dict({"uid": "2"}, hint="currentLogin")
        assert r2["score"] > (r1["score"] if r1 else 0)
