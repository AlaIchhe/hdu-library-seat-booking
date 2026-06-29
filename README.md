# HDU Library Seat Booking

杭州电子科技大学图书馆座位自动预约系统 — 共享核心库。

## 简介

`core` 是从四个 HDU 图书馆自动预约项目（Instant、Master、AUTO_BOOK、Killer）中提取的公共逻辑库，提供统一的 API 客户端、认证、签名和工具函数，实现与[慧图图书馆管理平台](https://hdu.huitu.zhishulib.com)的全部 HTTP 交互。

## 功能

- **API 客户端** — 会话管理、房间查询、座位查询、预约提交
- **双认证方式** — Cookie 免密认证 / 用户名密码登录
- **Api-Token 签名** — MD5 + Base64 反篡改签名
- **配置管理** — YAML 配置文件读写
- **智能重试** — 根据服务器错误消息自动决策（重试/放弃/停止）
- **时间工具** — 北京时间 (UTC+8) 转换、预约计划解析

## 安装

```bash
pip install requests pyyaml
```

## 快速开始

```python
from core import HduLibraryClient

# Cookie 认证
client = HduLibraryClient()
client.set_cookie_header("uid=xxx; auth=yyy; ...")
client.resolve_uid()

# 查询房间
rooms = client.get_room_types()
detail = client.get_room_detail(rooms[0]["query"])

# 查询座位
from core.utils import build_begin_time
begin = build_begin_time(13, book_days=1)
floors = client.get_seat_map(
    detail["space_category"]["category_id"],
    detail["space_category"]["content_id"],
    begin, duration_hours=9,
)

# 定位座位
floor, seat = client.find_seat_in_floors(floors, floor_id=1558, seat_num="296")

# 提交预约
result = client.book_seat(seat["id"], client.uid, begin, 9)
```

## 项目结构

```
core/
├── __init__.py      # 统一导出
├── api.py           # HduLibraryClient HTTP 客户端
├── auth.py          # Api-Token 签名 (MD5 + Base64)
├── config.py        # YAML 配置读写
├── constants.py     # URL、Headers、错误消息等常量
├── exceptions.py    # 异常层次结构
├── room_cache.py    # 房间信息缓存
├── config_parser.py # 配置解析器
└── utils.py         # 时间工具函数
```

## 依赖

| 包 | 最低版本 | 用途 |
|---|---|---|
| `requests` | 2.28 | HTTP 客户端 |
| `PyYAML` | 6.0 | YAML 配置解析 |

## 文档

- [产品需求文档](docs/requirements.md)
- [核心库技术文档](docs/core.md)

## 安全提示

- 密码/Cookie 仅存储在本地，请勿泄露配置文件
- 请合理控制请求频率，避免账号被封禁
- 本工具为非官方工具，仅供学习研究使用
