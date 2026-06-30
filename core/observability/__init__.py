"""可观测性模块 — 结构化日志、指标、关联追踪。

提供统一的可观测性接口：
  - logging: configure_logging / get_logger — 结构化日志
  - metrics: MetricsCollector / ErrorTracker — 错误计数 + 性能指标
  - correlation: set_correlation_id / get_correlation_id — 请求链路追踪

用法
----
from core.observability import configure_logging, get_logger, set_correlation_id

configure_logging(level="INFO")
logger = get_logger(__name__)

with set_correlation_id():
    logger.info("booking_started", plan="1:1558:296:13:9")
"""

from .correlation import (
    clear_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from .logging import (
    configure_from_config,
    configure_logging,
    get_logger,
)
from .metrics import (
    MetricsCollector,
    metrics_collector,
)

__all__ = [
    # Metrics
    "MetricsCollector",
    "clear_correlation_id",
    "configure_from_config",
    # Logging
    "configure_logging",
    "get_correlation_id",
    "get_logger",
    "metrics_collector",
    # Correlation
    "set_correlation_id",
]
