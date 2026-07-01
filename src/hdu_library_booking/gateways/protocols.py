"""基础设施层抽象协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from ..types import FloorInfo, RoomDetail, RoomItem, SeatPair


class Instrumentation(Protocol):
    """可观测性接口 — 用于替代直接引用 error_tracker 单例。

    ErrorTracker 已经满足此协议，无需修改。
    """

    def record(
        self,
        category: str,
        message: str,
        exc: Exception | None = None,
        module: str = "",
    ) -> None: ...

    @property
    def total(self) -> int: ...


class NullInstrumentation:
    """测试用的空实现 — 静默丢弃所有记录。"""

    def record(
        self,
        category: str,
        message: str,
        exc: Exception | None = None,
        module: str = "",
    ) -> None:
        pass

    @property
    def total(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# 扩展的可观测性协议 — 日志 + 指标 + 追踪
# ---------------------------------------------------------------------------


class IObservability(Protocol):
    """统一可观测性协议：错误记录 + 结构化日志 + 指标 + 关联追踪。

    此协议扩展了 Instrumentation，为应用层提供完整的可观测性能力。
    ``MetricsCollector`` 结合 ``structlog`` 可满足此协议。

    用法::

        def book_all(self, obs: IObservability, ...):
            obs.log("info", "booking_started", plan=plan.code)
            obs.metric("booking_requests_total", labels={"status": "success"})
    """

    # --- 错误记录 (继承自 Instrumentation) ---
    def record(
        self,
        category: str,
        message: str,
        exc: Exception | None = None,
        module: str = "",
    ) -> None: ...

    @property
    def total(self) -> int: ...

    # --- 结构化日志 ---
    def log(self, level: str, message: str, **kwargs: Any) -> None: ...

    # --- 指标 ---
    def metric(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        metric_type: str = "counter",
    ) -> None: ...

    # --- 关联追踪 ---
    def set_correlation(self, cid: str | None = None) -> str: ...


class NullObservability:
    """测试用的完整空实现 — 静默丢弃所有可观测性操作。

    继承 NullInstrumentation 的错误记录能力，并添加日志、指标、关联 ID 的空实现。
    """

    def record(
        self,
        category: str,
        message: str,
        exc: Exception | None = None,
        module: str = "",
    ) -> None:
        pass

    @property
    def total(self) -> int:
        return 0

    def log(self, level: str, message: str, **kwargs: Any) -> None:
        pass

    def metric(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        metric_type: str = "counter",
    ) -> None:
        pass

    def set_correlation(self, cid: str | None = None) -> str:
        return ""


class ISessionAuthenticator(ABC):
    """会话认证抽象 — Cookie 加载、UID 解析。"""

    @abstractmethod
    def set_cookie_header(self, cookie_string: str) -> None: ...

    @abstractmethod
    def set_cookies_from_json_file(self, path: str) -> None: ...

    @abstractmethod
    def validate_cookie(self) -> bool: ...

    @abstractmethod
    def resolve_uid(self) -> str: ...

    @property
    @abstractmethod
    def uid(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class ILibraryGateway(ABC):
    """图书馆 API 网关抽象 — 房间/座位/预约。"""

    @property
    @abstractmethod
    def uid(self) -> str: ...

    @abstractmethod
    def get_room_types(self) -> list[RoomItem]: ...

    @abstractmethod
    def get_room_detail(self, room_query_string: str) -> RoomDetail: ...

    @abstractmethod
    def get_seat_map(
        self,
        category_id: str,
        content_id: str,
        lookup_time: Any,
        duration_hours: int = 1,
        num: int = 1,
    ) -> list[FloorInfo]: ...

    @abstractmethod
    def find_seat_in_floors(
        self, floors: list[FloorInfo], floor_id: str | int, seat_num: str | int
    ) -> SeatPair: ...

    @abstractmethod
    def book_seat(
        self,
        seat_id: str,
        uid: str,
        begin_time: Any,
        duration_hours: int,
        is_recommend: int = 1,
        dry_run: bool = False,
    ) -> dict[str, Any]: ...
