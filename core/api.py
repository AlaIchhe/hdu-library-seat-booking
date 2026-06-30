"""
HduLibraryClient — 慧图图书馆预约平台统一 API 客户端。

封装所有 HTTP 交互：
  - Session 初始化（Headers、SSL、Params）
  - Cookie 认证（主流程）+ Cookie 有效性验证
  - 房间类型 → 房间详情 → 座位地图 → 预约提交 完整链路
  - Api-Token 签名（内部调用 auth 模块）

注意：密码认证已移至 core.password_auth 模块，不纳入主流程。
"""

import json
from pathlib import Path
from urllib.parse import unquote

import requests

from . import constants as C
from . import exceptions as E
from .auth import generate_api_token
from .infrastructure.protocols import ILibraryGateway, ISessionAuthenticator
from .infrastructure.user_info import find_user_info
from .metrics import ErrorCategory, error_tracker


class HduLibraryClient(ISessionAuthenticator, ILibraryGateway):
    """慧图图书馆平台 HTTP 客户端。

    使用方法
    --------
    # 方式 1：Cookie 认证
    client = HduLibraryClient()
    client.set_cookie_header("uid=xxx; auth=yyy")
    client.resolve_uid()  # 从 API 自动获取 UID

    # 方式 2：密码登录
    client = HduLibraryClient()
    client.login("学号", "密码")

    # 查询 - 预约
    rooms = client.get_room_types()
    detail = client.get_room_detail(rooms[0]["query"])
    floors = client.get_seat_map(detail["space_category"]["category_id"],
                                  detail["space_category"]["content_id"],
                                  begin_time, duration)
    result = client.book_seat("12345", uid, begin_time, duration_hours)
    """

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def __init__(self, config=None, timeout=None):
        """初始化客户端。

        参数
        ----------
        config : dict, optional
            配置字典。通常来自 config.yaml，包含 session、urls 等字段。
        timeout : int, optional
            HTTP 请求超时秒数。默认使用 DEFAULT_TIMEOUT。
        """
        self.config = config or {}
        self.timeout = int(
            (self.config.get("request") or {}).get("timeout") or timeout or C.DEFAULT_TIMEOUT
        )
        self.urls = self.config.get("urls") or dict(C.URLS)
        self._uid = str((self.config.get("user_info") or {}).get("uid") or "")
        self._name = str((self.config.get("user_info") or {}).get("name") or "")

        # 创建 requests.Session 并设置默认 headers / params
        session_cfg = self.config.get("session") or {}
        self.session = requests.Session()
        self.session.headers.update(session_cfg.get("headers") or dict(C.DEFAULT_HEADERS))
        self.session.params = session_cfg.get("params") or dict(C.DEFAULT_SESSION_PARAMS)
        self.session.trust_env = bool(session_cfg.get("trust_env", False))
        self.session.verify = bool(session_cfg.get("verify", False))

        # 禁用 SSL 警告
        requests.packages.urllib3.disable_warnings()

    @property
    def uid(self) -> str:
        return self._uid  # type: ignore[no-any-return]

    @uid.setter
    def uid(self, value: str) -> None:
        self._uid = str(value)

    @property
    def name(self) -> str:
        return self._name  # type: ignore[no-any-return]

    @name.setter
    def name(self, value: str) -> None:
        self._name = str(value)

    # ------------------------------------------------------------------
    # HTTP 请求
    # ------------------------------------------------------------------
    def _request(self, method, url, data=None):
        """统一 HTTP 请求封装，含错误处理。"""
        try:
            if method == "GET":
                resp = self.session.get(url, timeout=self.timeout)
            else:
                resp = self.session.post(url, data=data, timeout=self.timeout)
        except requests.RequestException as exc:
            error_tracker.record(
                ErrorCategory.NETWORK,
                f"请求失败：{exc}",
                exc,
                module=__name__,
            )
            raise E.HduLibraryError(f"请求失败：{exc}") from exc

        if resp.status_code not in (200, 302):
            error_tracker.record(
                ErrorCategory.NETWORK,
                f"HTTP {resp.status_code} {url}",
                module=__name__,
            )
            raise E.HduLibraryError(f"请求失败：HTTP {resp.status_code} {url}")
        try:
            return resp.json()
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.JSON_PARSE,
                f"JSON 解析失败：{exc}",
                exc,
                module=__name__,
            )
            raise E.HduLibraryError(f"JSON 解析失败：{exc}") from exc

    # ------------------------------------------------------------------
    # 认证（Cookie）
    # ------------------------------------------------------------------
    def set_cookie_header(self, cookie_string):
        """从原始 Cookie 请求头字符串加载 Cookie。

        参数
        ----------
        cookie_string : str
            浏览器中复制的 Cookie 字符串（例如 "uid=xxx; auth=yyy"）。
        """
        loaded = False
        for part in cookie_string.split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            self.session.cookies.set(name, value, domain="hdu.huitu.zhishulib.com", path="/")
            loaded = True
        if not loaded:
            error_tracker.record(
                ErrorCategory.AUTH,
                "Cookie 字符串中没有有效的键值对",
                module=__name__,
            )
            raise E.CookieError("Cookie 字符串中没有有效的键值对")

    def set_cookies_from_json_file(self, json_path):
        """从 Netscape 格式的 JSON Cookie 文件加载。

        参数
        ----------
        json_path : str or Path
            Cookie JSON 文件路径。
        """
        path = Path(json_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            error_tracker.record(
                ErrorCategory.AUTH,
                f"Cookie 文件不存在：{path}",
                module=__name__,
            )
            raise E.CookieError(f"Cookie 文件不存在：{path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.JSON_PARSE,
                f"Cookie 文件 JSON 解析失败：{path}",
                exc,
                module=__name__,
            )
            raise E.CookieError(f"Cookie 文件 JSON 解析失败：{path}") from exc
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
            error_tracker.record(
                ErrorCategory.AUTH,
                "Cookie 文件格式无效：缺少 cookies 列表",
                module=__name__,
            )
            raise E.CookieError("Cookie 文件格式无效：缺少 cookies 列表")
        for item in cookies:
            name = item.get("name")
            value = item.get("value")
            if not name or value is None:
                continue
            cookie = requests.cookies.create_cookie(
                name=str(name),
                value=str(value),
                domain=item.get("domain") or "hdu.huitu.zhishulib.com",
                path=item.get("path") or "/",
                secure=bool(item.get("secure", False)),
            )
            self.session.cookies.set_cookie(cookie)

    # ------------------------------------------------------------------
    # Cookie 有效性验证
    # ------------------------------------------------------------------
    def validate_cookie(self) -> bool:
        """验证当前 Session 中的 Cookie 是否仍然有效。

        通过调用 user_base_info 端点并检查响应是否包含有效的 UID
        来判断，而非仅依赖本地 Cookie 解析。

        返回
        -------
        bool
            True 表示 Cookie 有效且能识别用户。
        """
        url = self.urls.get("user_base_info") or C.URLS.get("user_base_info")
        if not url:
            return False
        try:
            data = self._request("GET", url)
        except E.HduLibraryError:
            return False
        candidate = find_user_info(data)
        return bool(candidate and candidate.get("uid"))

    # ------------------------------------------------------------------
    # 解析用户 UID
    # ------------------------------------------------------------------
    def resolve_uid(self):
        """当 UID 未知时，从 API 响应中自动探测。

        依次尝试 user_base_info / user_center 端点，递归搜索
        JSON 中与 UID 模式匹配的字段。
        """
        if self.uid:
            return self.uid

        for endpoint_key in ("user_base_info", "user_center"):
            url = self.urls.get(endpoint_key)
            if not url:
                continue
            try:
                data = self._request("GET", url)
            except E.HduLibraryError:
                continue
            candidate = find_user_info(data)
            if candidate and candidate.get("uid"):
                self._uid = str(candidate["uid"])
                if candidate.get("name") and not self._name:
                    self._name = str(candidate["name"])
                return self._uid

        error_tracker.record(
            ErrorCategory.AUTH,
            "未能识别用户 uid",
            module=__name__,
        )
        raise E.HduLibraryError("未能识别用户 uid。请在配置文件 user_info.uid 中填写慧图内部 uid。")

    # ------------------------------------------------------------------
    # 房间查询
    # ------------------------------------------------------------------
    def get_room_types(self):
        """获取所有可用的房间类型列表。

        返回
        -------
        list[dict]
            每个元素格式：{"name": "自习室", "query": "space_category[...]=..."}
        """
        url = self.urls.get("query_rooms") or C.URLS["query_rooms"]
        data = self._request("GET", url)
        raw_items = data["content"]["children"][1]["defaultItems"]
        room_items = []
        for item in raw_items:
            link_url = unquote(item["link"]["url"])
            query = link_url.split("?", 1)[1]
            room_items.append({"name": item["name"], "query": query})
        return room_items

    def get_room_detail(self, room_query_string):
        """查询单个房间的详细信息（分类 ID、时间范围等）。

        参数
        ----------
        room_query_string : str
            get_room_types() 返回的 query 字段值。

        返回
        -------
        dict
            房间详情（含 space_category、range 等）。
        """
        url = self.urls.get("query_seats") or C.URLS["query_seats"]
        full_url = url + "?" + room_query_string
        resp = self._request("GET", full_url)
        detail = resp.get("data")
        if not detail:
            error_tracker.record(
                ErrorCategory.ROOM_QUERY,
                "房间信息为空",
                module=__name__,
            )
            raise E.RoomQueryError("房间信息为空")
        return detail

    def get_seat_map(self, category_id, content_id, lookup_time, duration_hours=1, num=1):
        """根据分类和参考时间查询座位布局（楼层 + 座位 POI）。

        参数
        ----------
        category_id : str
            房间 space_category[category_id]。
        content_id : str
            房间 space_category[content_id]。
        lookup_time : datetime
            参考查询时间。
        duration_hours : int, optional
            查询时长（小时）。默认 1。
        num : int, optional
            座位数量。默认 1。

        返回
        -------
        list[dict]
            楼层列表，每个元素包含 seatMap 信息。
        """
        url = self.urls.get("query_seats") or C.URLS["query_seats"]
        payload = {
            "beginTime": lookup_time.timestamp(),
            "duration": int(duration_hours * 3600),
            "num": num,
            "space_category[category_id]": str(category_id),
            "space_category[content_id]": str(content_id),
        }
        resp = self._request("POST", url, payload)
        try:
            return resp["allContent"]["children"][2]["children"]["children"]
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.SEAT_QUERY,
                f"座位分布解析失败：{exc}",
                exc,
                module=__name__,
            )
            raise E.SeatQueryError(f"座位分布解析失败：{exc}") from exc

    def find_seat_in_floors(self, floors, floor_id, seat_num):
        """在楼层列表中定位指定楼层和座位号。

        参数
        ----------
        floors : list[dict]
            get_seat_map() 返回的楼层列表。
        floor_id : str or int
            目标楼层 ID。
        seat_num : str or int
            目标座位号。

        返回
        -------
        tuple[dict, dict]
            (楼层对象, 座位 POI 对象)
        """
        floor_id = str(floor_id)
        seat_num = str(seat_num)
        floor_names = []

        target_floor = None
        for item in floors:
            info = item.get("seatMap", {}).get("info", {})
            floor_names.append(f"{item.get('roomName', '?')}={info.get('id', '?')}")
            if str(info.get("id")) == floor_id:
                target_floor = item
                break

        if not target_floor:
            error_tracker.record(
                ErrorCategory.SEAT_QUERY,
                f"找不到楼层 id={floor_id}。可用：{', '.join(floor_names)}",
                module=__name__,
            )
            raise E.SeatQueryError(f"找不到楼层 id={floor_id}。可用楼层：{', '.join(floor_names)}")

        seats = target_floor["seatMap"]["POIs"]
        matches = [s for s in seats if str(s.get("title")) == seat_num]
        if not matches:
            error_tracker.record(
                ErrorCategory.SEAT_QUERY,
                f"{target_floor.get('roomName')} 中找不到 {seat_num} 座",
                module=__name__,
            )
            raise E.SeatQueryError(f"{target_floor.get('roomName')} 中找不到 {seat_num} 座")
        if len(matches) > 1:
            error_tracker.record(
                ErrorCategory.SEAT_QUERY,
                f"{target_floor.get('roomName')} 中存在多个 {seat_num} 座",
                module=__name__,
            )
            raise E.SeatQueryError(f"{target_floor.get('roomName')} 中存在多个 {seat_num} 座")
        return target_floor, matches[0]

    # ------------------------------------------------------------------
    # 预约
    # ------------------------------------------------------------------
    def book_seat(self, seat_id, uid, begin_time, duration_hours, is_recommend=1, dry_run=False):

        begin_ts = int(begin_time.timestamp())
        duration_sec = int(duration_hours * 3600)
        uid_str = str(uid)
        seat_str = str(seat_id)

        # 生成签名
        api_token, api_time = generate_api_token(
            seat_id=seat_str,
            uid=uid_str,
            begin_time=begin_ts,
            duration=duration_sec,
            is_recommend=is_recommend,
        )

        payload = {
            "beginTime": begin_ts,
            "duration": duration_sec,
            "is_recommend": is_recommend,
            "api_time": api_time,
            "seats[0]": seat_str,
            "seatBookers[0]": uid_str,
        }

        if dry_run:
            return {"dry_run": True, "payload": payload, "api_token": api_token}

        self.session.headers["Api-Token"] = api_token
        url = self.urls.get("book_seat") or C.URLS["book_seat"]
        return self._request("POST", url, payload)
