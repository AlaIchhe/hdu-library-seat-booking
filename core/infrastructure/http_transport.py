"""HTTP 传输层 — 纯网络 I/O，不含领域逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests

from .. import constants as C
from .. import exceptions as E
from ..types import Json

if TYPE_CHECKING:
    from ..settings import Settings
    from .protocols import Instrumentation


class HttpTransport:
    """底层 HTTP 传输 — 封装 requests.Session。"""

    def __init__(
        self,
        settings: Settings | None = None,
        instrumentation: Instrumentation | None = None,
    ):
        self._settings = settings
        self._instrumentation = instrumentation
        s = settings or __import__("core.settings", fromlist=["Settings"]).Settings()

        self.timeout = s.http.timeout
        self.session = requests.Session()
        self.session.headers.update(s.http.headers or dict(C.DEFAULT_HEADERS))
        self.session.params = s.http.params or dict(C.DEFAULT_SESSION_PARAMS)
        self.session.trust_env = s.http.trust_env
        self.session.verify = s.http.verify

        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined,unused-ignore]

    def _record(self, category: str, message: str, exc: Exception | None = None) -> None:
        if self._instrumentation:
            self._instrumentation.record(category, message, exc, module=__name__)

    def request(self, method: str, url: str, data: dict[str, str] | None = None) -> Json:
        """统一 HTTP 请求封装，含错误处理。"""
        try:
            if method == "GET":
                resp = self.session.get(url, timeout=self.timeout)
            else:
                resp = self.session.post(url, data=data, timeout=self.timeout)
        except requests.RequestException as exc:
            self._record("NETWORK", f"请求失败：{exc}", exc)
            raise E.HduLibraryError(f"请求失败：{exc}") from exc

        if resp.status_code not in (200, 302):
            self._record("NETWORK", f"HTTP {resp.status_code} {url}")
            raise E.HduLibraryError(f"请求失败：HTTP {resp.status_code} {url}")

        try:
            return resp.json()  # type: ignore[no-any-return]
        except Exception as exc:
            self._record("JSON_PARSE", f"JSON 解析失败：{exc}", exc)
            raise E.HduLibraryError(f"JSON 解析失败：{exc}") from exc
