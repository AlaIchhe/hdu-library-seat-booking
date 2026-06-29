"""
RoomCache — 房间/座位缓存和批量查询。

提取 Master（utils/master.py）和 Killer（utils/killer.py）中完全重复的：
  - 房间类型 + 详情批量查询
  - 座位布局批量查询
  - 楼层/座位信息访问
  - 预约计划构建
"""

from time import sleep

from .utils import get_seat_lookup_time


class RoomCache:
    """共享房间缓存 — 封装 Master 和 Killer 共用的批量查询与数据访问逻辑。

    使用方法
    --------
    cache = RoomCache(client, delay=2)
    room_names = cache.update_rooms()
    floors = cache.get_floor_names("自习室")
    seats = cache.get_seats("自习室", "2楼")
    plan = cache.build_plan("自习室", begin_time, 3, seats_info, seat_bookers)
    """

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
        替代各项目中直接操作 session 的重复代码。

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

    def query_seats(self, rooms=None, cancel_flag=None,
                    re_query_on_error=False):
        """对每个房间查询座位布局，填充 floors 和 seats 字段。

        参数
        ----------
        rooms : dict, optional
            要查询的房间字典。若为 None，使用 self.rooms。
        cancel_flag : callable, optional
            若提供，每次循环前调用；返回 True 时中止查询。
        re_query_on_error : bool, optional
            若为 True，查询失败时自动重新查询房间列表。
            默认 False（Killer 行为）。Master 使用 True。

        返回
        -------
        dict or None
            更新后的 rooms 字典。若 cancel_flag 触发则返回 None。
        """
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
                floors = self.client.get_seat_map(
                    cat_id, con_id, lookup_time, 1, 1
                )
            except Exception:
                if re_query_on_error:
                    rooms = self.query_rooms()
                    return rooms
                raise

            rooms[room_name]["floors"] = {
                f["roomName"]: f for f in floors
            }

            for floor_name in list(rooms[room_name]["floors"].keys()):
                rooms[room_name]["floors"][floor_name]["seats"] = (
                    rooms[room_name]["floors"][floor_name]["seatMap"]["POIs"]
                )

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
        """构建预约计划字典 — Master 和 Killer 使用完全相同的结构。

        参数
        ----------
        room_name : str
            房间名称。
        begin_time : datetime
            预约开始时间。
        duration : int
            预约时长（小时）。
        seats_info : list[dict]
            座位信息列表，每个元素包含 roomName, floorName, seatId, seatNum 等。
        seat_bookers : list or tuple
            预约人 UID 列表。

        返回
        -------
        dict
            标准化的预约计划字典。
        """
        return {
            "roomName": room_name,
            "beginTime": begin_time,
            "duration": duration,
            "seatsInfo": list(seats_info),
            "seatBookers": list(seat_bookers),
        }
