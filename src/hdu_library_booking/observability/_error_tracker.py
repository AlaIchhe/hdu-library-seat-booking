"""
错误追踪与度量模块 (Instrumentation / Telemetry)。

提供线程安全的错误计数、分类、时间线记录和报告导出，
便于排查问题和监控系统健康状态。

用法
----
from hdu_library_booking.observability._error_tracker import error_tracker

# 在捕获异常处插桩

try:
    ...
except HduLibraryError as exc:
    error_tracker.record("network", str(exc), exc)
    raise

# 查看报告
print(error_tracker.summary())
error_tracker.export_json("errors.json")
"""

import json
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


# ============================================================================
# 错误类别常量
# ============================================================================
class ErrorCategory:
    """标准错误类别，统一命名避免散落字符串。"""

    NETWORK = "network"  # HTTP 请求失败、超时、连接错误
    AUTH = "auth"  # 登录失败、Cookie 无效
    CONFIG = "config"  # 配置文件读取/解析错误
    ROOM_QUERY = "room_query"  # 房间类型/详情查询失败
    SEAT_QUERY = "seat_query"  # 座位地图/搜索失败
    BOOKING = "booking"  # 预约提交失败
    BOOKING_VALIDATION = "booking_validation"  # 方案参数校验失败
    BOOKING_CANCELLED = "booking_cancelled"  # 用户主动取消
    PERSISTENCE = "persistence"  # 方案文件读写失败
    NOTIFICATION = "notification"  # 通知发送失败
    JSON_PARSE = "json_parse"  # JSON 解析失败
    UI = "ui"  # 终端界面交互错误
    STRATEGY = "strategy"  # 座位选择策略错误
    UNKNOWN = "unknown"  # 未分类错误


# ============================================================================
# 单条错误记录
# ============================================================================
class ErrorRecord:
    """单条错误记录，包含完整上下文。"""

    __slots__ = (
        "category",
        "exception_type",
        "message",
        "module",
        "timestamp",
        "traceback",
    )

    def __init__(
        self,
        category: str,
        message: str,
        exception: BaseException | None = None,
        module: str = "",
    ):
        self.category = category
        self.message = message
        self.exception_type = type(exception).__name__ if exception else ""
        self.traceback = "".join(traceback.format_exception(exception)) if exception else ""
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.module = module

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "message": self.message,
            "exception_type": self.exception_type,
            "traceback": self.traceback,
            "timestamp": self.timestamp,
            "module": self.module,
        }


