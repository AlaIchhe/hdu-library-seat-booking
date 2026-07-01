"""应用服务 — 预约编排、认证、方案管理、YAML 持久化、通知."""

from hdu_library_booking.services.auth import AuthService
from hdu_library_booking.services.booking import (
    BookingOrchestrator,
    BookingResult,
    RetryDecision,
    default_retry_decider,
)
from hdu_library_booking.services.interfaces import (
    CancellationToken,
    INotificationChannel,
    IPlanRepository,
    ISeatSelectionStrategy,
    ITaskCancellation,
    IUserInterface,
)
from hdu_library_booking.services.notifications import (
    ConsoleNotification,
    LogFileNotification,
    NotificationAggregator,
    WeChatNotification,
)
from hdu_library_booking.services.plan import PlanService
from hdu_library_booking.services.yaml_plan import YamlPlanRepository

__all__ = [
    "AuthService",
    "BookingOrchestrator",
    "BookingResult",
    "CancellationToken",
    "ConsoleNotification",
    "INotificationChannel",
    "IPlanRepository",
    "ISeatSelectionStrategy",
    "ITaskCancellation",
    "IUserInterface",
    "LogFileNotification",
    "NotificationAggregator",
    "PlanService",
    "RetryDecision",
    "WeChatNotification",
    "YamlPlanRepository",
    "default_retry_decider",
]
