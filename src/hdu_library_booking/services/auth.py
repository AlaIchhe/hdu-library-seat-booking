"""认证服务 — 编排 Cookie 认证流程。

密码认证已移至 api.password_auth 模块，不纳入主流程。
"""

from hdu_library_booking.exceptions import CookieError
from hdu_library_booking.gateways.protocols import ISessionAuthenticator
from hdu_library_booking.observability._error_tracker import ErrorCategory, error_tracker


class AuthService:
    """认证编排器 (SRP: 只负责身份认证流程)。

    依赖注入 ISessionAuthenticator，面向具体需求。
    """

    def __init__(self, authenticator: ISessionAuthenticator):
        self._auth = authenticator

    # ------------------------------------------------------------------
    # Cookie 认证
    # ------------------------------------------------------------------
    def authenticate_with_cookie(self, cookie_string: str, validate: bool = True) -> bool:
        """使用 Cookie 字符串认证。"""
        if not cookie_string or not cookie_string.strip():
            error_tracker.record(
                ErrorCategory.AUTH,
                "Cookie 字符串为空",
                module=__name__,
            )
            raise CookieError("Cookie 字符串为空")

        self._auth.set_cookie_header(cookie_string)
        self._auth.resolve_uid()
        if validate and not self._auth.validate_cookie():
            error_tracker.record(
                ErrorCategory.AUTH,
                "Cookie 字符串已过期或无效",
                module=__name__,
            )
            return False
        return bool(self._auth.uid)

    def authenticate_with_cookie_file(self, json_path: str, validate: bool = True) -> bool:
        """从 Netscape JSON Cookie 文件认证。"""
        self._auth.set_cookies_from_json_file(json_path)
        self._auth.resolve_uid()
        if validate and not self._auth.validate_cookie():
            error_tracker.record(
                ErrorCategory.AUTH,
                f"Cookie 文件已过期或无效：{json_path}",
                module=__name__,
            )
            return False
        return bool(self._auth.uid)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @property
    def uid(self) -> str:
        """当前已认证用户的 UID。"""
        return self._auth.uid

    @property
    def name(self) -> str:
        """当前已认证用户的姓名。"""
        return self._auth.name

    def is_authenticated(self) -> bool:
        """检查是否已完成认证（UID 已知）。"""
        return bool(self._auth.uid)
