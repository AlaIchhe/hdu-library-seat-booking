"""容错模块 — 错误分类、重试策略、熔断器、认证刷新、超时控制。

提供项目级的容错基础设施：
  - errors: 错误分类（瞬时 vs 永久）
  - retry: 基于 tenacity 的重试策略（指数退避 + 抖动）
  - circuit_breaker: 熔断器（防止持续故障无限重试）
  - auth_refresher: 认证自动刷新
  - timeout: 超时配置（连接/读取/整体墙钟）
  - cancellation: 线程安全的取消令牌

用法
----
from core.resilience import (
    is_retryable,
    make_retry_decorator,
    CircuitBreaker,
    CancellationToken,
    TimeoutConfig,
    deadline,
)
"""

from .cancellation import CancellationToken
from .circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from .errors import (
    NON_RETRYABLE_EXCEPTIONS,
    RETRYABLE_EXCEPTIONS,
    classify_http_status,
    is_retryable,
    is_retryable_status,
)
from .retry import (
    get_retry_stats,
    make_retry_decorator,
)
from .timeout import (
    TimeoutConfig,
    deadline,
)

__all__ = [
    "NON_RETRYABLE_EXCEPTIONS",
    # Errors
    "RETRYABLE_EXCEPTIONS",
    # Cancellation
    "CancellationToken",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    # Timeout
    "TimeoutConfig",
    "classify_http_status",
    "deadline",
    "get_retry_stats",
    "is_retryable",
    "is_retryable_status",
    # Retry
    "make_retry_decorator",
]
