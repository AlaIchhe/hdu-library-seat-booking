"""会话认证 — Cookie 加载 + UID 解析。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .. import constants as C
from .. import exceptions as E
from .protocols import ISessionAuthenticator

if TYPE_CHECKING:
    from .protocols import Instrumentation


class SessionAuthenticator(ISessionAuthenticator):
    """Cookie 认证实现 — 从 Cookie 文件或字符串加载会话。"""

    def __init__(
        self,
        transport,
        instrumentation: Instrumentation | None = None,
    ):
        self._transport = transport
        self._instrumentation = instrumentation
        self.uid: str = ""
        self.name: str = ""

    def _record(self, category: str, message: str, exc: Exception | None = None) -> None:
        if self._instrumentation:
            self._instrumentation.record(category, message, exc, module=__name__)

    def set_cookie_header(self, cookie_string: str) -> None:
        """从原始 Cookie 请求头字符串加载 Cookie。"""
        loaded = False
        for part in cookie_string.split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            self._transport.session.cookies.set(
                name, value, domain="hdu.huitu.zhishulib.com", path="/"
            )
            loaded = True
        if not loaded:
            self._record("AUTH", "Cookie 字符串中没有有效的键值对")
            raise E.CookieError("Cookie 字符串中没有有效的键值对")

    def set_cookies_from_json_file(self, json_path: str) -> None:
        """从 Netscape 格式的 JSON Cookie 文件加载。"""
        path = Path(json_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            self._record("AUTH", f"Cookie 文件不存在：{path}")
            raise E.CookieError(f"Cookie 文件不存在：{path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._record("JSON_PARSE", f"Cookie 文件 JSON 解析失败：{path}", exc)
            raise E.CookieError(f"Cookie 文件 JSON 解析失败：{path}") from exc

        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
            self._record("AUTH", "Cookie 文件格式无效：缺少 cookies 列表")
            raise E.CookieError("Cookie 文件格式无效：缺少 cookies 列表")

        for item in cookies:
            name = item.get("name")
            value = item.get("value")
            if not name or value is None:
                continue
            from requests.cookies import create_cookie

            cookie = create_cookie(
                name=str(name),
                value=str(value),
                domain=item.get("domain") or "hdu.huitu.zhishulib.com",
                path=item.get("path") or "/",
                secure=bool(item.get("secure", False)),
            )
            self._transport.session.cookies.set_cookie(cookie)

    def validate_cookie(self) -> bool:
        """验证当前 Session 中的 Cookie 是否仍然有效。"""
        from .user_info import find_user_info

        url = C.URLS.get("user_base_info")
        if not url:
            return False
        try:
            data = self._transport.request("GET", url)
        except E.HduLibraryError:
            return False
        candidate = find_user_info(data)
        return bool(candidate and candidate.get("uid"))

    def resolve_uid(self) -> str:
        """当 UID 未知时，从 API 响应中自动探测。"""
        from .user_info import find_user_info

        if self.uid:
            return self.uid

        for endpoint_key in ("user_base_info", "user_center"):
            url = C.URLS.get(endpoint_key)
            if not url:
                continue
            try:
                data = self._transport.request("GET", url)
            except E.HduLibraryError:
                continue
            candidate = find_user_info(data)
            if candidate and candidate.get("uid"):
                self.uid = str(candidate["uid"])
                if candidate.get("name") and not self.name:
                    self.name = str(candidate["name"])
                return self.uid

        self._record("AUTH", "未能识别用户 uid")
        raise E.HduLibraryError("未能识别用户 uid。请在配置文件 user_info.uid 中填写慧图内部 uid。")
