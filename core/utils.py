"""
时间工具函数。

处理 UTC+8 时区转换、datetime 构建、预约计划解析等。
"""

from datetime import datetime, timedelta


def now_cst():
    """获取当前北京时间 (UTC+8) 的 datetime 对象。"""
    return datetime.now().astimezone()


def build_begin_time(start_hour, book_days=0):
    """根据开始小时和偏移天数构建预约开始时间。

    参数
    ----------
    start_hour : int
        预约开始小时（0-23）。
    book_days : int, optional
        天数偏移。0 = 今天，1 = 明天，2 = 后天。默认 0。

    返回
    -------
    datetime
    """
    now = now_cst()
    return (now + timedelta(days=book_days)).replace(
        hour=start_hour, minute=0, second=0, microsecond=0
    )


def parse_plan_code(plan_text):
    """解析预约计划编码字符串。

    格式：roomType:floorId:seatNum:startHour:durationHours
    示例：'1:1558:296:13:9'

    参数
    ----------
    plan_text : str
        冒号分隔的计划编码。

    返回
    -------
    dict
        包含 room_type, floor_id, seat_num, start_hour, duration_hours 的字典。
    """
    try:
        room_type, floor_id, seat_num, start_hour, duration_hours = plan_text.split(":")
        return {
            "room_type": int(room_type),
            "floor_id": int(floor_id),
            "seat_num": str(seat_num),
            "start_hour": int(start_hour),
            "duration_hours": int(duration_hours),
        }
    except Exception as exc:
        raise ValueError("plan 格式应为 roomType:floorId:seatNum:startHour:durationHours") from exc


def parse_execute_time(execute_at_str):
    """解析执行时间字符串。

    参数
    ----------
    execute_at_str : str
        格式为 HH:MM 或 HH:MM:SS。

    返回
    -------
    time or None
    """
    text = str(execute_at_str or "").strip()
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            pass
    raise ValueError("execute_at 格式应为 HH:MM 或 HH:MM:SS")


def build_execute_datetime(execute_at_str, now=None):
    """根据执行时间字符串构建今天的执行 datetime。

    若时间已过，则自动推迟到明天。

    参数
    ----------
    execute_at_str : str
        格式为 HH:MM 或 HH:MM:SS。
    now : datetime, optional
        参考时间；默认现在。

    返回
    -------
    datetime or None
    """
    parsed = parse_execute_time(execute_at_str)
    if parsed is None:
        return None
    now = now or now_cst()
    target = now.replace(
        hour=parsed.hour, minute=parsed.minute, second=parsed.second, microsecond=0
    )
    if target <= now:
        target += timedelta(days=1)
    return target


def normalize_execute_time(value):
    """将执行时间格式化为 HH:MM:SS 字符串。

    参数
    ----------
    value : str
        原始执行时间字符串（HH:MM 或 HH:MM:SS）。

    返回
    -------
    str
        格式化后的 HH:MM:SS 字符串，空输入返回空字符串。
    """
    parsed = parse_execute_time(value)
    if parsed is None:
        return ""
    return f"{parsed.hour:02d}:{parsed.minute:02d}:{parsed.second:02d}"


def is_time_out_of_range(result):
    """判断预约结果是否为"超出时间范围"错误。"""
    message = str(result.get("MESSAGE") or (result.get("DATA") or {}).get("msg") or "")
    from .constants import MSG_TIME_OUT_OF_RANGE

    return MSG_TIME_OUT_OF_RANGE in message


def booking_failed(result):
    """判断预约是否失败。"""
    if not isinstance(result, dict):
        return True
    data = result.get("DATA") if isinstance(result.get("DATA"), dict) else {}
    code = str(result.get("CODE") or "").strip().lower()
    status = str(data.get("result") or "").strip().lower()
    return status == "fail" or code in {"paramerror", "error", "fail", "failed"}


def booking_message(result):
    """提取预约结果的文本消息。"""
    if not isinstance(result, dict):
        return "预约接口返回失败"
    data = result.get("DATA") if isinstance(result.get("DATA"), dict) else {}
    return str(result.get("MESSAGE") or data.get("msg") or "预约接口返回失败").strip()


def get_seat_lookup_time():
    """计算座位查询时使用的参考时间。

    22 点之后 → 次日 08:00
    7 点之前 → 当日 08:00
    其他     → 当前时间

    返回
    -------
    datetime
    """
    now = now_cst()
    if now.hour >= 22:
        return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    elif now.hour < 7:
        return now.replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        return now
