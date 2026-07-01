"""共享类型别名、TypedDict 与泛型 — 统一 API 边界的类型命名。

慧图平台返回的 JSON 结构是外部不可控的，因此使用 TypeAlias 为常见的
字典形状赋予有意义的名称，提升代码可读性，同时保留 ``Any`` 的灵活性。

对于形状稳定、由内部构造或高频使用的实体，使用 TypedDict 提供字段名
检查；对于嵌套复杂或易变的 API 响应，保留 TypeAlias。
"""

from typing import Any, Generic, TypeAlias, TypedDict, TypeVar

# ---------------------------------------------------------------------------
# 泛型 — Result[T, E]
# ---------------------------------------------------------------------------
T = TypeVar("T")
E = TypeVar("E")


class Result(Generic[T, E]):
    """显式成功/错误包装，替代 ``None`` 返回或异常驱动错误处理。

    用法::

        result = find_seat(...)
        if result.is_failure():
            print(result.error)
        else:
            use(result.value)
    """

    def __init__(self, value: T | None = None, error: E | None = None) -> None:
        if (value is None) == (error is None):
            raise ValueError("Result 必须恰好设置 value 或 error 之一")
        self._value = value
        self._error = error

    @property
    def is_success(self) -> bool:
        return self._error is None

    @property
    def is_failure(self) -> bool:
        return self._error is not None

    @property
    def value(self) -> T:
        """获取成功值；若为失败状态则抛出 AssertionError。"""
        assert self._error is None, "Cannot access value on a failure Result"
        return self._value  # type: ignore[return-value]

    @property
    def error(self) -> E:
        """获取错误值；若为成功状态则抛出 AssertionError。"""
        assert self._error is not None, "Cannot access error on a success Result"
        return self._error

    def unwrap_or(self, default: T) -> T:
        """获取成功值，失败时返回默认值。"""
        if self._error is not None:
            return default
        return self._value  # type: ignore[return-value]

    @classmethod
    def success(cls, value: T) -> "Result[T, Any]":
        return cls(value=value)

    @classmethod
    def failure(cls, error: E) -> "Result[Any, E]":
        return cls(error=error)


# ---------------------------------------------------------------------------
# 通用 JSON 值
# ---------------------------------------------------------------------------
Json: TypeAlias = dict[str, Any]


# ---------------------------------------------------------------------------
# TypedDict — 形状稳定的实体
# ---------------------------------------------------------------------------
class UserInfo(TypedDict):
    """用户信息候选 — 由 ``_user_info_from_dict()`` 内部构造，形状稳定。

    所有字段均由内部逻辑保证存在，不使用 ``total=False``。
    """

    uid: str
    name: str | None
    score: int


# SeatPoi 和 RoomItem 保持 TypeAlias：它们在 API 边界大量流入 dict[str, Any]
# 消费者，使用 TypedDict 会产生不必要的类型摩擦。
SeatPoi: TypeAlias = dict[str, Any]
"""座位 POI 对象，至少包含 ``id``、``title`` 字段。"""

RoomItem: TypeAlias = dict[str, Any]
"""房间类型条目，包含 ``name``、``query`` 字段。"""


# ---------------------------------------------------------------------------
# TypeAlias — 嵌套复杂或易变的 API 响应
# ---------------------------------------------------------------------------
FloorInfo: TypeAlias = dict[str, Any]
"""楼层对象，包含 ``roomName``、``seatMap.info``、``seatMap.POIs`` 等字段。"""

RoomDetail: TypeAlias = dict[str, Any]
"""房间详情，包含 ``space_category``、``range`` 等字段。"""

# ---------------------------------------------------------------------------
# 复合类型
# ---------------------------------------------------------------------------
SeatPair: TypeAlias = tuple[FloorInfo, SeatPoi]
"""``find_seat_in_floors`` 返回值：(楼层对象, 座位 POI)。"""
