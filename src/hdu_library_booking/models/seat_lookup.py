"""座位查询时参考时间 — 纯业务规则，零基础设施依赖。"""

from datetime import datetime, timedelta

from . import time_utils as _time


def get_seat_lookup_time() -> datetime:
    """计算座位查询时使用的参考时间。

    22 点之后 → 次日 08:00
    7 点之前 → 当日 08:00
    其他     → 当前时间

    返回
    -------
    datetime
    """
    now = _time.now_cst()
    if now.hour >= 22:
        return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    elif now.hour < 7:
        return now.replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        return now
