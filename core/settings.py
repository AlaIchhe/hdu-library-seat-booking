"""统一配置管理 — 单一入口，分层覆盖。

优先级 (高 → 低):
  1. 命令行参数 (通过 from_cli / with_cli_overrides)
  2. 环境变量 (HDU_ 前缀，__ 分隔嵌套)
  3. .env 文件
  4. config.yaml (通过 from_yaml 加载)
  5. 代码默认值
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# =============================================================================
# 子配置模型
# =============================================================================


class APIUrls(BaseModel):
    """API 端点 URL 配置。"""

    book_seat: str = "https://hdu.huitu.zhishulib.com/Seat/Index/bookSeats"
    login: str = "https://hdu.huitu.zhishulib.com/User/Index/login"
    query_seats: str = "https://hdu.huitu.zhishulib.com/Seat/Index/searchSeats"
    query_rooms: str = "https://hdu.huitu.zhishulib.com/Space/Category/list"
    user_base_info: str = "https://hdu.huitu.zhishulib.com/User/Center/baseInfo"
    user_center: str = "https://hdu.huitu.zhishulib.com/User/Center/index"


class AuthConfig(BaseModel):
    """认证配置。"""

    cookie: str | None = Field(default=None, description="Cookie 认证字符串")
    cookie_file: str | None = Field(default=None, description="Netscape JSON Cookie 文件路径")
    uid: str | None = Field(default=None, description="用户 UID (预设置可跳过 API 探测)")
    name: str | None = Field(default=None, description="用户姓名")
    org_id: str = Field(default="104", description="机构 ID")
    login_name: str | None = Field(default=None, description="登录名 (密码认证 fallback)")
    password: str | None = Field(default=None, description="密码 (密码认证 fallback)")


class HTTPConfig(BaseModel):
    """HTTP 请求配置。"""

    timeout: int = Field(default=10, ge=1, le=120, description="请求超时秒数")
    verify: bool = Field(default=False, description="SSL 证书验证")
    trust_env: bool = Field(default=False, description="是否信任代理环境变量")
    headers: dict[str, str] = Field(default_factory=dict, description="自定义请求头")
    params: dict[str, str] = Field(
        default_factory=lambda: {"LAB_JSON": "1"}, description="自定义 GET 参数"
    )


class BookingConfig(BaseModel):
    """预约行为配置。"""

    max_trials: int = Field(default=5, ge=1, le=100, description="最大重试次数")
    retry_delay: float = Field(default=1.0, ge=0.0, le=60.0, description="重试间隔秒数")
    dry_run: bool = Field(default=False, description="预览模式 (不实际提交)")


class LoggingConfig(BaseModel):
    """日志配置。"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="日志级别"
    )
    file: str = Field(default="booking.log", description="日志文件路径")


class PlansConfig(BaseModel):
    """方案持久化配置。"""

    file: str = Field(default="plans.yaml", description="YAML 方案文件路径")


class NotificationConfig(BaseModel):
    """通知配置。"""

    wechat_webhook: str | None = Field(default=None, description="微信 Webhook URL")
    log_file: str = Field(default="booking.log", description="通知日志文件")


class StrategyConfig(BaseModel):
    """座位选择策略配置。"""

    type: Literal["fixed", "random", "weekday"] = Field(default="fixed", description="策略类型")
    random_range: tuple[int, int] = Field(default=(1, 500), description="随机策略座位号范围")
    preferred_seats: list[str] = Field(default_factory=list, description="偏好座位号列表")
    preferred_attempts: int = Field(default=3, ge=1, le=20, description="偏好座位优先尝试次数")


# =============================================================================
# 主 Settings 类
# =============================================================================


class Settings(BaseSettings):
    """项目统一配置。

    用法::

        settings = Settings.from_yaml("config.yaml")
        settings = settings.with_cli_overrides(auth__cookie="xxx")
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="HDU_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    api: APIUrls = Field(default_factory=APIUrls)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    http: HTTPConfig = Field(default_factory=HTTPConfig)
    booking: BookingConfig = Field(default_factory=BookingConfig)
    logging_cfg: LoggingConfig = Field(default_factory=LoggingConfig, alias="logging")
    plans: PlansConfig = Field(default_factory=PlansConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    # --- 顶层快捷访问 ---

    @property
    def urls(self) -> dict[str, str]:
        # model_dump() 返回 dict[str, Any]，但 APIUrls 所有字段均为 str
        return cast(dict[str, str], self.api.model_dump())

    # --- 工厂方法 ---

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        """从 YAML 文件加载配置，作为最低优先级基础。"""
        import yaml as _yaml

        p = Path(path).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            return cls()
        data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        # _flatten_yaml 产生 "auth__uid" 格式的 flat key；
        # pydantic-settings 的 env_nested_delimiter 仅适用于环境变量，
        # 不适用于构造函数 kwargs，因此需要还原为嵌套 dict。
        return cls(**_unflatten_keys(_flatten_yaml(data)))

    @classmethod
    def from_cli(cls, **overrides: Any) -> Settings:
        """从 CLI 参数创建，覆盖任何已存在的值。

        支持双下划线分隔的嵌套 key，如 ``auth__uid="xxx"``
        等价于 ``{"auth": {"uid": "xxx"}}``。
        """
        clean = {k: v for k, v in overrides.items() if v is not None}
        return cls(**_unflatten_keys(clean))

    def with_cli_overrides(self, **overrides: Any) -> Settings:
        """返回新 Settings，应用 CLI 覆盖。

        支持双下划线分隔的嵌套 key，如 ``booking__max_trials=20``
        等价于 ``{"booking": {"max_trials": 20}}``。
        """
        clean = {k: v for k, v in overrides.items() if v is not None}
        data = self.model_dump()
        nested = _unflatten_keys(clean)
        _deep_update(data, nested)
        return self.__class__(**data)


# =============================================================================
# 内部工具
# =============================================================================


# YAML 旧 key → Settings 模型 key 的映射
_YAML_KEY_MAP = {
    "request": "http",
    "user_info": "auth",
    "session": "http",
}


def _flatten_yaml(data: dict) -> dict:
    """将嵌套 YAML 扁平化为 pydantic-settings 可用的格式。

    将旧版 YAML key (如 request.timeout, user_info.uid) 映射到
    新版 Settings 模型 key (如 http.timeout, auth.uid)。
    """
    result: dict = {}
    for key, value in data.items():
        # 映射旧 key 到新 key
        mapped_key = _YAML_KEY_MAP.get(key, key)
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                result[f"{mapped_key}__{sub_key}"] = sub_value
        else:
            result[mapped_key] = value
    return result


def _unflatten_keys(data: dict) -> dict:
    """将带 __ 分隔符的 flat key 转为嵌套 dict。

    如 ``{"booking__max_trials": 20}`` → ``{"booking": {"max_trials": 20}}``。
    """
    result: dict = {}
    for key, value in data.items():
        if "__" in key:
            head, _, tail = key.partition("__")
            if head not in result:
                result[head] = {}
            result[head][tail] = value
        else:
            result[key] = value
    return result


def _deep_update(base: dict, overrides: dict) -> None:
    """递归更新嵌套 dict。"""
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局单例 Settings。"""
    yaml_path = os.environ.get("HDU_CONFIG", "config.yaml")
    return Settings.from_yaml(yaml_path)
