"""容错 — 重试、熔断、超时、取消、认证刷新."""

from hdu_library_booking.resilience.auth_refresher import (
    ReauthStrategy,
    is_auth_error,
    with_reauth,
)
from hdu_library_booking.resilience.cancellation import CancellationToken
from hdu_library_booking.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from hdu_library_booking.resilience.errors import (
    NON_RETRYABLE_EXCEPTIONS,
    RETRYABLE_EXCEPTIONS,
    classify_http_status,
    is_retryable,
    is_retryable_status,
)
from hdu_library_booking.resilience.retry import (
    get_retry_stats,
    make_retry_decorator,
)
from hdu_library_booking.resilience.timeout import (
    Deadline,
    TimeoutConfig,
    deadline,
)

__all__ = [
    "NON_RETRYABLE_EXCEPTIONS",
    "RETRYABLE_EXCEPTIONS",
    "CancellationToken",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "Deadline",
    "ReauthStrategy",
    "TimeoutConfig",
    "classify_http_status",
    "deadline",
    "get_retry_stats",
    "is_auth_error",
    "is_retryable",
    "is_retryable_status",
    "make_retry_decorator",
    "with_reauth",
]
