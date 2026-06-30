"""线程安全的取消令牌。

提供比 ``app.services.base.CancellationToken`` 更健壮的实现：
  - 基于 ``threading.Event``，天然线程安全
  - 支持注册取消回调
  - 支持等待取消信号（带超时）

保留 ``app.services.base.CancellationToken`` 作为兼容别名。

用法
----
from core.resilience import CancellationToken

token = CancellationToken()

# 检查是否已取消
if token.is_cancelled():
    break

# 注册取消回调
token.register_callback(lambda: print("Cancelled!"))

# 等待取消信号（带超时）
token.wait(timeout=1.0)
"""

from __future__ import annotations

import threading
from collections.abc import Callable


class CancellationToken:
    """线程安全的取消令牌。

    基于 ``threading.Event`` 实现，所有操作天然线程安全。
    支持注册取消回调，在取消时自动执行。

    Attributes
    ----------
    _event : threading.Event
        内部事件对象，取消时 set。
    _callbacks : list[Callable[[], None]]
        取消时执行的回调列表。
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    def is_cancelled(self) -> bool:
        """检查是否已取消。

        Returns
        -------
        bool
            True 表示已取消。
        """
        return self._event.is_set()

    def cancel(self) -> None:
        """请求取消，并执行所有已注册的回调。"""
        self._event.set()
        with self._lock:
            for cb in self._callbacks:
                try:
                    cb()
                except Exception:
                    # 回调异常不应影响取消操作
                    pass

    def register_callback(self, callback: Callable[[], None]) -> None:
        """注册取消回调。

        回调在 ``cancel()`` 调用时执行。如果已经取消，
        回调会立即执行。

        Parameters
        ----------
        callback : Callable[[], None]
            取消时执行的回调函数。
        """
        with self._lock:
            self._callbacks.append(callback)
            # 如果已经取消，立即执行
            if self._event.is_set():
                try:
                    callback()
                except Exception:
                    pass

    def wait(self, timeout: float | None = None) -> bool:
        """等待取消信号。

        Parameters
        ----------
        timeout : float, optional
            超时秒数；None 表示无限等待。

        Returns
        -------
        bool
            True 表示收到取消信号，False 表示超时。
        """
        return self._event.wait(timeout)

    def __repr__(self) -> str:
        return f"CancellationToken(cancelled={self.is_cancelled()})"
