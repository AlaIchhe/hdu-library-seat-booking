# core — HDU 图书馆预约系统共享核心库

## 概述

`core` 是从四个 HDU 图书馆自动预约项目中提取的公共逻辑库。它将原本分散在各项目中的相同代码统一为单一实现，四个项目（Instant、Master、AUTO_BOOK、Killer）均导入此库完成 API 交互。

**目标平台**：杭州电子科技大学慧图图书馆管理系统（`hdu.huitu.zhishulib.com`）

---

## 模块结构

```
core/
├── __init__.py      # 统一导出接口
├── api.py           # HduLibraryClient — 统一 HTTP API 客户端
├── auth.py          # Api-Token 签名生成
├── config.py        # YAML 配置文件读写
├── constants.py     # 全局常量
├── exceptions.py    # 异常层次结构
└── utils.py         # 工具函数
```

---

## 模块详解

### 1. `api.py` — HduLibraryClient

核心 API 客户端类，封装与慧图平台的所有 HTTP 交互。可同时向四个项目提供服务。

#### 属性

| 属性 | 类型 | 说明 |
|---|---|---|
| `session` | `requests.Session` | 共享的 HTTP 会话对象，所有请求通过它发出 |
| `uid` | `str` | 登录用户的内部 UID |
| `name` | `str` | 登录用户的姓名 |
| `config` | `dict` | 完整的配置字典 |
| `urls` | `dict` | API 端点映射 |
| `timeout` | `int` | HTTP 请求超时秒数（默认 10） |

#### 构造方法

```python
client = HduLibraryClient(config=None, timeout=None)
```

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `config` | `dict` | `{}` | 配置字典，通常来自 `config.yaml`。包含 `session`（headers/params）、`urls`、`request.timeout`、`user_info.uid` 等字段 |
| `timeout` | `int` | `10` | HTTP 请求超时秒数 |

初始化行为：
1. 从 config 中提取 `request.timeout` 或使用传入的 `timeout`
2. 从 config 中提取 `urls`，缺失时回退到 `constants.URLS`
3. 从 config 中提取 `session.headers`，缺失时回退到 `constants.DEFAULT_HEADERS`
4. 从 config 中提取 `session.params`，缺失时回退到 `{"LAB_JSON": "1"}`
5. 禁用 `urllib3` SSL 警告

#### 认证方法

##### Cookie 认证（Instant 项目）

```python
# 从原始 Cookie 字符串加载
client.set_cookie_header("uid=xxx; auth=yyy; login_time=...")

# 从 Netscape 格式的 JSON Cookie 文件加载
client.set_cookies_from_json_file("./cookies.json")
```

##### 密码登录（Master / Killer 项目）

```python
success = client.login(username="学号", password="密码", org_id="104")
# 返回 bool，登录成功后 client.uid 和 client.name 自动填充
```

- `username` / `password` 省略时从 config 的 `user_info` 段读取
- `org_id` 省略时默认 `"104"`（HDU 机构 ID）
- API 端点：`POST /User/Index/login`

##### UID 自动探测

```python
uid = client.resolve_uid()
```

当 UID 未知时，依次请求 `user_base_info` / `user_center` 端点，递归扫描整个 JSON 响应，匹配包含 `uid`、`user_id`、`userId` 等键的字段。算法会按候选字段的上下文（`current`、`user`、`login` 等关键词）打分排序，返回最佳匹配。

#### 房间与座位查询

