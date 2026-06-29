"""
Api-Token 签名生成。

四个项目的签名算法完全一致：
  1. 拼接请求参数字符串
  2. 计算 MD5 哈希（hex digest）
  3. Base64 编码 MD5 hex 字符串
  4. 结果作为 Api-Token 请求头

这是慧图平台的自定义反篡改机制。
"""

import base64
import hashlib
from datetime import datetime


def generate_api_token(
    seat_id,
    uid,
    begin_time,
    duration,
    is_recommend=1,
    api_time=None,
):
    """生成慧图图书预约平台需要的 Api-Token 签名。

    参数
    ----------
    seat_id : str
        座位 ID（例如 "12345"）
    uid : str
        用户 UID
    begin_time : int
        预约开始时间（Unix 时间戳，秒）
    duration : int
        预约时长（秒）
    is_recommend : int, optional
        是否推荐座位。Instant / Master 使用 1，Killer 使用 0。默认 1。
    api_time : int, optional
        当前的 Unix 时间戳（秒）。若为 None，则自动取当前时间。

    返回
    -------
    tuple[str, int]
        (Api-Token 签名字符串, 对应的 api_time)
    """
    if api_time is None:
        api_time = int(datetime.now().timestamp())

    # 拼接签名字符串 — 四个项目的拼接方式完全一致
    token_source = (
        "post&/Seat/Index/bookSeats?LAB_JSON=1"
        f"&api_time{api_time}"
        f"&beginTime{begin_time}"
        f"&duration{duration}"
        f"&is_recommend{is_recommend}"
        f"&seatBookers[0]{uid}"
        f"&seats[0]{seat_id}"
    )

    md5_hex = hashlib.md5(token_source.encode("utf-8")).hexdigest()
    api_token = base64.b64encode(md5_hex.encode("utf-8")).decode("utf-8")
    return api_token, api_time
