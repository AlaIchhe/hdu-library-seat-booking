"""
HduLibraryClient — 慧图图书馆预约平台统一 API 客户端。

封装四个项目的所有公共 HTTP 交互：
  - Session 初始化（Headers、SSL、Params）
  - Cookie / 密码两种认证方式
  - 房间类型 → 房间详情 → 座位地图 → 预约提交 完整链路
  - Api-Token 签名（内部调用 auth 模块）
"""

import json
import time
from pathlib import Path
from urllib.parse import unquote

import requests

from . import constants as C
from . import exceptions as E
from .auth import generate_api_token


class HduLibraryClient:
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
            (self.config.get("request") or {}).get("timeout")
            or timeout
            or C.DEFAULT_TIMEOUT
        )
        self.urls = self.config.get("urls") or dict(C.URLS)
        self.uid = str(
            (self.config.get("user_info") or {}).get("uid") or ""
        )
        self.name = str(
            (self.config.get("user_info") or {}).get("name") or ""
        )

        # 创建 requests.Session 并设置默认 headers / params
        session_cfg = self.config.get("session") or {}
        self.session = requests.Session()
        self.session.headers.update(
            session_cfg.get("headers") or dict(C.DEFAULT_HEADERS)
        )
        self.session.params = session_cfg.get("params") or dict(C.DEFAULT_SESSION_PARAMS)
        self.session.trust_env = bool(session_cfg.get("trust_env", False))
        self.session.verify = bool(session_cfg.get("verify", False))

        # 禁用 SSL 警告
        requests.packages.urllib3.disable_warnings()

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
            raise E.HduLibraryError(f"请求失败：{exc}") from exc

        if resp.status_code not in (200, 302):
            raise E.HduLibraryError(
                f"请求失败：HTTP {resp.status_code} {url}"
            )
        try:
            return resp.json()
        except Exception as exc:
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
            self.session.cookies.set(
                name, value, domain="hdu.huitu.zhishulib.com", path="/"
            )
            loaded = True
        if not loaded:
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
            raise E.CookieError(f"Cookie 文件不存在：{path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
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
    # 认证（用户名密码登录）
    # ------------------------------------------------------------------
    def login(self, username=None, password=None, org_id=None):
        """通过用户名密码登录慧图平台。

        参数
        ----------
        username : str, optional
            学号 / 登录名。若为 None 则从 config 读取。
        password : str, optional
            密码。若为 None 则从 config 读取。
        org_id : str, optional
            机构 ID。默认 "104"（HDU）。

        返回
        -------
        bool
            登录是否成功。
        """
        user_info = self.config.get("user_info") or {}
        uname = username or user_info.get("login_name")
        pwd = password or user_info.get("password")
        oid = org_id or user_info.get("org_id") or C.DEFAULT_ORG_ID

        if not uname or not pwd:
            raise E.LoginError("登录名或密码未提供")

        url = self.urls.get("login") or C.URLS["login"]
        resp = self._request("POST", url, {
            "login_name": uname,
            "password": pwd,
            "org_id": oid,
        })

        if resp.get("CODE") == "ok":
            data = resp.get("DATA", resp)
            self.uid = str(data.get("uid", ""))
            # user_info 嵌套在 DATA 下
            ui = data.get("user_info") or {}
            self.name = str(ui.get("name") or data.get("name") or "")
            return True
        return False

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
            candidate = self._find_user_info(data)
            if candidate and candidate.get("uid"):
                self.uid = str(candidate["uid"])
                if candidate.get("name") and not self.name:
                    self.name = str(candidate["name"])
                return self.uid

        raise E.HduLibraryError(
            "未能识别用户 uid。请在配置文件 user_info.uid 中填写慧图内部 uid。"
        )

    def _find_user_info(self, data):
        """递归搜索 JSON 中与用户信息匹配的字段。"""
        candidates = []

        def walk(obj, hint=""):
            if isinstance(obj, dict):
                if "name" in obj and "value" in obj and isinstance(obj.get("value"), str):
                    walk(obj["value"], str(obj.get("name") or hint))
                c = self._user_info_from_dict(obj, hint)
                if c:
                    candidates.append(c)
                for k, v in obj.items():
                    walk(v, f"{hint}.{k}" if hint else str(k))
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, hint)
            elif isinstance(obj, str):
                val = obj.strip()
                if val and val[0] in "[{":
                    try:
                        walk(json.loads(val), hint)
                    except Exception:
                        pass

        walk(data)
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        return candidates[0]

    def _user_info_from_dict(self, data, hint=""):
        """从字典中提取用户 UID 和姓名候选。"""
        id_keys = ("uid", "user_id", "userId", "booker", "id")
        name_keys = (
            "name", "real_name", "realName", "bookerName",
            "username", "login_name", "nickname",
        )
        uid = None
        name = None
        for k in id_keys:
            v = data.get(k)
            if v is not None and str(v).isdigit():
                uid = str(v)
                break
        for k in name_keys:
            v = data.get(k)
            if v:
                name = str(v)
                break

        score = 1 if name else 0
        hint_lower = hint.lower()
        for kw in ("current", "user", "login", "lab4"):
            if kw in hint_lower:
                score += 2
        if uid and (score > 0 or name):
            return {"uid": uid, "name": name, "score": score}
        return None

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
        url = (self.urls.get("query_seats") or C.URLS["query_seats"])
        full_url = url + "?" + room_query_string
        resp = self._request("GET", full_url)
        detail = resp.get("data")
        if not detail:
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
            floor_names.append(
                f"{item.get('roomName', '?')}={info.get('id', '?')}"
            )
            if str(info.get("id")) == floor_id:
                target_floor = item
                break

        if not target_floor:
            raise E.SeatQueryError(
                f"找不到楼层 id={floor_id}。可用楼层：{', '.join(floor_names)}"
            )

        seats = target_floor["seatMap"]["POIs"]
        matches = [
            s for s in seats if str(s.get("title")) == seat_num
        ]
        if not matches:
            raise E.SeatQueryError(
                f"{target_floor.get('roomName')} 中找不到 {seat_num} 座"
            )
        if len(matches) > 1:
            raise E.SeatQueryError(
                f"{target_floor.get('roomName')} 中存在多个 {seat_num} 座"
            )
        return target_floor, matches[0]

    # ------------------------------------------------------------------
    # 预约
    # ------------------------------------------------------------------
    def book_seat(self, seat_id, uid, begin_time, duration_hours, is_recommend=1,
                  dry_run=False):
        """提交座位预约请求。

        内部自动生成 Api-Token 签名。

        参数
        ----------
        seat_id : str or int
            座位 ID。
        uid : str
            用户 UID。
        begin_time : datetime
            预约开始时间（含时区信息）。
        duration_hours : int
            预约时长（小时）。
        is_recommend : int, optional
            是否推荐。默认 1（兼容 Instant / Master）。
        dry_run : bool, optional
            若为 True，只生成 payload 不提交请求。

        返回
        -------
        dict
            API 返回的 JSON 响应（或 dry_run 时的 payload 字典）。
        """
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
