"""熔断器 — 防止持续故障时无限重试。

实现经典的三态熔断器模式：
  - CLOSED: 正常放行所有请求
  - OPEN: 拒绝所有请求，等待恢复
  - HALF_OPEN: 允许一次试探请求

状态转换：
  CLOSED → (连续 failure_threshold 次失败) → OPEN
  OPEN → (recovery_timeout 秒后) → HALF_OPEN
  HALF_OPEN → (成功) → CLOSED
  HALF_OPEN → (失败) → OPEN

用法
----
from core.resilience import CircuitBreaker

cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

# 方式 1: 手动检查
if cb.can_execute():
    try:
        result = api_call()
        cb.record_success()
    except Exception:
        cb.record_failure()
        raise

# 方式 2: 装饰器
@cb
def api_call():
    ...
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from core.observability import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """熔断器状态。"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """熔断器打开时抛出的异常。"""

    pass


class CircuitBreaker:
    """线程安全的熔断器。

    通过跟踪连续失败次数，在达到阈值时"熔断"（拒绝调用），
    经过恢复时间后进入半开状态，允许一次试探。

    Parameters
    ----------
    failure_threshold : int
        触发熔断的连续失败次数。
    recovery_timeout : float
        熔断恢复等待秒数。
    success_threshold : int
        半开状态下恢复为 CLOSED 所需的连续成功次数。

    Examples
    --------
    >>> cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
    >>> for _ in range(10):
    ...     if not cb.can_execute():
    ...         print("Circuit is open, skip")
    ...         break
    ...     try:
    ...         api_call()
    ...         cb.record_success()
    ...     except Exception:
    ...         cb.record_failure()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")

        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """当前状态（自动检查是否应从 OPEN 转为 HALF_OPEN）。"""
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and time.monotonic() - self._last_failure_time >= self._recovery_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(
                    "circuit_breaker_half_open",
                    recovery_timeout=self._recovery_timeout,
                )
            return self._state

    @property
    def failure_count(self) -> int:
        """当前连续失败次数。"""
        with self._lock:
            return self._failure_count

    def record_success(self) -> None:
        """记录一次成功调用。"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info("circuit_breaker_closed")
            else:
                self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败调用。"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_reopened",
                    failure_count=self._failure_count,
                )
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_opened",
                    failure_count=self._failure_count,
                    threshold=self._failure_threshold,
                    recovery_timeout=self._recovery_timeout,
                )

    def can_execute(self) -> bool:
        """检查是否允许执行调用。"""
        return self.state != CircuitState.OPEN

    def reset(self) -> None:
        """重置熔断器为 CLOSED 状态。"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = 0.0

    def __call__(self, func: Callable) -> Callable:
        """作为装饰器使用。

        用法::

            @CircuitBreaker(failure_threshold=3)
            def api_call():
                ...
        """

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self.can_execute():
                raise CircuitOpenError(
                    f"Circuit breaker is OPEN for {func.__name__}. "
                    f"Recovery in {self._recovery_timeout:.0f}s"
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except BaseException:
                self.record_failure()
                raise

        return wrapper

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self.state.value}, "
            f"failures={self._failure_count}/{self._failure_threshold})"
        )
