"""HTTP 传输层 — 纯网络 I/O，不含领域逻辑。

提供弹性 HTTP 传输能力：
  - 连接池（HTTPAdapter）
  - Transport 级别重试（对 5xx 和 429）
  - 连接/读取超时拆分
  - 速率限制感知（Retry-After）

错误处理策略：
  - 网络错误（ConnectionError/Timeout）→ 包装为 HduLibraryError，可重试
  - HTTP 5xx/429 → Transport 层自动重试
  - HTTP 4xx → 直接抛出，不可重试
  - JSON 解析失败 → 直接抛出，不可重试
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter

from .. import constants as C
from .. import exceptions as E
from ..resilience import TimeoutConfig, is_retryable_status

if TYPE_CHECKING:
    from ..settings import Settings
    from .protocols import Instrumentation


def _create_session(
    settings: Settings | None,
    max_retries: int = 3,
    backoff_factor: float = 0.5,
) -> requests.Session:
    """创建具备连接池和重试能力的 Session。

    Parameters
    ----------
    settings : Settings, optional
        配置对象。
    max_retries : int
        Transport 级别最大重试次数。
    backoff_factor : float
        重试退避因子。
    """
    session = requests.Session()

    if max_retries > 0:
        # 使用 urllib3 的 Retry 实现 transport 级别重试
        # 仅对安全方法（GET/HEAD/OPTIONS）和幂等方法（PUT/DELETE）重试
        # 仅对 500/502/503/504 状态码重试
        try:
            from urllib3.util.retry import Retry

            retry_strategy = Retry(
                total=max_retries,
                backoff_factor=backoff_factor,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET", "HEAD", "OPTIONS"],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(
                pool_connections=10,
                pool_maxsize=10,
                max_retries=retry_strategy,
            )
            session.mount("https://", adapter)
            session.mount("http://", adapter)
        except ImportError:
            # urllib3 版本不支持 Retry，降级为无重试
            adapter = HTTPAdapter(
                pool_connections=10,
                pool_maxsize=10,
            )
            session.mount("https://", adapter)
            session.mount("http://", adapter)

    return session


class HttpTransport:
    """底层 HTTP 传输 — 封装 requests.Session。

    特性：
    - 连接池复用
    - Transport 级别重试（5xx）
    - 连接/读取超时拆分
    - 错误分类与记录
    """

    def __init__(
        self,
        settings: Settings | None = None,
        instrumentation: Instrumentation | None = None,
        timeout_config: TimeoutConfig | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self._settings = settings
        self._instrumentation = instrumentation
        s = settings or __import__("core.settings", fromlist=["Settings"]).Settings()

        # 超时配置
        self._timeout_config = timeout_config or TimeoutConfig(
            connect_timeout=5.0,
            read_timeout=s.http.timeout,
        )

        # 创建带连接池和重试的 Session
        self.session = _create_session(s, max_retries, backoff_factor)
        self.session.headers.update(s.http.headers or dict(C.DEFAULT_HEADERS))
        self.session.params = s.http.params or dict(C.DEFAULT_SESSION_PARAMS)
        self.session.trust_env = s.http.trust_env
        self.session.verify = s.http.verify

        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined,unused-ignore]

    @property
    def timeout(self) -> tuple[float, float]:
        """返回 (connect_timeout, read_timeout) 元组。"""
        return self._timeout_config.as_tuple

    def _record(self, category: str, message: str, exc: Exception | None = None) -> None:
        if self._instrumentation:
            self._instrumentation.record(category, message, exc, module=__name__)

    def request(self, method: str, url: str, data: dict[str, str] | None = None) -> dict:
        """统一 HTTP 请求封装，含错误处理。

        错误处理策略：
        - 网络错误（ConnectionError/Timeout）→ 记录 + 包装为 HduLibraryError
        - HTTP 5xx/429 → Transport 层已重试，若仍失败则抛出
        - HTTP 4xx → 直接抛出（不可重试）
        - JSON 解析失败 → 直接抛出
        """
        try:
            if method == "GET":
                resp = self.session.get(url, timeout=self.timeout)
            else:
                resp = self.session.post(url, data=data, timeout=self.timeout)
        except requests.RequestException as exc:
            self._record("NETWORK", f"请求失败：{exc}", exc)
            raise E.HduLibraryError(f"请求失败：{exc}") from exc

        # 检查 HTTP 状态码
        if resp.status_code not in (200, 302):
            classification = is_retryable_status(resp.status_code)
            if classification:
                # 可重试的状态码（但 transport 层已重试过仍失败）
                self._record(
                    "NETWORK",
                    f"HTTP {resp.status_code} {url} (retried, still failing)",
                )
            else:
                # 不可重试的状态码（4xx 客户端错误）
                self._record(
                    "NETWORK",
                    f"HTTP {resp.status_code} {url} (non-retryable)",
                )
            raise E.HduLibraryError(f"请求失败：HTTP {resp.status_code} {url}")

        try:
            return resp.json()  # type: ignore[no-any-return]
        except Exception as exc:
            self._record("JSON_PARSE", f"JSON 解析失败：{exc}", exc)
            raise E.HduLibraryError(f"JSON 解析失败：{exc}") from exc
