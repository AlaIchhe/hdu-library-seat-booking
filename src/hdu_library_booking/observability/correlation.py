"""关联 ID 管理 — 为单次预约流程提供端到端追踪能力。

关联 ID 通过 ContextVar 传播，自动绑定到 structlog 的日志输出中，
使得同一流程的所有日志共享同一个 correlation_id。

用法
----
from hdu_library_booking.observability import set_correlation_id, get_correlation_id

# 在流程入口设置
cid = set_correlation_id()  # 自动生成 UUID
# 或从外部传入：set_correlation_id("incoming-cid")

# 在任意位置获取
current = get_correlation_id()

# 作为上下文管理器使用
with set_correlation_id():
    do_booking()  # 此作用域内的所有日志自动携带 correlation_id
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import structlog

# 关联 ID 上下文变量
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


@contextmanager
def set_correlation_id(cid: str | None = None) -> Iterator[str]:
    """设置当前上下文的关联 ID，并绑定到 structlog。

    可作为上下文管理器使用，退出时自动清除。

    Parameters
    ----------
    cid : str, optional
        关联 ID；为 None 时自动生成一个短 UUID。

    Yields
    ------
    str
        设置的关联 ID。

    Examples
    --------
    >>> with set_correlation_id() as cid:
    ...     logger.info("step_started")
    ...     # 日志输出自动包含 correlation_id=cid
    """
    token = _correlation_id.set(cid or _generate_id())
    structlog.contextvars.bind_contextvars(correlation_id=_correlation_id.get())
    try:
        yield _correlation_id.get()
    finally:
        _correlation_id.reset(token)
        structlog.contextvars.unbind_contextvars("correlation_id")


def get_correlation_id() -> str:
    """获取当前上下文的关联 ID。

    Returns
    -------
    str
        当前关联 ID；未设置时返回空字符串。
    """
    return _correlation_id.get()


def clear_correlation_id() -> None:
    """清除当前上下文的关联 ID。"""
    _correlation_id.set("")
    structlog.contextvars.unbind_contextvars("correlation_id")


def _generate_id() -> str:
    """生成短关联 ID（12 位十六进制）。"""
    return uuid.uuid4().hex[:12]