```python
# 步骤 1：获取房间类型列表
rooms = client.get_room_types()
# 返回: [{"name": "自习室", "query": "space_category[category_id]=591&..."}, ...]

# 步骤 2：获取房间详情
detail = client.get_room_detail(rooms[0]["query"])
# 返回: {"space_category": {"category_id": "591", "content_id": "3"}, "range": {...}}

# 步骤 3：查询座位地图
floors = client.get_seat_map(
    category_id=detail["space_category"]["category_id"],
    content_id=detail["space_category"]["content_id"],
    lookup_time=begin_time,      # datetime 对象
    duration_hours=1,            # 查询时长（小时）
    num=1,                       # 座位数量
)
# 返回: [{"roomName": "四楼宋韵云图", "seatMap": {"info": {"id": 1558}, "POIs": [...]}}, ...]

# 步骤 4：在楼层中定位座位
floor_item, seat_item = client.find_seat_in_floors(floors, floor_id=1558, seat_num="296")
# 返回: (楼层dict, 座位POI dict)
```

API 端点对应关系：

| 方法 | HTTP 方法 | API 端点 |
|---|---|---|
| `get_room_types()` | GET | `/Space/Category/list` |
| `get_room_detail()` | GET | `/Seat/Index/searchSeats?{query}` |
| `get_seat_map()` | POST | `/Seat/Index/searchSeats` |

#### 预约提交

```python
result = client.book_seat(
    seat_id="12345",          # 座位 ID（来自 seat_item["id"]）
    uid="377454",             # 用户 UID
    begin_time=begin_time,    # datetime 对象（预约开始时间）
    duration_hours=9,         # 预约时长（小时）
    is_recommend=1,           # 1=推荐模式(Instant/Master), 0=不推荐(Killer)
    dry_run=False,            # True=仅生成 payload 不实际提交
)
```

内部流程：
1. 将 `begin_time` 和 `duration_hours` 转为 Unix 时间戳/秒
2. 调用 `auth.generate_api_token()` 生成 `Api-Token` 签名
3. 构造 POST payload：`beginTime`、`duration`、`is_recommend`、`api_time`、`seats[0]`、`seatBookers[0]`
4. 设置 `Api-Token` HTTP 头
5. POST 到 `/Seat/Index/bookSeats`
6. 返回 API 响应的 JSON 字典

---

### 2. `auth.py` — Api-Token 签名

慧图平台的自定义反篡改机制。四个项目逆向工程得出的完全一致的算法。

```python
from core import generate_api_token

token, api_time = generate_api_token(
    seat_id="12345",
    uid="377454",
    begin_time=1719705600,   # Unix 时间戳（秒）
    duration=32400,          # 秒
    is_recommend=1,          # Instant/Master=1, Killer=0
    api_time=None,           # None=自动取当前时间
)
```

#### 算法步骤

| 步骤 | 操作 | 说明 |
|---|---|---|
| 1 | 拼接源字符串 | `"post&/Seat/Index/bookSeats?LAB_JSON=1&api_time{ts}&beginTime{bt}&duration{d}&is_recommend{r}&seatBookers[0]{uid}&seats[0]{sid}"` |
| 2 | MD5 哈希 | `hashlib.md5(source.encode("utf-8")).hexdigest()` |
| 3 | Base64 编码 | `base64.b64encode(md5_hex.encode("utf-8")).decode("utf-8")` |

#### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `seat_id` | `str` | 必填 | 座位 ID |
| `uid` | `str` | 必填 | 用户 UID |
| `begin_time` | `int` | 必填 | Unix 时间戳（秒），预约开始时间 |
| `duration` | `int` | 必填 | 预约时长（秒） |
| `is_recommend` | `int` | `1` | Instant/Master 用 `1`，Killer 用 `0` |
| `api_time` | `int` | `None` | 当前时间戳，`None` 时自动取 `datetime.now().timestamp()` |

---

### 3. `config.py` — 配置文件读写

```python
from core import load_yaml_config, save_yaml_config, create_default_config

# 读取
cfg = load_yaml_config("config/config.yaml")

# 写入
save_yaml_config("config/config.yaml", cfg)

# 从模板创建
template = """
urls:
  book_seat: https://hdu.huitu.zhishulib.com/Seat/Index/bookSeats
  ...
"""
cfg = create_default_config("config/config.yaml", template)
```

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `load_yaml_config(path)` | 文件路径 | `dict` | 使用 `yaml.safe_load` 安全加载 |
| `save_yaml_config(path, data)` | 文件路径 + 字典 | — | 使用 `yaml.dump` 写入，保留 Unicode |
| `create_default_config(path, template)` | 文件路径 + YAML 模板字符串 | `dict` | 解析模板并写入文件，返回解析结果 |

