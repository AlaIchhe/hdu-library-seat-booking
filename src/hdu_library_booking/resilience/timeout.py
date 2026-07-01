"""超时配置 — 连接/读取分离 + 整体墙钟超时。

提供三层超时控制：
  - connect_timeout: TCP 连接建立超时
  - read_timeout: 等待响应数据超时
  - overall_timeout: 整个操作的墙钟超时

用法
----
from hdu_library_booking.resilience import TimeoutConfig, deadline

# 配置超时
timeout = TimeoutConfig(connect_timeout=5.0, read_timeout=10.0)

# 作为 requests 参数
resp = requests.get(url, timeout=timeout.as_tuple)

# 墙钟超时
with deadline(30.0):
    book_all(plans)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager


class TimeoutConfig:
    """超时配置模型。

    Attributes
    ----------
    connect_timeout : float
        TCP 连接建立超时秒数。
    read_timeout : float
        等待响应数据超时秒数。
    overall_timeout : float | None
        整体墙钟超时秒数；None 表示无限制。
    """

    def __init__(
        self,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        overall_timeout: float | None = 300.0,
    ):
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.overall_timeout = overall_timeout

    @property
    def as_tuple(self) -> tuple[float, float]:
        """返回 ``(connect, read)`` 元组，用于 requests 的 timeout 参数。"""
        return (self.connect_timeout, self.read_timeout)

    def __repr__(self) -> str:
        return (
            f"TimeoutConfig(connect={self.connect_timeout}s, "
            f"read={self.read_timeout}s, "
            f"overall={self.overall_timeout}s)"
        )


@contextmanager
def deadline(timeout: float) -> Iterator[None]:
    """墙钟超时上下文管理器。

    超时后抛出 ``TimeoutError``。使用后台计时器实现，
    不会阻塞主线程的执行，但会在退出时检查是否超时。

    Parameters
    ----------
    timeout : float
        超时秒数。

    Raises
    ------
    TimeoutError
        超过指定时间后抛出。

    Examples
    --------
    >>> with deadline(30.0):
    ...     result = book_all(plans)
    """
    timed_out = threading.Event()
    timer: threading.Timer | None = None

    def _timeout_handler() -> None:
        timed_out.set()

    timer = threading.Timer(timeout, _timeout_handler)
    timer.daemon = True
    timer.start()

    try:
        yield
        if timed_out.is_set():
            raise TimeoutError(f"Operation exceeded deadline of {timeout}s")
    finally:
        timer.cancel()


class Deadline:
    """可检查的墙钟超时对象。

    与 ``deadline()`` 上下文管理器不同，``Deadline`` 可以在循环中
    反复检查剩余时间，适用于需要分段检查的场景。

    Examples
    --------
    >>> dl = Deadline(30.0)
    >>> while not dl.is_expired:
    ...     do_work()
    ...     time.sleep(1)
    """

    def __init__(self, timeout: float):
        self._deadline = time.monotonic() + timeout
        self._timeout = timeout

    @property
    def is_expired(self) -> bool:
        """是否已超时。"""
        return time.monotonic() >= self._deadline

    @property
    def remaining(self) -> float:
        """剩余秒数；已超时返回 0。"""
        return max(0.0, self._deadline - time.monotonic())

    def check(self) -> None:
        """检查是否超时，超时则抛出 TimeoutError。"""
        if self.is_expired:
            raise TimeoutError(f"Deadline exceeded ({self._timeout}s)")

    def __repr__(self) -> str:
        return f"Deadline(remaining={self.remaining:.1f}s / {self._timeout}s)"
