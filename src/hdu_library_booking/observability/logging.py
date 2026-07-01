"""结构化日志配置。

提供统一的日志初始化入口，支持开发环境（彩色文本）和生产环境（JSON）两种输出格式。

用法
----
from hdu_library_booking.observability.logging import configure_logging, get_logger

# 应用启动时调用一次
configure_logging(level="INFO", json_format=False)

# 在模块中获取 logger
logger = get_logger(__name__)
logger.info("booking_started", plan="1:1558:296:13:9", attempt=1)
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog

from hdu_library_booking.config.settings import LoggingConfig

# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def configure_logging(
    level: str = "INFO",
    log_file: str = "",
    json_format: bool = False,
) -> None:
    """配置全局结构化日志。

    在应用启动时调用一次。重复调用会覆盖之前的配置。

    Parameters
    ----------
    level : str
        日志级别 ("DEBUG" / "INFO" / "WARNING" / "ERROR")。
    log_file : str
        日志文件路径；空字符串表示仅控制台输出。
    json_format : bool
        True → JSON 格式（生产环境）；False → 彩色文本（开发环境）。
    """
    processors = _build_processors(json_format)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 同步 stdlib logging 的级别，使第三方库日志也能输出
    _configure_stdlib_logging(level, log_file)


def configure_from_config(config: LoggingConfig, json_format: bool = False) -> None:
    """从 LoggingConfig 配置日志。

    Parameters
    ----------
    config : LoggingConfig
        日志配置对象。
    json_format : bool
        是否使用 JSON 格式输出。
    """
    file = config.file if config.file != "booking.log" else ""
    configure_logging(level=config.level, log_file=file, json_format=json_format)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """获取结构化日志记录器。

    Parameters
    ----------
    name : str, optional
        模块名；为 None 时使用调用者模块名。

    Returns
    -------
    structlog.BoundLogger
        支持 ``logger.info("event", key=value)`` 形式的日志记录器。
    """
    return cast(structlog.BoundLogger, structlog.get_logger(name))


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _build_processors(json_format: bool) -> list:
    """构建 structlog 处理器链。"""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]
        )
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    return processors


def _configure_stdlib_logging(level: str, log_file: str) -> None:
    """配置根 stdlib logger，使第三方库日志也能输出。"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))

    # 清除旧 handlers，防止重复
    for h in root.handlers[:]:
        root.removeHandler(h)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    for h in handlers:
        h.setFormatter(fmt)
        root.addHandler(h)
