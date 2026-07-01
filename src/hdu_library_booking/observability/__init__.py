"""可观测性 — 结构化日志、指标收集、关联 ID 追踪."""

from hdu_library_booking.observability._error_tracker import (
    ErrorCategory,
    ErrorRecord,
    ErrorTracker,
    error_tracker,
)
from hdu_library_booking.observability.correlation import (
    clear_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from hdu_library_booking.observability.logging import (
    configure_from_config,
    configure_logging,
    get_logger,
)
from hdu_library_booking.observability.metrics import (
    MetricsCollector,
    metrics_collector,
)

__all__ = [
    "ErrorCategory",
    "ErrorRecord",
    "ErrorTracker",
    "MetricsCollector",
    "clear_correlation_id",
    "configure_from_config",
    "configure_logging",
    "error_tracker",
    "get_correlation_id",
    "get_logger",
    "metrics_collector",
    "set_correlation_id",
]
