"""共享 pytest fixtures。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.plan import BookingPlan, PlanStatus, Weekday
from app.services.booking_service import BookingOrchestrator
from app.services.notification_service import ConsoleNotification
from app.strategies.fixed_seat import FixedSeatStrategy
from core import HduLibraryClient
from core.infrastructure.protocols import NullInstrumentation

# ============================================================================
# 领域对象 fixtures
# ============================================================================


@pytest.fixture
def sample_plan() -> BookingPlan:
    """创建一个标准的测试方案。"""
    return BookingPlan(
        room_type=1,
        floor_id=1558,
        seat_num="296",
        start_hour=13,
        duration_hours=9,
        booker_name="测试用户",
        book_days=1,
        weekday=Weekday.MONDAY,
        status=PlanStatus.ENABLED,
        tags=["test"],
    )


@pytest.fixture
def minimal_plan() -> BookingPlan:
    """创建一个最小化的测试方案。"""
    return BookingPlan(
        room_type=1,
        floor_id=1558,
        seat_num="296",
        start_hour=13,
        duration_hours=1,
    )


# ============================================================================
# Mock client / gateway fixtures
# ============================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """创建一个 mock HduLibraryClient。"""
    return MagicMock(spec=HduLibraryClient)


@pytest.fixture
def mock_transport() -> MagicMock:
    """创建一个 mock HttpTransport。"""
    transport = MagicMock()
    transport.config = {}
    transport.session = MagicMock()
    transport.request = MagicMock(return_value={})
    return transport


@pytest.fixture
def null_instrumentation() -> NullInstrumentation:
    """创建一个 NullInstrumentation 实例。"""
    return NullInstrumentation()


# ============================================================================
# 编排器 fixtures
# ============================================================================


@pytest.fixture
def mock_orchestrator(mock_client) -> BookingOrchestrator:
    """创建一个使用 mock client 的 BookingOrchestrator。"""
    return BookingOrchestrator(
        gateway=mock_client,
        strategy=FixedSeatStrategy(),
        notifier=ConsoleNotification(use_colors=False),
    )


# ============================================================================
# 时间 fixtures
# ============================================================================


@pytest.fixture
def fixed_time():
    """固定 now_cst() 返回值。"""
    fixed = datetime(2026, 7, 15, 10, 30, 0)
    with patch("core.domain.time.now_cst", return_value=fixed):
        yield fixed
