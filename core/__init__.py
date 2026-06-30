from .api import HduLibraryClient
from .auth import generate_api_token
from .config import create_default_config, load_yaml_config, save_yaml_config
from .config_parser import ConfigParser
from .constants import (
    DEFAULT_HEADERS,
    DEFAULT_MAX_TRIALS,
    DEFAULT_ORG_ID,
    DEFAULT_RETRY_DELAY,
    DEFAULT_SESSION_PARAMS,
    DEFAULT_TIMEOUT,
    MSG_DUPLICATE,
    MSG_INVALID_REQUEST,
    MSG_SEAT_UNAVAILABLE,
    MSG_TIME_OUT_OF_RANGE,
    ROOM_TYPE_MAP,
    URLS,
)
from .exceptions import (
    BookingCancelled,
    BookingError,
    BookingValidationError,
    CookieError,
    HduLibraryError,
    LoginError,
    RoomQueryError,
    SeatQueryError,
)
from .infrastructure.http_transport import HttpTransport
from .infrastructure.library_gateway import HduLibraryGateway
from .infrastructure.protocols import (
    ILibraryGateway,
    Instrumentation,
    IObservability,
    ISessionAuthenticator,
    NullInstrumentation,
    NullObservability,
)
from .infrastructure.session_auth import SessionAuthenticator
from .metrics import ErrorCategory, ErrorRecord, ErrorTracker, error_tracker
from .observability import (
    MetricsCollector,
    configure_from_config,
    configure_logging,
    get_correlation_id,
    get_logger,
    metrics_collector,
    set_correlation_id,
)
from .room_cache import RoomCache
from .settings import Settings, get_settings

__all__ = [
    "DEFAULT_HEADERS",
    "DEFAULT_MAX_TRIALS",
    "DEFAULT_ORG_ID",
    "DEFAULT_RETRY_DELAY",
    "DEFAULT_SESSION_PARAMS",
    "DEFAULT_TIMEOUT",
    "MSG_DUPLICATE",
    "MSG_INVALID_REQUEST",
    "MSG_SEAT_UNAVAILABLE",
    "MSG_TIME_OUT_OF_RANGE",
    "ROOM_TYPE_MAP",
    "URLS",
    "BookingCancelled",
    "BookingError",
    "BookingValidationError",
    "ConfigParser",
    "CookieError",
    "ErrorCategory",
    "ErrorRecord",
    "ErrorTracker",
    "HduLibraryClient",
    "HduLibraryError",
    "HduLibraryGateway",
    "HttpTransport",
    "ILibraryGateway",
    "IObservability",
    "ISessionAuthenticator",
    "Instrumentation",
    "LoginError",
    "MetricsCollector",
    "NullInstrumentation",
    "NullObservability",
    "RoomCache",
    "RoomQueryError",
    "SeatQueryError",
    "SessionAuthenticator",
    "Settings",
    "configure_from_config",
    "configure_logging",
    "create_default_config",
    "error_tracker",
    "generate_api_token",
    "get_correlation_id",
    "get_logger",
    "get_settings",
    "load_yaml_config",
    "metrics_collector",
    "save_yaml_config",
    "set_correlation_id",
]
