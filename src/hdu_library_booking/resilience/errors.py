"""错误分类 — 区分瞬时故障与永久故障。

重试策略的核心原则：只重试瞬时错误，不重试永久错误。

瞬时错误（可重试）：
  - 网络连接失败、超时
  - 服务端临时故障（HTTP 5xx）
  - DNS 解析失败

永久错误（不可重试）：
  - 认证失败（Cookie 过期、登录失败）
  - 参数校验错误（时间范围、座位号）
  - 用户主动取消
  - 客户端错误（HTTP 4xx，除了 429）
"""

from __future__ import annotations

from core.exceptions import (
    BookingCancelled,
    BookingValidationError,
    CookieError,
    HduLibraryError,
    LoginError,
)

# ---------------------------------------------------------------------------
# 可重试的瞬时错误
# ---------------------------------------------------------------------------

RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# ---------------------------------------------------------------------------
# 不可重试的永久错误
# ---------------------------------------------------------------------------

NON_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    LoginError,
    CookieError,
    BookingValidationError,
    BookingCancelled,
)

# HTTP 状态码分类
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
NON_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset(
    {
        400,
        401,
        403,
        404,
        405,
        406,
        407,
        408,
        409,
        410,
        411,
        412,
        413,
        414,
        415,
        416,
        417,
        418,
        422,
        425,
        426,
        431,
        451,
    }
)
SUCCESS_STATUS_CODES: frozenset[int] = frozenset({200, 302})


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试。

    规则
    ----
    - 永久错误（认证、参数校验、用户取消）→ 不可重试
    - 瞬时错误（网络、超时、OS）→ 可重试
    - HduLibraryError 需根据 cause 判断：
      - cause 是网络错误 → 可重试
      - 其他 → 不可重试（保守策略）

    Parameters
    ----------
    exc : BaseException
        要判断的异常。

    Returns
    -------
    bool
        True 表示可重试。
    """
    # 永久错误 → 不可重试
    if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
        return False

    # 明确的瞬时错误 → 可重试
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True

    # HduLibraryError 包装的异常 → 检查 cause
    if isinstance(exc, HduLibraryError) and exc.__cause__:
        return isinstance(exc.__cause__, RETRYABLE_EXCEPTIONS)

    # 默认：不可重试（保守策略，避免无意义重试）
    return False


def classify_http_status(status_code: int) -> str:
    """HTTP 状态码分类。

    Parameters
    ----------
    status_code : int
        HTTP 状态码。

    Returns
    -------
    str
        ``"success"`` — 200, 302
        ``"retryable"`` — 429, 500, 502, 503, 504
        ``"non_retryable"`` — 其他 4xx
    """
    if status_code in SUCCESS_STATUS_CODES:
        return "success"
    if status_code in RETRYABLE_STATUS_CODES:
        return "retryable"
    return "non_retryable"


def is_retryable_status(status_code: int) -> bool:
    """判断 HTTP 状态码是否可重试。

    Parameters
    ----------
    status_code : int
        HTTP 状态码。

    Returns
    -------
    bool
        True 表示可重试。
    """
    return status_code in RETRYABLE_STATUS_CODES
