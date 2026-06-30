# HDU Library Seat Booking

杭州电子科技大学图书馆座位自动预约系统。

## 部署

### 环境要求

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (包管理器)

### 快速开始

```bash
# 安装 uv (Windows)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 安装 uv (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目
git clone https://github.com/zhuhe/hdu-library-booking.git
cd hdu-library-booking

# 安装依赖 + 创建虚拟环境
uv sync

# 运行
uv run hdu-tui                                    # 终端交互模式
uv run hdu-book --cookie "uid=xxx;auth=yyy" --plan "1:1558:296:13:9"
```

### uv 常用命令

```bash
# 同步依赖（根据 uv.lock 安装）
uv sync

# 添加依赖
uv add requests

# 添加开发依赖
uv add --dev pytest

# 升级依赖
uv sync --upgrade

# 锁定依赖（生成/更新 uv.lock）
uv lock

# 运行命令（自动激活虚拟环境）
uv run python main.py
uv run pytest tests/unit/
uv run ruff check core/ app/

# 指定 Python 版本
uv sync --python 3.12
```

### 运行

终端交互模式：

```bash
uv run python main.py
```

命令行一次性执行：

```bash
# Cookie 认证
uv run hdu-book --cookie "uid=xxx;auth=yyy" --plan "1:1558:296:13:9"

# 预览模式（不实际提交）
uv run hdu-book --cookie "..." --plan "..." --dry-run

# 定时预约
uv run hdu-book --cookie "..." --plan "..." --at "19:59:30"

# 环境变量
export HDU_COOKIE="uid=xxx;auth=yyy"
export HDU_PLAN="1:1558:296:13:9"
uv run hdu-book
```

### pip 安装（可选）

```bash
pip install .
hdu-tui        # 终端交互模式
hdu-book --cookie "..." --plan "..."
```

### 服务器部署（cron 定时任务）

```bash
# 每天 19:58 自动执行预约
58 19 * * * cd /path/to/project && uv run hdu-book >> booking.log 2>&1
```

## 错误追踪

系统内置了全面的错误插桩（Instrumentation），自动追踪各类运行错误。

### 查看错误报告

```bash
# 命令行打印错误统计
python main.py --cli --report

# 导出 JSON 格式报告
python main.py --cli --report-json errors.json
```

### 程序中获取追踪数据

```python
from core.metrics import error_tracker, ErrorCategory

# 查看摘要
print(error_tracker.summary())

# 按类别查询
print(f"网络错误: {error_tracker.count(ErrorCategory.NETWORK)}")
print(f"预约失败: {error_tracker.count(ErrorCategory.BOOKING)}")

# 导出 JSON
error_tracker.export_json("errors.json")

# 获取最近错误
for r in error_tracker.recent(10):
    print(f"[{r.category}] {r.message}")
```

### 追踪的错误类别

| 类别 | 说明 |
|------|------|
| `network` | HTTP 请求失败、超时、连接错误 |
| `auth` | 登录失败、Cookie 无效、UID 识别失败 |
| `config` | 配置文件读取/写入/解析错误 |
| `room_query` | 房间类型/详情查询失败 |
| `seat_query` | 座位地图查询/搜索失败 |
| `booking` | 预约提交被拒绝 |
| `booking_validation` | 方案参数校验失败 |
| `booking_cancelled` | 用户主动取消 |
| `persistence` | 方案文件读写失败 |
| `notification` | 通知发送失败 |
| `json_parse` | JSON 解析失败 |
| `strategy` | 座位选择策略失败 |
| `ui` | 终端界面交互错误 |
| `unknown` | 未分类错误 |

## 安全提示

- 密码/Cookie 仅存储在本地，请勿泄露配置文件
- 请合理控制请求频率，避免账号被封禁
- 本工具为非官方工具，仅供学习研究使用
