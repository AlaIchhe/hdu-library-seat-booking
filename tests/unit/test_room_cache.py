"""Tests for hdu_library_booking.api.room_cache — RoomCache."""

from unittest.mock import MagicMock

import pytest

from hdu_library_booking.api.room_cache import RoomCache
from hdu_library_booking.exceptions import SeatQueryError


class TestRoomCache:
    def make_client(self):
        client = MagicMock()
        client.get_room_types.return_value = [
            {
                "name": "自习室",
                "query": "space_category[category_id]=10&space_category[content_id]=20",
            },
            {
                "name": "阅览室",
                "query": "space_category[category_id]=30&space_category[content_id]=40",
            },
        ]
        client.get_room_detail.side_effect = lambda q: {
            "space_category[category_id]=10&space_category[content_id]=20": {
                "space_category": {"category_id": "10", "content_id": "20"}
            },
            "space_category[category_id]=30&space_category[content_id]=40": {
                "space_category": {"category_id": "30", "content_id": "40"}
            },
        }[q]
        client.get_seat_map.return_value = [
            {
                "roomName": "3楼",
                "seatMap": {
                    "info": {"id": "1558"},
                    "POIs": [{"title": "296", "id": "seat_296"}],
                },
            },
        ]
        return client

    def test_query_rooms(self):
        client = self.make_client()
        cache = RoomCache(client, delay=0)
        rooms = cache.query_rooms()
        assert len(rooms) == 2
        assert "自习室" in rooms
        assert "阅览室" in rooms
        assert "space_category" in rooms["自习室"]

    def test_query_seats(self):
        client = self.make_client()
        cache = RoomCache(client, delay=0)
        rooms = cache.query_rooms()
        result = cache.query_seats(rooms)
        assert result is not None
        assert "floors" in result["自习室"]
        assert "3楼" in result["自习室"]["floors"]
        assert "seats" in result["自习室"]["floors"]["3楼"]

    def test_update_rooms(self):
        client = self.make_client()
        cache = RoomCache(client, delay=0)
        room_names = cache.update_rooms()
        assert len(room_names) == 2
        assert cache.rooms is not None

    def test_get_floor_names(self):
        client = self.make_client()
        cache = RoomCache(client, delay=0)
        cache.update_rooms()
        floors = cache.get_floor_names("自习室")
        assert "3楼" in floors

    def test_get_seats(self):
        client = self.make_client()
        cache = RoomCache(client, delay=0)
        cache.update_rooms()
        seats = cache.get_seats("自习室", "3楼")
        assert len(seats) == 1
        assert seats[0]["title"] == "296"

    def test_cancel_flag_stops_query_seats(self):
        client = self.make_client()
        cache = RoomCache(client, delay=0)
        rooms = cache.query_rooms()

        def cancel():
            return True

        result = cache.query_seats(rooms, cancel_flag=cancel)
        assert result is None

    def test_re_query_on_error(self):
        client = self.make_client()
        # 首次 get_seat_map 失败，应触发重新查询
        client.get_seat_map.side_effect = [
            SeatQueryError("查询失败"),  # 第一次失败 → 触发 re_query
            # re_query 调用 query_rooms 时需要 get_room_detail
        ]
        # 重新 query_rooms 时 get_room_types 返回相同数据
        # 但 query_seats 中第二次不会再调用 get_seat_map（因为 re_query 直接返回 query_rooms 结果）

        cache = RoomCache(client, delay=0)
        rooms = cache.query_rooms()
        result = cache.query_seats(rooms, re_query_on_error=True)
        # 应该返回重新查询的结果
        assert result is not None

    def test_build_plan(self):
        from datetime import datetime

        plan = RoomCache.build_plan(
            room_name="自习室",
            begin_time=datetime(2026, 7, 1, 13, 0, 0),
            duration=3600,
            seats_info=[{"title": "296"}],
            seat_bookers=["12345"],
        )
        assert plan["roomName"] == "自习室"
        assert plan["duration"] == 3600
        assert len(plan["seatsInfo"]) == 1
        assert len(plan["seatBookers"]) == 1

    def test_query_seats_seat_map_error_without_re_query(self):
        """re_query_on_error=False 时，错误应向上传播。"""
        client = self.make_client()
        client.get_seat_map.side_effect = SeatQueryError("查询失败")

        cache = RoomCache(client, delay=0)
        rooms = cache.query_rooms()

        with pytest.raises(SeatQueryError):
            cache.query_seats(rooms, re_query_on_error=False)
