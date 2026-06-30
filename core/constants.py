"""
公共常量：API URL、HTTP Headers、房间映射、错误消息等。
"""

# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------
URLS = {
    "book_seat": "https://hdu.huitu.zhishulib.com/Seat/Index/bookSeats",
    "login": "https://hdu.huitu.zhishulib.com/User/Index/login",
    "query_seats": "https://hdu.huitu.zhishulib.com/Seat/Index/searchSeats",
    "query_rooms": "https://hdu.huitu.zhishulib.com/Space/Category/list",
    "index": "https://hdu.huitu.zhishulib.com/",
    "user_base_info": "https://hdu.huitu.zhishulib.com/User/Center/baseInfo",
    "user_center": "https://hdu.huitu.zhishulib.com/User/Center/index",
}

# ---------------------------------------------------------------------------
# 默认 HTTP Headers — 模拟微信小程序 Android 环境，所有项目共用
# ---------------------------------------------------------------------------
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "Host": "hdu.huitu.zhishulib.com",
    "Origin": "https://hdu.huitu.zhishulib.com",
    "Referer": "https://hdu.huitu.zhishulib.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Pixel 3 Build/SP1A.210812.016.C2; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/86.0.4240.99 "
        "Mobile Safari/537.36 MicroMessenger/8.0.30 Language/zh_CN"
    ),
}

# 公共 GET 参数
DEFAULT_SESSION_PARAMS = {"LAB_JSON": "1"}

ROOM_TYPE_MAP = {
    "1": "自习室",
    "2": "教师休息室",
    "3": "阅览室",
    "4": "讨论室",
}

# ---------------------------------------------------------------------------
# API 错误消息 — 驱动重试 / 放弃决策
# ---------------------------------------------------------------------------
MSG_TIME_OUT_OF_RANGE = "超出可预约座位时间范围"
MSG_DUPLICATE = "已有预约，请勿重复预约！"
MSG_SEAT_UNAVAILABLE = "选择的座位无法预约，可能座位不可用或已经被其他人锁定或占用，请换一个再试"
MSG_INVALID_REQUEST = "非法请求"

# ---------------------------------------------------------------------------
# 默认值
# ---------------------------------------------------------------------------
DEFAULT_ORG_ID = "104"
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_TRIALS = 5
DEFAULT_RETRY_DELAY = 1.0
