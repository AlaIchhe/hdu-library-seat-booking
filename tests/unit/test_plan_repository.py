"""Tests for hdu_library_booking.services.yaml_plan — YamlPlanRepository."""

import os
import tempfile

import pytest
import yaml

from hdu_library_booking.models.plan import BookingPlan, PlanStatus
from hdu_library_booking.services.yaml_plan import YamlPlanRepository


class TestYamlPlanRepository:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.tmpdir, "plans.yaml")
        self.repo = YamlPlanRepository(self.repo_path)

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def make_plan(self, **overrides):
        defaults = {
            "room_type": 1,
            "floor_id": 1558,
            "seat_num": "296",
            "start_hour": 13,
            "duration_hours": 9,
        }
        defaults.update(overrides)
        return BookingPlan(**defaults)

    # ------------------------------------------------------------------
    # 基本 CRUD
    # ------------------------------------------------------------------
    def test_load_all_empty(self):
        assert self.repo.load_all() == []

    def test_add_and_load(self):
        plan = self.make_plan()
        self.repo.add(plan)
        loaded = self.repo.load_all()
        assert len(loaded) == 1
        assert loaded[0].room_type == 1

    def test_add_generates_plan_id(self):
        plan = self.make_plan()
        assert plan.plan_id is None
        self.repo.add(plan)
        assert plan.plan_id is not None
        assert len(plan.plan_id) == 12  # uuid4 hex[:12]

    def test_add_generates_created_at(self):
        plan = self.make_plan()
        self.repo.add(plan)
        assert plan.created_at is not None

    def test_get_by_id(self):
        plan = self.make_plan()
        self.repo.add(plan)
        fetched = self.repo.get(plan.plan_id)
        assert fetched is not None
        assert fetched.plan_id == plan.plan_id

    def test_get_nonexistent(self):
        assert self.repo.get("nonexistent") is None

    def test_remove(self):
        plan = self.make_plan()
        self.repo.add(plan)
        assert self.repo.remove(plan.plan_id) is True
        assert self.repo.load_all() == []

    def test_remove_nonexistent(self):
        assert self.repo.remove("nonexistent") is False

    def test_save_all_overwrites(self):
        p1 = self.make_plan(seat_num="100")
        p2 = self.make_plan(seat_num="200")
        self.repo.save_all([p1, p2])
        loaded = self.repo.load_all()
        assert len(loaded) == 2

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def test_persists_to_disk(self):
        plan = self.make_plan()
        self.repo.add(plan)

        # 创建新 repo 实例重新加载
        repo2 = YamlPlanRepository(self.repo_path)
        loaded = repo2.load_all()
        assert len(loaded) == 1
        assert loaded[0].plan_id == plan.plan_id

    def test_cache_invalidation(self):
        plan = self.make_plan()
        self.repo.add(plan)

        # 手动修改文件（模拟外部修改）
        self.repo.invalidate_cache()
        loaded = self.repo.load_all()
        assert len(loaded) >= 1

    def test_handles_corrupt_yaml_raises(self):
        """损坏的 YAML 文件应抛出异常（而非静默返回空列表）。"""
        with open(self.repo_path, "w", encoding="utf-8") as f:
            f.write(":: not valid yaml :: {{{")

        repo = YamlPlanRepository(self.repo_path)
        with pytest.raises(yaml.YAMLError):
            repo.load_all()

    def test_handles_non_list_yaml(self):
        """YAML 文件内容为非列表时应返回空列表。"""
        import yaml

        with open(self.repo_path, "w", encoding="utf-8") as f:
            yaml.dump({"key": "value"}, f)

        repo = YamlPlanRepository(self.repo_path)
        plans = repo.load_all()
        assert plans == []

    def test_handles_missing_file(self):
        repo = YamlPlanRepository("/nonexistent/path/plans.yaml")
        plans = repo.load_all()
        assert plans == []

    # ------------------------------------------------------------------
    # 新增后字段
    # ------------------------------------------------------------------
    def test_add_preserves_existing_plan_id(self):
        plan = self.make_plan()
        plan.plan_id = "my-custom-id"
        self.repo.add(plan)
        assert plan.plan_id == "my-custom-id"

    def test_add_preserves_existing_created_at(self):
        plan = self.make_plan()
        plan.created_at = "2026-01-01T00:00:00"
        self.repo.add(plan)
        assert plan.created_at == "2026-01-01T00:00:00"

    def test_serialization_roundtrip(self):
        """复杂方案的序列化往返测试。"""
        from hdu_library_booking.models.plan import Weekday

        plan = BookingPlan(
            room_type=2,
            floor_id=1000,
            seat_num="050",
            start_hour=8,
            duration_hours=4,
            booker_name="张三",
            book_days=2,
            status=PlanStatus.DISABLED,
            weekday=Weekday.FRIDAY,
            tags=["安静", "角落"],
        )
        self.repo.add(plan)
        repo2 = YamlPlanRepository(self.repo_path)
        loaded = repo2.load_all()
        assert len(loaded) == 1
        p = loaded[0]
        assert p.room_type == 2
        assert p.status == PlanStatus.DISABLED
        assert p.weekday == Weekday.FRIDAY
        assert p.tags == ["安静", "角落"]
