"""指标收集器 — 在 ErrorTracker 基础上增加性能指标。

提供：
  - 错误计数（继承自 ErrorTracker）
  - 通用计数器 (counter)
  - 延迟直方图 (histogram)
  - 瞬时值 (gauge)
  - Prometheus 格式导出

用法
----
from hdu_library_booking.observability import metrics_collector as metrics

# 计数
metrics.increment("booking_requests_total", labels={"status": "success"})

# 延迟
metrics.observe_latency("booking_latency_seconds", 0.45, labels={"operation": "submit"})

# 计时器（上下文管理器）
with metrics.timer("api_call_duration", labels={"endpoint": "book_seat"}):
    make_api_request()

# Prometheus 格式输出
print(metrics.prometheus_output())
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from hdu_library_booking.observability._error_tracker import ErrorTracker


class MetricsCollector(ErrorTracker):
    """线程安全的指标收集器，继承并扩展 ErrorTracker。

    在保留原有错误追踪能力的基础上，增加通用计数器和延迟直方图。
    满足 Instrumentation 协议（继承自 ErrorTracker）。
    """

    def __init__(self, max_records: int = ErrorTracker.DEFAULT_MAX_RECORDS):
        super().__init__(max_records)
        self._metrics_lock = threading.RLock()
        # 注意：此处 _counters 与 ErrorTracker._counters 同名但类型不同。
        # ErrorTracker 的 _counters 用于错误计数（int），
        # 此处的 _counters 用于通用指标计数（float）。
        # 为避免冲突，使用不同的内部名称。
        self._metric_counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    # ------------------------------------------------------------------
    # 通用计数器
    # ------------------------------------------------------------------

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """增加计数器的值。

        Parameters
        ----------
        name : str
            指标名称。
        value : float
            增量（默认 1.0）。
        labels : dict, optional
            标签键值对，用于区分不同维度。
        """
        key = _format_key(name, labels)
        with self._metrics_lock:
            self._metric_counters[key] += value

    # ------------------------------------------------------------------
    # 延迟直方图
    # ------------------------------------------------------------------

    def observe_latency(
        self,
        name: str,
        seconds: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """记录一个延迟观测值。

        Parameters
        ----------
        name : str
            指标名称。
        seconds : float
            耗时秒数。
        labels : dict, optional
            标签键值对。
        """
        key = _format_key(name, labels)
        with self._metrics_lock:
            self._histograms[key].append(seconds)

    # ------------------------------------------------------------------
    # 计时器（上下文管理器）
    # ------------------------------------------------------------------

    @contextmanager
    def timer(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> Iterator[None]:
        """自动计时的上下文管理器。

        Parameters
        ----------
        name : str
            指标名称。
        labels : dict, optional
            标签键值对。

        Examples
        --------
        >>> with metrics.timer("api_call", labels={"endpoint": "book"}):
        ...     make_request()
        """
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - start
            self.observe_latency(name, elapsed, labels)

    # ------------------------------------------------------------------
    # 瞬时值
    # ------------------------------------------------------------------

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """设置瞬时值。

        Parameters
        ----------
        name : str
            指标名称。
        value : float
            当前值。
        labels : dict, optional
            标签键值对。
        """
        key = _format_key(name, labels)
        with self._metrics_lock:
            self._gauges[key] = value

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def prometheus_output(self) -> str:
        """生成 Prometheus text exposition 格式输出。

        Returns
        -------
        str
            符合 Prometheus 抓取格式的文本。
        """
        lines: list[str] = []

        with self._metrics_lock:
            # 计数器
            for key, val in sorted(self._metric_counters.items()):
                lines.append(f"# TYPE {_base_name(key)} counter")
                lines.append(f"{key} {val}")
                lines.append("")

            # 瞬时值
            for key, val in sorted(self._gauges.items()):
                lines.append(f"# TYPE {_base_name(key)} gauge")
                lines.append(f"{key} {val}")
                lines.append("")

            # 直方图
            for key, values in sorted(self._histograms.items()):
                lines.append(f"# TYPE {_base_name(key)} summary")
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values):.6f}")
                lines.append("")

        return "\n".join(lines)

    def metrics_summary(self) -> dict:
        """导出指标摘要字典。

        Returns
        -------
        dict
            包含 counters、gauges、histograms 的字典。
        """
        with self._metrics_lock:
            histograms_summary = {}
            for key, values in self._histograms.items():
                histograms_summary[key] = {
                    "count": len(values),
                    "sum": sum(values),
                    "avg": sum(values) / len(values) if values else 0,
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                }
            return {
                "counters": dict(self._metric_counters),
                "gauges": dict(self._gauges),
                "histograms": histograms_summary,
            }

    # ------------------------------------------------------------------
    # 重置
    # ------------------------------------------------------------------

    def reset_metrics(self) -> None:
        """清空所有指标数据（保留错误记录）。"""
        with self._metrics_lock:
            self._metric_counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def reset(self) -> None:
        """清空所有数据（错误记录 + 指标）。"""
        super().reset()
        self.reset_metrics()


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

metrics_collector = MetricsCollector()


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _format_key(name: str, labels: dict[str, str] | None) -> str:
    """将指标名和标签组合成 Prometheus 格式的 key。"""
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}}"


def _base_name(key: str) -> str:
    """从带标签的 key 中提取基础指标名。"""
    idx = key.find("{")
    return key[:idx] if idx > 0 else key
