"""重试策略 — 基于 tenacity 的指数退避 + 抖动。

提供配置化的重试装饰器，特性：
  - 指数退避 + 全抖动（exponential backoff + full jitter）
  - 仅重试瞬时错误（通过 is_retryable 判断）
  - 双重停止条件：次数上限 + 总时长上限
  - 重试前日志记录
  - 重试统计信息导出

用法
----
from hdu_library_booking.resilience import make_retry_decorator

# 使用默认配置
@make_retry_decorator()
def call_api():
    ...

# 自定义配置
@make_retry_decorator(max_attempts=5, max_duration=60, initial_wait=2.0, max_wait=30.0)
def call_api():
    ...
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from tenacity import (
    RetryCallState,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
)

from .errors import is_retryable

logger = logging.getLogger(__name__)


def make_retry_decorator(
    max_attempts: int = 3,
    max_duration: float = 30.0,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
) -> Callable:
    """创建配置化的重试装饰器。

    Parameters
    ----------
    max_attempts : int
        最大尝试次数（含首次）。
    max_duration : float
        总超时秒数。
    initial_wait : float
        初始等待秒数（首次重试前）。
    max_wait : float
        最大等待秒数（上限）。

    Returns
    -------
    Callable
        可用作装饰器的 tenacity retry 对象。

    Examples
    --------
    >>> @make_retry_decorator(max_attempts=3, max_duration=30)
    ... def fetch_data(url: str) -> dict:
    ...     return httpx.get(url).json()
    """
    return retry(
        retry=retry_if_exception(is_retryable),
        stop=(stop_after_attempt(max_attempts) | stop_after_delay(max_duration)),
        wait=wait_exponential_jitter(
            initial=initial_wait,
            max=max_wait,
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def get_retry_stats(retry_state: RetryCallState) -> dict[str, Any]:
    """获取重试统计信息，用于指标上报。

    Parameters
    ----------
    retry_state : RetryCallState
        tenacity 的重试状态对象。

    Returns
    -------
    dict
        包含 attempt_number、idle_for、outcome 等字段。
    """
    outcome_str = "success"
    if retry_state.outcome is not None:
        if retry_state.outcome.failed:
            outcome_str = str(retry_state.outcome.exception())
        else:
            outcome_str = str(retry_state.outcome.result())
    return {
        "attempt_number": retry_state.attempt_number,
        "idle_for": round(retry_state.idle_for, 3) if retry_state.idle_for else 0,
        "outcome": outcome_str,
    }


# 预定义的常用重试策略


def transport_retry() -> Callable:
    """Transport 层重试策略 — 快速重试，短时间。

    用于 HTTP 请求级别的重试，特点：
    - 最多 3 次尝试
    - 总超时 10 秒
    - 初始等待 0.5 秒，最大 3 秒
    """
    return make_retry_decorator(
        max_attempts=3,
        max_duration=10.0,
        initial_wait=0.5,
        max_wait=3.0,
    )


def booking_retry() -> Callable:
    """预约提交重试策略 — 中等强度。

    用于预约提交级别的重试，特点：
    - 最多 3 次尝试
    - 总超时 30 秒
    - 初始等待 1 秒，最大 10 秒
    """
    return make_retry_decorator(
        max_attempts=3,
        max_duration=30.0,
        initial_wait=1.0,
        max_wait=10.0,
    )


def auth_retry() -> Callable:
    """认证重试策略 — 保守重试。

    用于认证相关操作，特点：
    - 最多 2 次尝试
    - 总超时 10 秒
    - 初始等待 1 秒，最大 5 秒
    """
    return make_retry_decorator(
        max_attempts=2,
        max_duration=10.0,
        initial_wait=1.0,
        max_wait=5.0,
    )
