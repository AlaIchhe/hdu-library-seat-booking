"""图书馆 API 网关 — 房间/座位/预约 API 封装。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote

from .. import constants as C
from .. import exceptions as E
from ..auth import generate_api_token
from .protocols import ILibraryGateway

if TYPE_CHECKING:
    from .protocols import Instrumentation


class HduLibraryGateway(ILibraryGateway):
    """图书馆平台 API 网关实现。

    组合 HttpTransport（网络 I/O）和 SessionAuthenticator（认证），
    提供房间查询、座位定位、预约提交等高阶 API。
    """

    def __init__(
        self,
        transport,
        settings=None,
        instrumentation: Instrumentation | None = None,
    ):
        self._transport = transport
        self._settings = settings
        self._instrumentation = instrumentation

    def _record(self, category: str, message: str, exc: Exception | None = None) -> None:
        if self._instrumentation:
            self._instrumentation.record(category, message, exc, module=__name__)

    @property
    def uid(self) -> str:
        return self._settings.auth.uid if self._settings else ""

    @property
    def urls(self) -> dict:
        if self._settings:
            return self._settings.api.model_dump()  # type: ignore[no-any-return]
        return dict(C.URLS)

    @property
    def session(self):
        return self._transport.session

    # ------------------------------------------------------------------
    # 房间查询
    # ------------------------------------------------------------------
    def get_room_types(self) -> list[dict]:
        """获取所有可用的房间类型列表。"""
        url = self.urls.get("query_rooms") or C.URLS["query_rooms"]
        data = self._transport.request("GET", url)
        raw_items = data["content"]["children"][1]["defaultItems"]
        room_items = []
        for item in raw_items:
            link_url = unquote(item["link"]["url"])
            query = link_url.split("?", 1)[1]
            room_items.append({"name": item["name"], "query": query})
        return room_items

    def get_room_detail(self, room_query_string: str) -> dict:
        """查询单个房间的详细信息。"""
        url = self.urls.get("query_seats") or C.URLS["query_seats"]
        full_url = url + "?" + room_query_string
        resp = self._transport.request("GET", full_url)
        detail = resp.get("data")
        if not detail:
            self._record("ROOM_QUERY", "房间信息为空")
            raise E.RoomQueryError("房间信息为空")
        return detail  # type: ignore[no-any-return]

    def get_seat_map(
        self,
        category_id: str,
        content_id: str,
        lookup_time,
        duration_hours: int = 1,
        num: int = 1,
    ) -> list[dict]:
        """根据分类和参考时间查询座位布局。"""
        url = self.urls.get("query_seats") or C.URLS["query_seats"]
        payload = {
            "beginTime": lookup_time.timestamp(),
            "duration": int(duration_hours * 3600),
            "num": num,
            "space_category[category_id]": str(category_id),
            "space_category[content_id]": str(content_id),
        }
        resp = self._transport.request("POST", url, payload)
        try:
            return resp["allContent"]["children"][2]["children"]["children"]  # type: ignore[no-any-return]
        except Exception as exc:
            self._record("SEAT_QUERY", f"座位分布解析失败：{exc}", exc)
            raise E.SeatQueryError(f"座位分布解析失败：{exc}") from exc

    def find_seat_in_floors(self, floors: list, floor_id, seat_num) -> tuple:
        """在楼层列表中定位指定楼层和座位号。"""
        floor_id = str(floor_id)
        seat_num = str(seat_num)
        floor_names = []

        target_floor = None
        for item in floors:
            info = item.get("seatMap", {}).get("info", {})
            floor_names.append(f"{item.get('roomName', '?')}={info.get('id', '?')}")
            if str(info.get("id")) == floor_id:
                target_floor = item
                break

        if not target_floor:
            self._record(
                "SEAT_QUERY",
                f"找不到楼层 id={floor_id}。可用：{', '.join(floor_names)}",
            )
            raise E.SeatQueryError(f"找不到楼层 id={floor_id}。可用楼层：{', '.join(floor_names)}")

        seats = target_floor["seatMap"]["POIs"]
        matches = [s for s in seats if str(s.get("title")) == seat_num]
        if not matches:
            self._record(
                "SEAT_QUERY",
                f"{target_floor.get('roomName')} 中找不到 {seat_num} 座",
            )
            raise E.SeatQueryError(f"{target_floor.get('roomName')} 中找不到 {seat_num} 座")
        if len(matches) > 1:
            self._record(
                "SEAT_QUERY",
                f"{target_floor.get('roomName')} 中存在多个 {seat_num} 座",
            )
            raise E.SeatQueryError(f"{target_floor.get('roomName')} 中存在多个 {seat_num} 座")
        return target_floor, matches[0]

    # ------------------------------------------------------------------
    # 预约
    # ------------------------------------------------------------------
    def book_seat(
        self,
        seat_id: str,
        uid: str,
        begin_time,
        duration_hours: int,
        is_recommend: int = 1,
        dry_run: bool = False,
    ) -> dict:
        """提交预约请求。"""
        begin_ts = int(begin_time.timestamp())
        duration_sec = int(duration_hours * 3600)
        uid_str = str(uid)
        seat_str = str(seat_id)

        api_token, api_time = generate_api_token(
            seat_id=seat_str,
            uid=uid_str,
            begin_time=begin_ts,
            duration=duration_sec,
            is_recommend=is_recommend,
        )

        payload = {
            "beginTime": begin_ts,
            "duration": duration_sec,
            "is_recommend": is_recommend,
            "api_time": api_time,
            "seats[0]": seat_str,
            "seatBookers[0]": uid_str,
        }

        if dry_run:
            return {"dry_run": True, "payload": payload, "api_token": api_token}

        self.session.headers["Api-Token"] = api_token
        url = self.urls.get("book_seat") or C.URLS["book_seat"]
        return self._transport.request("POST", url, payload)  # type: ignore[no-any-return]
