"""Tests for hdu_library_booking.observability._error_tracker — ErrorTracker, ErrorRecord, ErrorCategory."""

import json
import os
import tempfile
import threading

from hdu_library_booking.observability._error_tracker import (
    ErrorCategory,
    ErrorRecord,
    ErrorTracker,
)
from hdu_library_booking.observability._error_tracker import (
    error_tracker as global_tracker,
)


class TestErrorCategory:
    """ErrorCategory 常量应覆盖所有预设类别。"""

    def test_all_categories_defined(self):
        categories = [
            v for v in vars(ErrorCategory).values() if isinstance(v, str) and not v.startswith("_")
        ]
        assert "network" in categories
        assert "auth" in categories
        assert "config" in categories
        assert "room_query" in categories
        assert "seat_query" in categories
        assert "booking" in categories
        assert "booking_validation" in categories
        assert "booking_cancelled" in categories
        assert "persistence" in categories
        assert "notification" in categories
        assert "json_parse" in categories
        assert "strategy" in categories
        assert "ui" in categories
        assert "unknown" in categories


class TestErrorRecord:
    """ErrorRecord 数据类测试。"""

    def test_basic_record(self):
        r = ErrorRecord("network", "连接超时")
        assert r.category == "network"
        assert r.message == "连接超时"
        assert r.exception_type == ""
        assert r.traceback == ""
        assert r.module == ""
        assert r.timestamp  # ISO 格式时间戳

    def test_record_with_exception(self):
        try:
            raise ValueError("test error")
        except ValueError as exc:
            r = ErrorRecord("test", "msg", exc, module="test_mod")

        assert r.exception_type == "ValueError"
        assert "ValueError" in r.traceback
        assert "test error" in r.traceback
        assert r.module == "test_mod"

    def test_to_dict(self):
        r = ErrorRecord("auth", "登录失败")
        d = r.to_dict()
        assert d["category"] == "auth"
        assert d["message"] == "登录失败"
        assert "timestamp" in d


class TestErrorTrackerBasic:
    """ErrorTracker 基本功能测试。"""

    def setup_method(self):
        self.tracker = ErrorTracker(max_records=100)

    def test_record_and_count(self):
        self.tracker.record("network", "msg1")
        self.tracker.record("network", "msg2")
        self.tracker.record("auth", "msg3")

        assert self.tracker.count("network") == 2
        assert self.tracker.count("auth") == 1
        assert self.tracker.count("nonexistent") == 0
        assert self.tracker.total() == 3

    def test_recent_returns_latest(self):
        for i in range(10):
            self.tracker.record("test", f"msg{i}")

        recent = self.tracker.recent(5)
        assert len(recent) == 5
        assert recent[-1].message == "msg9"

    def test_recent_filter_by_category(self):
        self.tracker.record("network", "n1")
        self.tracker.record("auth", "a1")
        self.tracker.record("network", "n2")

        net = self.tracker.recent(10, category="network")
        assert len(net) == 2
        assert all(r.category == "network" for r in net)

    def test_categories_list(self):
        self.tracker.record("network", "n1")
        self.tracker.record("auth", "a1")
        cats = self.tracker.categories()
        assert "network" in cats
        assert "auth" in cats
        assert "__total__" in cats

    def test_ring_buffer_eviction(self):
        tracker = ErrorTracker(max_records=5)
        for i in range(10):
            tracker.record("test", f"msg{i}")
        # 仅保留最近 5 条
        assert len(tracker.recent(20)) == 5
        # 最旧的 5 条已被驱逐
        messages = [r.message for r in tracker.recent(20)]
        assert "msg0" not in messages
        assert "msg5" in messages

    def test_to_dict_structure(self):
        self.tracker.record("network", "test")
        d = self.tracker.to_dict()
        assert "summary" in d
        assert "counters" in d
        assert "first_error_at" in d
        assert "last_error_at" in d
        assert "recent_errors" in d
        assert d["summary"]["total_errors"] == 1

    def test_summary_text(self):
        self.tracker.record("network", "test error")
        text = self.tracker.summary()
        assert "Error Tracker Summary" in text
        assert "network" in text
        assert "test error" in text

    def test_export_json(self):
        self.tracker.record("network", "test")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            self.tracker.export_json(path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert data["summary"]["total_errors"] == 1
            assert "exported_at" in data
        finally:
            os.unlink(path)

    def test_reset(self):
        self.tracker.record("network", "msg")
        assert self.tracker.total() == 1
        self.tracker.reset()
        assert self.tracker.total() == 0
        assert self.tracker.categories() == []


class TestErrorTrackerCallbacks:
    """回调功能测试。"""

    def setup_method(self):
        self.tracker = ErrorTracker()
        self.received = []

    def test_callback_fires_on_record(self):
        def cb(category, message, record):
            self.received.append((category, message))

        self.tracker.on_error(cb)
        self.tracker.record("network", "test")
        assert len(self.received) == 1
        assert self.received[0] == ("network", "test")

    def test_remove_callback(self):
        def cb(cat, msg, rec):
            self.received.append(msg)

        self.tracker.on_error(cb)
        assert self.tracker.remove_callback(cb) is True
        self.tracker.record("test", "should not fire")
        assert len(self.received) == 0

    def test_remove_nonexistent_callback(self):
        def cb(cat, msg, rec):
            pass

        assert self.tracker.remove_callback(cb) is False

    def test_callback_exception_does_not_block(self):
        def bad_cb(cat, msg, rec):
            raise RuntimeError("boom")

        def good_cb(cat, msg, rec):
            self.received.append(msg)

        self.tracker.on_error(bad_cb)
        self.tracker.on_error(good_cb)
        # 不应抛出异常
        self.tracker.record("test", "msg")
        assert len(self.received) == 1


class TestErrorTrackerThreadSafety:
    """线程安全测试。"""

    def test_concurrent_records(self):
        tracker = ErrorTracker(max_records=1000)
        errors_per_thread = 100
        thread_count = 10

        def worker(tid):
            for i in range(errors_per_thread):
                tracker.record(f"cat_{tid % 3}", f"t{tid}_msg{i}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker.total() == errors_per_thread * thread_count
        # 每个类别应有 thread_count/3 个线程 * errors_per_thread 条 ≈
        for c in ("cat_0", "cat_1", "cat_2"):
            assert tracker.count(c) > 0


class TestGlobalTracker:
    """模块级单例 error_tracker 测试。"""

    def test_global_tracker_is_singleton(self):
        from hdu_library_booking.observability._error_tracker import error_tracker as et1
        from hdu_library_booking.observability._error_tracker import error_tracker as et2

        assert et1 is et2

    def test_global_tracker_works(self):
        # 重置以避免与其他测试干扰
        global_tracker.reset()
        global_tracker.record("test_cat", "global test")
        assert global_tracker.count("test_cat") == 1
        global_tracker.reset()
