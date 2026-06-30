"""
认证服务。

编排 Cookie / 密码两种认证流程，支持交互式密码输入。
启动时自动加载项目根目录下的 .env 文件（如果存在）。
"""

import getpass
from pathlib import Path

import dotenv

from core import HduLibraryClient
from core.exceptions import CookieError
from core.metrics import ErrorCategory, error_tracker

# 加载项目根目录的 .env（不覆盖已有环境变量）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_PROJECT_ROOT / ".env", override=False)


class AuthService:
    """认证编排器 (SRP: 只负责身份认证流程)。

    依赖注入 HduLibraryClient，面向具体需求（HTTP 交互已在 core 中封装）。
    """

    def __init__(self, client: HduLibraryClient):
        self.client = client

    # ------------------------------------------------------------------
    # Cookie 认证
    # ------------------------------------------------------------------
    def authenticate_with_cookie(self, cookie_string: str, validate: bool = True) -> bool:
        """使用 Cookie 字符串认证。

        参数
        ----------
        validate : bool
            True（默认）时会发起一次真实 API 请求验证 Cookie 是否有效。

        Returns
        -------
        bool
            True 表示成功加载并识别用户。
        """
        if not cookie_string or not cookie_string.strip():
            error_tracker.record(
                ErrorCategory.AUTH,
                "Cookie 字符串为空",
                module=__name__,
            )
            raise CookieError("Cookie 字符串为空")

        self.client.set_cookie_header(cookie_string)
        self.client.resolve_uid()
        if validate and not self.client.validate_cookie():
            error_tracker.record(
                ErrorCategory.AUTH,
                "Cookie 字符串已过期或无效",
                module=__name__,
            )
            return False
        return bool(self.client.uid)

    def authenticate_with_cookie_file(self, json_path: str, validate: bool = True) -> bool:
        """从 Netscape JSON Cookie 文件认证。

        参数
        ----------
        validate : bool
            True（默认）时会发起一次真实 API 请求验证 Cookie 是否有效。
        """
        self.client.set_cookies_from_json_file(json_path)
        self.client.resolve_uid()
        if validate and not self.client.validate_cookie():
            error_tracker.record(
                ErrorCategory.AUTH,
                f"Cookie 文件已过期或无效：{json_path}",
                module=__name__,
            )
            return False
        return bool(self.client.uid)

    # ------------------------------------------------------------------
    # 密码登录
    # ------------------------------------------------------------------
    def authenticate_with_password(
        self,
        username: str | None = None,
        password: str | None = None,
        org_id: str | None = None,
        interactive: bool = False,
    ) -> bool:
        """使用用户名密码登录。

        Parameters
        ----------
        username : str, optional
            登录名；为 None 时交互式询问。
        password : str, optional
            密码；为 None 时交互式询问（不回显）。
        org_id : str, optional
            机构 ID。
        interactive : bool
            True 时强制交互式输入缺失的凭据。

        Returns
        -------
        bool
            登录是否成功。
        """
        if interactive:
            if not username:
                username = input("学号 / 登录名: ").strip()
            if not password:
                password = getpass.getpass("密码 (输入不回显): ")

        result: bool = self.client.login(
            username=username,
            password=password,
            org_id=org_id,
        )
        return result

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @property
    def uid(self) -> str:
        """当前已认证用户的 UID。"""
        result: str = self.client.uid
        return result

    @property
    def name(self) -> str:
        """当前已认证用户的姓名。"""
        result: str = self.client.name
        return result

    def is_authenticated(self) -> bool:
        """检查是否已完成认证（UID 已知）。"""
        return bool(self.client.uid)
