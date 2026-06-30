"""基础设施层抽象协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


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
    def get_room_types(self) -> list[dict]: ...

    @abstractmethod
    def get_room_detail(self, room_query_string: str) -> dict: ...

    @abstractmethod
    def get_seat_map(
        self,
        category_id: str,
        content_id: str,
        lookup_time,
        duration_hours: int = 1,
        num: int = 1,
    ) -> list[dict]: ...

    @abstractmethod
    def find_seat_in_floors(self, floors: list, floor_id, seat_num) -> tuple: ...

    @abstractmethod
    def book_seat(
        self,
        seat_id: str,
        uid: str,
        begin_time,
        duration_hours: int,
        is_recommend: int = 1,
        dry_run: bool = False,
    ) -> dict: ...
