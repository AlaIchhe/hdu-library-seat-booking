"""
HDU Library Common — 杭州电子科技大学图书馆预约系统共享库

提取四个项目（Instant, Master, AUTO_BOOK, Killer）的公共逻辑：
- API 客户端（会话管理、房间查询、座位查询、预约提交）
- Api-Token 签名（MD5 + Base64）
- 配置加载/保存
- 常量（URL、Headers、错误消息、房间类型）
- 公共异常类
- 时间工具函数
"""

from .api import HduLibraryClient
from .auth import generate_api_token
from .config import load_yaml_config, save_yaml_config, create_default_config
from .config_parser import ConfigParser
from .constants import (
    URLS,
    DEFAULT_HEADERS,
    DEFAULT_SESSION_PARAMS,
    ROOM_TYPE_MAP,
    MSG_TIME_OUT_OF_RANGE,
    MSG_DUPLICATE,
    MSG_SEAT_UNAVAILABLE,
    MSG_INVALID_REQUEST,
    DEFAULT_ORG_ID,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_TRIALS,
    DEFAULT_RETRY_DELAY,
)
from .exceptions import (
    HduLibraryError,
    LoginError,
    CookieError,
    RoomQueryError,
    SeatQueryError,
    BookingError,
    BookingValidationError,
    BookingCancelled,
)
from .room_cache import RoomCache

__all__ = [
    "HduLibraryClient",
    "RoomCache",
    "ConfigParser",
    "generate_api_token",
    "load_yaml_config",
    "save_yaml_config",
    "create_default_config",
    "URLS",
    "DEFAULT_HEADERS",
    "DEFAULT_SESSION_PARAMS",
    "ROOM_TYPE_MAP",
    "MSG_TIME_OUT_OF_RANGE",
    "MSG_DUPLICATE",
    "MSG_SEAT_UNAVAILABLE",
    "MSG_INVALID_REQUEST",
    "DEFAULT_ORG_ID",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_TRIALS",
    "DEFAULT_RETRY_DELAY",
    "HduLibraryError",
    "LoginError",
    "CookieError",
    "RoomQueryError",
    "SeatQueryError",
    "BookingError",
    "BookingValidationError",
    "BookingCancelled",
]
