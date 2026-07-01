"""网关 — HTTP 传输、图书馆 API、会话认证、用户信息解析."""

from hdu_library_booking.gateways.http_transport import HttpTransport
from hdu_library_booking.gateways.library import HduLibraryGateway
from hdu_library_booking.gateways.protocols import (
    ILibraryGateway,
    Instrumentation,
    ISessionAuthenticator,
    NullInstrumentation,
)
from hdu_library_booking.gateways.session_auth import SessionAuthenticator
from hdu_library_booking.gateways.user_info import find_user_info

__all__ = [
    "HduLibraryGateway",
    "HttpTransport",
    "ILibraryGateway",
    "ISessionAuthenticator",
    "Instrumentation",
    "NullInstrumentation",
    "SessionAuthenticator",
    "find_user_info",
]