# ============================================================================
# 错误追踪器
# ============================================================================
class ErrorTracker:
    """线程安全的错误追踪器。

    功能：
      - 按类别计数
      - 保存最近的错误记录（环形缓冲区）
      - 导出 JSON / 字典 / 文本摘要
      - 支持自定义回调（如告警）

    线程安全：所有写操作使用可重入锁保护。
    """

    # 默认保留的最近错误记录数
    DEFAULT_MAX_RECORDS = 500

    def __init__(self, max_records: int = DEFAULT_MAX_RECORDS):
        self._lock = threading.RLock()
        self._counters: dict[str, int] = defaultdict(int)
        self._records: list[ErrorRecord] = []
        self._max_records = max_records
        self._start_time = time.time()
        # 首次错误时间（按类别）
        self._first_error_at: dict[str, str] = {}
        # 最近错误时间（按类别）
        self._last_error_at: dict[str, str] = {}
        # 外部回调：fn(category, message, record)
        self._callbacks: list[Any] = []

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------
    def record(
        self,
        category: str,
        message: str,
        exception: BaseException | None = None,
        module: str = "",
    ) -> ErrorRecord:
        """记录一条错误。

        参数
        ----------
        category : str
            错误类别（推荐使用 ErrorCategory 常量）。
        message : str
            人类可读的错误描述。
        exception : BaseException, optional
            原始异常对象，用于提取类型和堆栈。
        module : str
            发生错误的模块名（如 __name__）。

        返回
        -------
        ErrorRecord
            创建的错误记录。
        """
        record = ErrorRecord(category, message, exception, module)
        now_iso = record.timestamp

        with self._lock:
            self._counters[category] += 1
            self._counters["__total__"] = self._counters.get("__total__", 0) + 1

            if category not in self._first_error_at:
                self._first_error_at[category] = now_iso
            self._last_error_at[category] = now_iso

            self._records.append(record)
            # 环形缓冲区：超过上限时丢弃旧记录
            while len(self._records) > self._max_records:
                self._records.pop(0)

        # 触发回调（在锁外执行，防止回调中再次加锁死锁）
        for cb in self._callbacks:
            try:
                cb(category, message, record)
            except Exception:
                pass

        return record

    def count(self, category: str) -> int:
        """获取某类错误的累计次数。"""
        with self._lock:
            return self._counters.get(category, 0)

    def total(self) -> int:
        """获取所有错误的累计次数。"""
        with self._lock:
            return self._counters.get("__total__", 0)

    # ------------------------------------------------------------------
    # 回调
    # ------------------------------------------------------------------
    def on_error(self, callback: object) -> None:
        """注册错误回调。回调签名：fn(category: str, message: str, record: ErrorRecord)。"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: object) -> bool:
        """移除已注册的回调，返回 True 表示成功。"""
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def recent(self, n: int = 20, category: str | None = None) -> list[ErrorRecord]:
        """获取最近 n 条错误记录，可按类别过滤。"""
        with self._lock:
            records = list(self._records)
        if category:
            records = [r for r in records if r.category == category]
        return records[-n:]

    def categories(self) -> list[str]:
        """返回所有出现过错误的类别。"""
        with self._lock:
            return sorted(self._counters.keys())

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """导出完整的错误统计数据字典。"""
        with self._lock:
            return {
                "summary": {
                    "total_errors": self._counters.get("__total__", 0),
                    "uptime_seconds": round(time.time() - self._start_time, 1),
                    "categories_tracked": len([k for k in self._counters if k != "__total__"]),
                },
                "counters": dict(self._counters),
                "first_error_at": dict(self._first_error_at),
                "last_error_at": dict(self._last_error_at),
                "recent_errors": [r.to_dict() for r in self._records[-50:]],
            }

    def summary(self) -> str:
        """生成人类可读的文本摘要。"""
        data = self.to_dict()
        s = data["summary"]
        lines = [
            "=" * 56,
            "  错误追踪报告 (Error Tracker Summary)",
            "=" * 56,
            f"  运行时间:     {s['uptime_seconds']:.0f} 秒",
            f"  错误总数:     {s['total_errors']}",
            f"  涉及类别数:   {s['categories_tracked']}",
            "",
            "  各类别错误计数:",
        ]
        counters = data["counters"]
        for cat in sorted(counters):
            if cat == "__total__":
                continue
            count = counters[cat]
            first = data["first_error_at"].get(cat, "-")
            last = data["last_error_at"].get(cat, "-")
            bar = "█" * min(count, 40)
            lines.append(f"  {cat:<22s} {count:>5d}  {bar}")
            lines.append(f"  {'':22s} 首次: {first}")
            lines.append(f"  {'':22s} 最近: {last}")

        # 最近的错误
        recent = data["recent_errors"][-10:]
        if recent:
            lines.append("")
            lines.append("  最近 10 条错误:")
            lines.append("  " + "-" * 52)
            for r in reversed(recent):
                lines.append(f"  [{r['category']}] {r['message'][:60]}")
                if r["exception_type"]:
                    lines.append(f"    ({r['exception_type']}) {r['timestamp']}")

        lines.append("=" * 56)
        return "\n".join(lines)

    def export_json(self, path: str) -> None:
        """将错误报告导出为 JSON 文件。"""
        data = self.to_dict()
        data["exported_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # 重置
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """清空所有计数和记录（谨慎使用）。"""
        with self._lock:
            self._counters.clear()
            self._records.clear()
            self._first_error_at.clear()
            self._last_error_at.clear()
            self._start_time = time.time()


# ============================================================================
# 模块级单例 — 跨模块共享
# ============================================================================
error_tracker = ErrorTracker()