---

### 4. `constants.py` — 全局常量

#### API 端点

```python
from core import URLS

URLS = {
    "book_seat":      "https://hdu.huitu.zhishulib.com/Seat/Index/bookSeats",
    "login":          "https://hdu.huitu.zhishulib.com/User/Index/login",
    "query_seats":    "https://hdu.huitu.zhishulib.com/Seat/Index/searchSeats",
    "query_rooms":    "https://hdu.huitu.zhishulib.com/Space/Category/list",
    "index":          "https://hdu.huitu.zhishulib.com/",
    "user_base_info": "https://hdu.huitu.zhishulib.com/User/Center/baseInfo",
    "user_center":    "https://hdu.huitu.zhishulib.com/User/Center/index",
}
```

#### HTTP Headers（模拟微信小程序 Android 环境）

```python
from core import DEFAULT_HEADERS

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
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 3 ...) ... MicroMessenger/8.0.30 ...",
}
```

#### 房间类型映射

```python
from core import ROOM_TYPE_MAP

ROOM_TYPE_MAP = {
    "1": "自习室",
    "2": "教师休息室",
    "3": "阅览室",
    "4": "讨论室",
}
```

#### API 错误消息

```python
from core import (
    MSG_TIME_OUT_OF_RANGE,   # "超出可预约座位时间范围" — 预约窗口未开放，应重试
    MSG_DUPLICATE,           # "已有预约，请勿重复预约！" — 已有预约，应放弃
    MSG_SEAT_UNAVAILABLE,    # "选择的座位无法预约..." — 座位被占，应放弃
    MSG_INVALID_REQUEST,     # "非法请求" — API 签名变更，应停止
)
```

这些消息用于驱动重试/放弃决策逻辑：

| 消息 | 含义 | 推荐行为 |
|---|---|---|
| `MSG_TIME_OUT_OF_RANGE` | 预约窗口未到开放时间 | 延迟后重试 |
| `MSG_DUPLICATE` | 已存在有效预约 | 放弃当前计划 |
| `MSG_SEAT_UNAVAILABLE` | 座位被他人锁定 | 放弃当前计划 |
| `MSG_INVALID_REQUEST` | 请求签名被拒 | 立即停止（API 已更新） |

#### 默认值

| 常量 | 值 | 说明 |
|---|---|---|
| `DEFAULT_ORG_ID` | `"104"` | HDU 机构 ID |
| `DEFAULT_TIMEOUT` | `10` | HTTP 超时秒数 |
| `DEFAULT_MAX_TRIALS` | `5` | 最大重试次数 |
| `DEFAULT_RETRY_DELAY` | `1.0` | 重试间隔秒数 |
| `DEFAULT_SESSION_PARAMS` | `{"LAB_JSON": "1"}` | 公共 GET 参数 |

---

### 5. `exceptions.py` — 异常层次结构

```
HduLibraryError                  # 所有异常的基类
├── LoginError                   # 登录失败
├── CookieError                  # Cookie 加载/解析失败
├── RoomQueryError               # 房间查询失败
├── SeatQueryError               # 座位查询失败
├── BookingError                 # 预约提交失败
├── BookingValidationError       # 预约参数校验失败
└── BookingCancelled             # 用户主动取消
```

使用示例：

```python
from core.exceptions import BookingCancelled, BookingValidationError

try:
    client.book_seat(...)
except BookingValidationError as e:
    print(f"预约参数错误：{e}")
```

---

### 6. `utils.py` — 工具函数

