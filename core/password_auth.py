"""
密码认证模块（保留参考，不纳入主认证流程）。

本模块提供两种密码认证方式：
  1. PasswordAuthClient.login() — 直接 POST 登录端点（CAS SSO 下无效）
  2. sso_browser_login() — Playwright 浏览器自动化 SSO 登录（受 CAPTCHA 限制）

注意
----
HDU 图书馆使用 CAS SSO 统一认证，直接 POST 登录端点会失败。
浏览器自动化路径则受 CAPTCHA 验证码限制，无法稳定运行。

因此本模块仅作保留参考，主认证流程 core/api.py 和
app/services/auth_service.py 不调用本模块的任何功能。

使用方式
--------
如需手动使用密码认证，可直接导入::

    from core.password_auth import PasswordAuthClient, sso_browser_login

    # 方式 1：直接 POST（CAS SSO 下无效）
    client = PasswordAuthClient()
    ok = client.login(username="学号", password="密码")

    # 方式 2：浏览器自动化（需 Playwright + 无 CAPTCHA）
    from core import HduLibraryClient
    client = HduLibraryClient()
    ok = sso_browser_login(client, username="学号", password="密码")
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from . import exceptions as E
from .metrics import ErrorCategory, error_tracker


class PasswordAuthClient:
    """密码认证客户端（保留参考，不纳入主流程）。

    提供直接 POST 登录端点的功能。在 CAS SSO 统一认证下，
    此方式无效，仅作为接口参考保留。
    """

    def __init__(self, config: dict | None = None) -> None:
        from .api import HduLibraryClient

        self._client = HduLibraryClient(config=config)

    def login(
        self,
        username: str | None = None,
        password: str | None = None,
        org_id: str | None = None,
    ) -> bool:
        """通过用户名密码直接 POST 登录端点。

        警告：HDU 使用 CAS SSO 统一认证，直接 POST 到图书馆
        login 端点会失败。此方法仅作保留参考。

        Parameters
        ----------
        username : str, optional
            学号 / 登录名。若为 None 则从 config 读取。
        password : str, optional
            密码。若为 None 则从 config 读取。
        org_id : str, optional
            机构 ID。默认 "104"（HDU）。

        Returns
        -------
        bool
            登录是否成功（CAS SSO 下始终返回 False）。
        """
        uname = username or self._client._settings.auth.login_name
        pwd = password or self._client._settings.auth.password
        oid = org_id or self._client._settings.auth.org_id

        if not uname or not pwd:
            error_tracker.record(
                ErrorCategory.AUTH,
                "登录名或密码未提供",
                module=__name__,
            )
            raise E.LoginError("登录名或密码未提供")

        url = self._client._settings.api.login
        resp = self._client._request(
            "POST",
            url,
            {
                "login_name": uname,
                "password": pwd,
                "org_id": oid,
            },
        )

        if resp.get("CODE") == "ok":
            data = resp.get("DATA", resp)
            self._client.uid = str(data.get("uid", ""))
            ui = data.get("user_info") or {}
            self._client.name = str(ui.get("name") or data.get("name") or "")
            return True
        return False


def sso_browser_login(
    client: Any,
    username: str,
    password: str,
    org_id: str = "104",
) -> bool:
    """使用 Playwright 浏览器自动化完成 CAS SSO 登录（保留参考）。

    通过打开无头浏览器，填写 CAS 登录表单并提交，完成 SSO
    认证后将 Cookie 注入 client session。

    警告：HDU CAS 可能要求 CAPTCHA 验证码，此时此函数
    无法完成登录。仅作保留参考，不纳入主流程。

    Parameters
    ----------
    client : HduLibraryClient
        目标客户端实例，登录成功后 Cookie 会注入其 session。
    username : str
        学号 / 登录名。
    password : str
        密码。
    org_id : str
        机构 ID（默认 "104"）。

    Returns
    -------
    bool
        登录是否成功。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                "https://sso.hdu.edu.cn/login"
                "?service=https://hdu.huitu.zhishulib.com/"
                "User/Index/hduCASLogin",
                timeout=30000,
            )
            page.get_by_placeholder("请输入学工号/绑定手机/证件号").fill(username)
            page.get_by_placeholder("请输入密码").fill(password)
            page.get_by_role("button", name="登 录").click()

            page.wait_for_url(
                lambda url: urlparse(url).hostname == "hdu.huitu.zhishulib.com",
                timeout=15000,
            )

            cookies = page.context.cookies()
            browser.close()

            for c in cookies:
                if "zhishulib.com" in c.get("domain", ""):
                    client.session.cookies.set(
                        c["name"],
                        c["value"],
                        domain=c.get("domain", ""),
                        path=c.get("path", "/"),
                    )
            client.resolve_uid()
            return bool(client.uid)
    except Exception:
        return False
