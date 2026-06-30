"""
按星期自动切换策略 (FR-5.2)。

用户为周一至周日分别配置不同的座位偏好，
系统自动根据目标日期是星期几选择对应配置。
"""

from datetime import timedelta
from typing import Any

from core.domain.time import now_cst

from ..models.plan import BookingPlan, Weekday
from ..services.base import ISeatSelectionStrategy


class WeekdayRotationStrategy(ISeatSelectionStrategy):
    """按星期轮换座位选择策略。

    每个 weekday 可配置独立的 floor_id、seat_num、start_hour、duration_hours。
    未配置的 weekday 自动跳过。

    Parameters
    ----------
    weekday_configs : dict[Weekday, dict]
        星期 → 配置映射。每个配置 dict 可包含：
        - floor_id (int)
        - seat_num (str)
        - start_hour (int)
        - duration_hours (int)
        - enabled (bool)
    default_config : dict, optional
        未配置星期时的默认配置。
    """

    def __init__(
        self,
        weekday_configs: dict[Weekday, dict],
        default_config: dict | None = None,
    ):
        self._configs = dict(weekday_configs)
        self._default = default_config or {}

    # ------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------
    def set_weekday(self, weekday: Weekday, **config) -> None:
        """为指定星期设置配置。"""
        self._configs[weekday] = config

    def get_weekday(self, weekday: Weekday) -> dict | None:
        """获取指定星期的配置，未配置返回 None。"""
        return self._configs.get(weekday)

    def is_enabled(self, weekday: Weekday) -> bool:
        """检查指定星期是否启用。"""
        cfg = self._configs.get(weekday)
        if cfg is None:
            return False
        return bool(cfg.get("enabled", True))

    # ------------------------------------------------------------------
    # ISeatSelectionStrategy 实现
    # ------------------------------------------------------------------
    def select_seat(self, client: Any, plan: BookingPlan, **kwargs) -> dict | None:
        """根据 plan 中的 weekday 选择对应座位。"""
        floors = kwargs.get("floors", [])

        # 确定目标星期
        weekday = plan.weekday
        if weekday is None:
            # 从 book_days 计算目标星期
            target_date = now_cst() + timedelta(days=plan.book_days)
            weekday = Weekday(target_date.weekday())

        cfg = self._configs.get(weekday, self._default)
        if not cfg or not cfg.get("enabled", True):
            return None

        # 用配置中的值覆盖 plan 的参数
        floor_id = cfg.get("floor_id", plan.floor_id)
        seat_num = cfg.get("seat_num", plan.seat_num)

        try:
            _, seat = client.find_seat_in_floors(floors, floor_id, seat_num)
            return seat  # type: ignore[no-any-return]
        except Exception:
            return None

    def describe(self, plan: BookingPlan) -> str:
        weekday = plan.weekday
        label = Weekday.label(weekday) if weekday else "?"
        cfg = self._configs.get(weekday, self._default) if weekday else self._default
        return (
            f"按星期切换 [{label}]: 楼层 {cfg.get('floor_id', '?')}, {cfg.get('seat_num', '?')} 座"
        )

    # ------------------------------------------------------------------
    # 静态工厂
    # ------------------------------------------------------------------
    @classmethod
    def from_plans(cls, plans: list[BookingPlan]) -> "WeekdayRotationStrategy":
        """从 BookingPlan 列表构建策略（每个 plan 绑定到一个 weekday）。"""
        configs = {}
        for p in plans:
            if p.weekday is not None:
                configs[p.weekday] = {
                    "floor_id": p.floor_id,
                    "seat_num": p.seat_num,
                    "start_hour": p.start_hour,
                    "duration_hours": p.duration_hours,
                    "enabled": True,
                }
        return cls(configs)
