"""
方案管理服务。

提供预约方案的 CRUD、批量修改、按星期筛选等业务操作。
"""

from ..models.plan import BookingPlan, PlanStatus, Weekday
from .base import IPlanRepository


class PlanService:
    """方案 CRUD 服务 (SRP: 只负责方案的管理逻辑)。

    依赖注入 IPlanRepository，不关心底层存储细节。
    """

    def __init__(self, repository: IPlanRepository):
        self._repo = repository

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_all(self) -> list[BookingPlan]:
        """获取全部方案。"""
        return self._repo.load_all()

    def list_enabled(self) -> list[BookingPlan]:
        """获取已启用的方案。"""
        return [p for p in self._repo.load_all() if p.status == PlanStatus.ENABLED]

    def list_by_weekday(self, weekday: Weekday) -> list[BookingPlan]:
        """获取指定星期启用的方案（含 weekday=None 的通用方案）。"""
        all_plans = self.list_enabled()
        specific = [p for p in all_plans if p.weekday == weekday]
        if specific:
            return specific
        # 回落至通用方案
        return [p for p in all_plans if p.weekday is None]

    def get(self, plan_id: str) -> BookingPlan | None:
        """按 ID 获取方案。"""
        return self._repo.get(plan_id)

    # ------------------------------------------------------------------
    # 增删改
    # ------------------------------------------------------------------
    def add(self, plan: BookingPlan) -> None:
        """新增方案并持久化。"""
        errors = plan.validate()
        if errors:
            raise ValueError("方案校验失败:\n" + "\n".join(f"  - {e}" for e in errors))
        self._repo.add(plan)

    def remove(self, plan_id: str) -> bool:
        """按 ID 删除方案。"""
        return self._repo.remove(plan_id)

    def remove_many(self, plan_ids: list[str]) -> int:
        """批量删除方案，返回删除数量。"""
        count = 0
        for pid in plan_ids:
            if self._repo.remove(pid):
                count += 1
        return count

    def update(self, plan_id: str, **kwargs: object) -> BookingPlan | None:
        """更新方案字段（部分更新）。"""
        plan = self._repo.get(plan_id)
        if not plan:
            return None

        allowed = {
            "room_type",
            "floor_id",
            "seat_num",
            "start_hour",
            "duration_hours",
            "booker_name",
            "book_days",
            "status",
            "weekday",
            "tags",
        }
        for key, value in kwargs.items():
            if key in allowed and hasattr(plan, key):
                setattr(plan, key, value)

        errors = plan.validate()
        if errors:
            raise ValueError("方案校验失败:\n" + "\n".join(f"  - {e}" for e in errors))

        # replace in place
        plans = self._repo.load_all()
        for i, p in enumerate(plans):
            if p.plan_id == plan_id:
                plans[i] = plan
                break
        self._repo.save_all(plans)
        return plan

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------
    def batch_set_time(
        self,
        plan_ids: list[str],
        start_hour: int | None = None,
        duration_hours: int | None = None,
        book_days: int | None = None,
    ) -> int:
        """批量设置方案的时间参数，返回修改数量。"""
        plans = self._repo.load_all()
        modified = 0
        for p in plans:
            if p.plan_id in plan_ids:
                if start_hour is not None:
                    p.start_hour = start_hour
                if duration_hours is not None:
                    p.duration_hours = duration_hours
                if book_days is not None:
                    p.book_days = book_days
                modified += 1
        if modified > 0:
            self._repo.save_all(plans)
        return modified

    def enable_all(self) -> int:
        """启用全部方案。"""
        plans = self._repo.load_all()
        for p in plans:
            p.status = PlanStatus.ENABLED
        self._repo.save_all(plans)
        return len(plans)

    def disable_all(self) -> int:
        """禁用全部方案。"""
        plans = self._repo.load_all()
        for p in plans:
            p.status = PlanStatus.DISABLED
        self._repo.save_all(plans)
        return len(plans)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def count(self) -> int:
        return len(self._repo.load_all())

    def count_enabled(self) -> int:
        return len(self.list_enabled())
