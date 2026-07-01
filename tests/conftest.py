"""共享 pytest fixtures。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from hdu_library_booking.api import HduLibraryClient
from hdu_library_booking.gateways.protocols import ILibraryGateway, NullInstrumentation
from hdu_library_booking.models.plan import BookingPlan, PlanStatus, Weekday
from hdu_library_booking.services.booking import BookingOrchestrator
from hdu_library_booking.services.notifications import ConsoleNotification
from hdu_library_booking.services.plan import PlanService
from hdu_library_booking.services.yaml_plan import YamlPlanRepository
from hdu_library_booking.strategies.fixed import FixedSeatStrategy

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
def mock_gateway() -> MagicMock:
    """创建一个符合 ILibraryGateway 协议的 mock 网关。"""
    return MagicMock(spec=ILibraryGateway)


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
# 楼层数据 fixtures — 供策略测试复用
# ============================================================================


@pytest.fixture
def sample_floors() -> list[dict]:
    """创建标准的双层楼层数据。"""
    return [
        {
            "roomName": "3楼",
            "seatMap": {
                "info": {"id": "1558"},
                "POIs": [
                    {"title": "296", "id": "seat_296"},
                    {"title": "297", "id": "seat_297"},
                ],
            },
        },
        {
            "roomName": "4楼",
            "seatMap": {
                "info": {"id": "2000"},
                "POIs": [
                    {"title": "100", "id": "seat_100"},
                ],
            },
        },
    ]


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
# PlanService fixtures
# ============================================================================


@pytest.fixture
def inmemory_repo() -> YamlPlanRepository:
    """创建一个内存中的 YAML 仓库（使用临时文件）。"""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        tmp_path = tmp.name
    return YamlPlanRepository(tmp_path)


@pytest.fixture
def plan_service(inmemory_repo: YamlPlanRepository) -> PlanService:
    """创建一个绑定到内存仓库的 PlanService。"""
    return PlanService(inmemory_repo)


@pytest.fixture
def populated_service(plan_service: PlanService) -> PlanService:
    """创建一个已填充多个方案的 PlanService（供查询/批量操作测试使用）。"""
    plans = [
        BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="296",
            start_hour=13,
            duration_hours=9,
            booker_name="用户甲",
            weekday=Weekday.MONDAY,
            status=PlanStatus.ENABLED,
            tags=["安静"],
        ),
        BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="297",
            start_hour=8,
            duration_hours=4,
            booker_name="用户乙",
            weekday=Weekday.TUESDAY,
            status=PlanStatus.ENABLED,
        ),
        BookingPlan(
            room_type=2,
            floor_id=2000,
            seat_num="100",
            start_hour=10,
            duration_hours=2,
            booker_name="用户丙",
            status=PlanStatus.DISABLED,
        ),
        BookingPlan(
            room_type=1,
            floor_id=1558,
            seat_num="298",
            start_hour=18,
            duration_hours=3,
            booker_name="通用用户",
            weekday=None,  # 适用于所有天
            status=PlanStatus.ENABLED,
        ),
    ]
    for p in plans:
        plan_service.add(p)
    return plan_service


# ============================================================================
# 时间 fixtures
# ============================================================================


@pytest.fixture
def fixed_time():
    """固定 now_cst() 返回值。"""
    fixed = datetime(2026, 7, 15, 10, 30, 0)
    with patch("hdu_library_booking.models.time_utils.now_cst", return_value=fixed):
        yield fixed
