"""
Api-Token 签名生成。

签名算法：
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

    if api_time is None:
        api_time = int(datetime.now().timestamp())

    # 拼接签名字符串
    token_source = (
        "post&/Seat/Index/bookSeats?LAB_JSON=1"
        f"&api_time{api_time}"
        f"&beginTime{begin_time}"
        f"&duration{duration}"
        f"&is_recommend{is_recommend}"
        f"&seatBookers[0]{uid}"
        f"&seats[0]{seat_id}"
    )

    # MD5 用于慧图 API 令牌签名协议，非密码哈希 — 安全场景见 B324 豁免
    md5_hex = hashlib.md5(token_source.encode("utf-8"), usedforsecurity=False).hexdigest()
    api_token = base64.b64encode(md5_hex.encode("utf-8")).decode("utf-8")
    return api_token, api_time
