"""
YAML 方案持久化仓库。

实现 IPlanRepository，使用 YAML 文件存储预约方案。
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hdu_library_booking.observability._error_tracker import ErrorCategory, error_tracker

from ..models.plan import BookingPlan
from .interfaces import IPlanRepository


class YamlPlanRepository(IPlanRepository):
    """基于 YAML 文件的方案仓库 (SRP: 只负责序列化/反序列化)。"""

    def __init__(self, file_path: str):
        """
        Parameters
        ----------
        file_path : str
            YAML 方案文件路径。
        """
        self._file = Path(file_path)
        self._cache: list[BookingPlan] | None = None

    # ------------------------------------------------------------------
    # IPlanRepository 实现
    # ------------------------------------------------------------------
    def load_all(self) -> list[BookingPlan]:
        """从 YAML 加载全部方案。"""
        if self._cache is not None:
            return list(self._cache)

        if not self._file.exists():
            self._cache = []
            return []

        try:
            data = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.PERSISTENCE,
                f"方案文件 YAML 解析失败: {self._file}",
                exc,
                module=__name__,
            )
            self._cache = []
            return []
        if not isinstance(data, list):
            self._cache = []
            return []

        plans = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                plans.append(BookingPlan.from_dict(item))
            except Exception:
                error_tracker.record(
                    ErrorCategory.PERSISTENCE,
                    f"方案条目反序列化失败: {item}",
                    module=__name__,
                )
                continue
        self._cache = plans
        return list(plans)

    def save_all(self, plans: list[BookingPlan]) -> None:
        """将全部方案写入 YAML。"""
        raw = [p.to_dict() for p in plans]
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                yaml.dump(raw, allow_unicode=True, encoding="utf-8").decode("utf-8"),
                encoding="utf-8",
            )
            self._cache = list(plans)
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.PERSISTENCE,
                f"方案文件写入失败: {self._file}",
                exc,
                module=__name__,
            )
            raise

    def add(self, plan: BookingPlan) -> None:
        plans = self.load_all()
        if not plan.plan_id:
            plan.plan_id = uuid.uuid4().hex[:12]
        if not plan.created_at:
            plan.created_at = datetime.now(timezone.utc).isoformat()
        plans.append(plan)
        self.save_all(plans)

    def remove(self, plan_id: str) -> bool:
        plans = self.load_all()
        before = len(plans)
        plans = [p for p in plans if p.plan_id != plan_id]
        if len(plans) < before:
            self.save_all(plans)
            return True
        return False

    def get(self, plan_id: str) -> BookingPlan | None:
        for p in self.load_all():
            if p.plan_id == plan_id:
                return p
        return None

    def invalidate_cache(self) -> None:
        """强制下次读取时重新加载文件。"""
        self._cache = None
