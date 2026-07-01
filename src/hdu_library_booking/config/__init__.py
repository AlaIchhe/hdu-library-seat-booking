"""配置管理 — Settings、YAML 读写、向后兼容解析器."""

from hdu_library_booking.config.parser import ConfigParser
from hdu_library_booking.config.settings import (
    APIUrls,
    AuthConfig,
    BookingConfig,
    HTTPConfig,
    LoggingConfig,
    ResilienceConfig,
    Settings,
    StrategyConfig,
    _deep_update,
    _flatten_yaml,
    _unflatten_keys,
    get_settings,
)
from hdu_library_booking.config.yaml import (
    create_default_config,
    load_yaml_config,
    save_yaml_config,
)

__all__ = [
    "APIUrls",
    "AuthConfig",
    "BookingConfig",
    "ConfigParser",
    "HTTPConfig",
    "LoggingConfig",
    "ResilienceConfig",
    "Settings",
    "StrategyConfig",
    "_deep_update",
    "_flatten_yaml",
    "_unflatten_keys",
    "create_default_config",
    "get_settings",
    "load_yaml_config",
    "save_yaml_config",
]
