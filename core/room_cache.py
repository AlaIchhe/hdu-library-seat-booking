from time import sleep

from .metrics import ErrorCategory, error_tracker
from .utils import get_seat_lookup_time


class RoomCache:
    def __init__(self, client, delay=2):
        """初始化房间缓存。

        参数
        ----------
        client : HduLibraryClient
            已初始化的 API 客户端实例。
        delay : int or float
            批量查询时每次请求之间的间隔秒数。默认 2。
        """
        self.client = client
        self.delay = delay
        self.rooms = None

    # ------------------------------------------------------------------
    # 批量查询
    # ------------------------------------------------------------------
    def query_rooms(self):
        """获取所有房间类型及其详情，构建 rooms 缓存字典。

        使用 HduLibraryClient.get_room_types() 和 get_room_detail()，

        返回
        -------
        dict
            {房间名: 房间详情 dict} 的映射。
        """
        rooms = {}
        for item in self.client.get_room_types():
            rooms[item["name"]] = self.client.get_room_detail(item["query"])
            sleep(self.delay)
        return rooms

    def query_seats(self, rooms=None, cancel_flag=None, re_query_on_error=False):

        if rooms is None:
            rooms = self.rooms

        lookup_time = get_seat_lookup_time()

        for room_name in list(rooms.keys()):
            if cancel_flag and cancel_flag():
                return None

            detail = rooms[room_name]
            cat_id = detail["space_category"]["category_id"]
            con_id = detail["space_category"]["content_id"]

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

    def update_rooms(self, cancel_flag=None, re_query_on_error=False):
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
    def get_floor_names(self, room_name):
        """获取指定房间的所有楼层名称列表。"""
        return list(self.rooms[room_name]["floors"].keys())

    def get_seats(self, room_name, floor_name):
        """获取指定房间和楼层的座位列表。"""
        return self.rooms[room_name]["floors"][floor_name]["seats"]

    # ------------------------------------------------------------------
    # 计划构建
    # ------------------------------------------------------------------
    @staticmethod
    def build_plan(room_name, begin_time, duration, seats_info, seat_bookers):

        return {
            "roomName": room_name,
            "beginTime": begin_time,
            "duration": duration,
            "seatsInfo": list(seats_info),
            "seatBookers": list(seat_bookers),
        }
