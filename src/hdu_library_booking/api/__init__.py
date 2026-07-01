"""API 客户端 — 慧图图书馆预约平台统一 HTTP 接口."""

from hdu_library_booking.api.client import HduLibraryClient
from hdu_library_booking.api.password_auth import PasswordAuthClient, sso_browser_login
from hdu_library_booking.api.room_cache import RoomCache

__all__ = [
    "HduLibraryClient",
    "PasswordAuthClient",
    "RoomCache",
    "sso_browser_login",
]