```python
from core.utils import (
    now_cst,                # 获取当前北京时间 (UTC+8) datetime
    build_begin_time,       # 根据 start_hour 和 book_days 构建预约开始时间
    parse_plan_code,        # 解析 "roomType:floorId:seatNum:startHour:durationHours"
    parse_execute_time,     # 解析 HH:MM 或 HH:MM:SS 执行时间字符串
    build_execute_datetime, # 构建执行 datetime（自动处理跨日）
    booking_message,        # 提取 API 响应的文本消息
    booking_failed,         # 判断预约是否失败
    is_time_out_of_range,   # 判断是否为"超出时间范围"错误
    get_seat_lookup_time,   # 计算座位查询的参考时间
)
```

#### 关键函数详情

##### `now_cst()`

```python
def now_cst() -> datetime:
    """获取当前北京时间 (UTC+8) 的 datetime 对象。"""
```

##### `build_begin_time(start_hour, book_days=0)`

```python
begin = build_begin_time(13, book_days=1)  # 明天 13:00
```

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `start_hour` | `int` | 必填 | 预约开始小时（0-23） |
| `book_days` | `int` | `0` | 天数偏移（0=今天, 1=明天, 2=后天） |

##### `parse_plan_code(plan_text)`

```python
plan = parse_plan_code("1:1558:296:13:9")
# 返回: {"room_type": 1, "floor_id": 1558, "seat_num": "296", "start_hour": 13, "duration_hours": 9}
```

##### `get_seat_lookup_time()`

```python
lookup = get_seat_lookup_time()
```

根据当前时间决定查询参考时间：
- `hour >= 22` → 次日 08:00
- `hour < 7` → 当日 08:00
- 其他 → 当前时间

##### `build_execute_datetime(execute_at_str, now=None)`

```python
dt = build_execute_datetime("20:00:00")
# 返回今天的 20:00（若已过则返回明天的 20:00）
```

---

## 依赖

共享库仅依赖两个 Python 包：

| 包 | 最低版本 | 用途 |
|---|---|---|
| `requests` | 2.28 | HTTP 客户端 |
| `PyYAML` | 6.0 | YAML 配置文件解析 |

无需安装数据库、Web 框架或其他重型依赖。

---

## 项目适配方式

四个项目通过不同方式使用此库：

| 项目 | 如何引用 core | 认证方式 | `is_recommend` |
|---|---|---|---|
| **Instant** | `InstantBooker(HduLibraryClient)` 继承 | Cookie 注入 | `1` |
| **Master** | `Master.client = HduLibraryClient(config)` 组合 | 密码登录 | `1` |
| **AUTO_BOOK** | `self.client = HduLibraryClient(config)` 组合 | Selenium → Cookie | `0` |
| **Killer** | `Killer.client = HduLibraryClient(config)` 组合 | 密码登录 | `0` |

每个项目只需 `sys.path.insert(0, project_root)` 后即可 `from core import ...`。

---

## 快速开始

```python
import sys
sys.path.insert(0, ".")  # 项目根目录

from core import HduLibraryClient, MSG_TIME_OUT_OF_RANGE
from core.utils import now_cst, build_begin_time, parse_plan_code

# 1. 初始化客户端（Cookie 方式）
client = HduLibraryClient()
client.set_cookie_header("uid=xxx; auth=yyy; ...")
client.resolve_uid()

# 2. 查询座位
rooms = client.get_room_types()
detail = client.get_room_detail(rooms[0]["query"])
begin = build_begin_time(13, book_days=1)
floors = client.get_seat_map(
    detail["space_category"]["category_id"],
    detail["space_category"]["content_id"],
    begin, duration_hours=9,
)
floor, seat = client.find_seat_in_floors(floors, floor_id=1558, seat_num="296")

# 3. 预约
result = client.book_seat(seat["id"], client.uid, begin, 9)
if result.get("CODE") == "ok":
    print("预约成功！")
```
