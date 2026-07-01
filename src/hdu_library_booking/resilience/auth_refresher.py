"""认证刷新 — Cookie 过期时自动重认证。

当检测到认证相关错误时，自动执行重认证并重试操作。
支持自定义重认证策略。

用法
----
from core.resilience import with_reauth, ReauthStrategy

class MyReauthStrategy(ReauthStrategy):
    def can_reauth(self, error: Exception) -> bool:
        return "登录" in str(error) or "过期" in str(error)

    def reauth(self) -> None:
        # 重新加载 Cookie
        auth_service.authenticate_with_cookie(new_cookie)

@with_reauth(MyReauthStrategy(), max_reauth=1)
def book_seat():
    ...
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, Protocol

from core.exceptions import HduLibraryError
from core.observability import get_logger

logger = get_logger(__name__)


class ReauthStrategy(Protocol):
    """重认证策略协议。"""

    def can_reauth(self, error: Exception) -> bool:
        """判断错误是否可以通过重认证恢复。"""
        ...

    def reauth(self) -> None:
        """执行重认证。"""
        ...


def with_reauth(strategy: ReauthStrategy, max_reauth: int = 1) -> Callable:
    """认证刷新装饰器。

    当检测到认证错误时，自动执行重认证并重试。

    Parameters
    ----------
    strategy : ReauthStrategy
        重认证策略实现。
    max_reauth : int
        最大重认证次数。

    Returns
    -------
    Callable
        装饰器函数。

    Examples
    --------
    >>> @with_reauth(my_strategy, max_reauth=2)
    ... def call_api():
    ...     return requests.get(url)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            reauth_count = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except HduLibraryError as exc:
                    if reauth_count < max_reauth and strategy.can_reauth(exc):
                        logger.info(
                            "auth_refresh_triggered",
                            attempt=reauth_count + 1,
                            max_reauth=max_reauth,
                            error=str(exc),
                        )
                        strategy.reauth()
                        reauth_count += 1
                        continue
                    raise

        return wrapper

    return decorator


def is_auth_error(error: Exception) -> bool:
    """判断错误是否为认证相关错误。

    Parameters
    ----------
    error : Exception
        要判断的异常。

    Returns
    -------
    bool
        True 表示是认证错误。
    """
    from core.exceptions import CookieError, LoginError

    if isinstance(error, (CookieError, LoginError)):
        return True

    # 检查错误消息中的关键词
    error_msg = str(error).lower()
    auth_keywords = [
        "登录",
        "认证",
        "过期",
        "无效",
        "未授权",
        "login",
        "auth",
        "expired",
        "unauthorized",
        "forbidden",
    ]
    return any(kw in error_msg for kw in auth_keywords)
