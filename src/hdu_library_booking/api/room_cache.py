from __future__ import annotations

from collections.abc import Callable
from time import sleep
from typing import TYPE_CHECKING, Any

from hdu_library_booking.models.seat_lookup import get_seat_lookup_time
from hdu_library_booking.observability._error_tracker import ErrorCategory, error_tracker

if TYPE_CHECKING:
    from hdu_library_booking.api.client import HduLibraryClient


class RoomCache:
    def __init__(self, client: HduLibraryClient, delay: float = 2) -> None:
        """初始化房间缓存。

        Args:
            client: 已初始化的 API 客户端实例。
            delay: 批量查询时每次请求之间的间隔秒数。
        """
        self.client = client
        self.delay = delay
        self.rooms: dict[str, dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # 批量查询
    # ------------------------------------------------------------------
    def query_rooms(self) -> dict[str, dict[str, Any]]:
        """获取所有房间类型及其详情，构建 rooms 缓存字典。

        Returns:
            {房间名: 房间详情 dict} 的映射。
        """
        rooms = {}
        for item in self.client.get_room_types():
            rooms[item["name"]] = self.client.get_room_detail(item["query"])
            sleep(self.delay)
        return rooms

    def query_seats(
        self,
        rooms: dict[str, dict[str, Any]] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
        re_query_on_error: bool = False,
    ) -> dict[str, dict[str, Any]] | None:
        if rooms is None:
            rooms = self.rooms
        if rooms is None:
            return None

        lookup_time = get_seat_lookup_time()

        for room_name in list(rooms.keys()):
            if cancel_flag and cancel_flag():
                return None

            detail = rooms[room_name]
            space = detail["space_category"]
            cat_id = str(space["category_id"])
            con_id = str(space["content_id"])

            try:
                floors = self.client.get_seat_map(cat_id, con_id, lookup_time, 1, 1)
            except Exception as exc:
                error_tracker.record(
                    ErrorCategory.SEAT_QUERY,
                    f"房间缓存座位查询失败 [{room_name}]",
                    exc,
                    module=__name__,
                )
                if re_query_on_error:
                    rooms = self.query_rooms()
                    return rooms
                raise

            rooms[room_name]["floors"] = {f["roomName"]: f for f in floors}

            for floor_name in list(rooms[room_name]["floors"].keys()):
                rooms[room_name]["floors"][floor_name]["seats"] = rooms[room_name]["floors"][
                    floor_name
                ]["seatMap"]["POIs"]

            sleep(self.delay)

        return rooms

    def update_rooms(
        self,
        cancel_flag: Callable[[], bool] | None = None,
        re_query_on_error: bool = False,
    ) -> list[str]:
        """完整刷新房间缓存（房间详情 + 座位布局）。

        返回
        -------
        list[str]
            所有房间名称列表。
        """
        self.rooms = self.query_rooms()
        result = self.query_seats(
            self.rooms,
            cancel_flag=cancel_flag,
            re_query_on_error=re_query_on_error,
        )
        if result is not None:
            self.rooms = result
        return list(self.rooms.keys())

    # ------------------------------------------------------------------
    # 信息访问
    # ------------------------------------------------------------------
    def get_floor_names(self, room_name: str) -> list[str]:
        """获取指定房间的所有楼层名称列表。"""
        if not self.rooms or room_name not in self.rooms:
            return []
        room = self.rooms[room_name]
        if "floors" not in room:
            return []
        return list(room["floors"].keys())

    def get_seats(self, room_name: str, floor_name: str) -> list[dict[str, Any]]:
        """获取指定房间和楼层的座位列表。"""
        if not self.rooms or room_name not in self.rooms:
            return []
        room = self.rooms[room_name]
        if "floors" not in room or floor_name not in room["floors"]:
            return []
        return room["floors"][floor_name].get("seats", [])  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # 计划构建
    # ------------------------------------------------------------------
    @staticmethod
    def build_plan(
        room_name: str,
        begin_time: object,
        duration: int,
        seats_info: Any,
        seat_bookers: Any,
    ) -> dict[str, Any]:
        return {
            "roomName": room_name,
            "beginTime": begin_time,
            "duration": duration,
            "seatsInfo": list(seats_info),
            "seatBookers": list(seat_bookers),
        }
