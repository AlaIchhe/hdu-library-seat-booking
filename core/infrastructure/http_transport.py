"""HTTP 传输层 — 纯网络 I/O，不含领域逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests

from .. import constants as C
from .. import exceptions as E

if TYPE_CHECKING:
    from .protocols import Instrumentation


class HttpTransport:
    """底层 HTTP 传输 — 封装 requests.Session。"""

    def __init__(
        self,
        config: dict | None = None,
        timeout: int | None = None,
        instrumentation: Instrumentation | None = None,
    ):
        self.config = config or {}
        self.timeout = int(
            (self.config.get("request") or {}).get("timeout") or timeout or C.DEFAULT_TIMEOUT
        )
        self._instrumentation = instrumentation

        session_cfg = self.config.get("session") or {}
        self.session = requests.Session()
        self.session.headers.update(session_cfg.get("headers") or dict(C.DEFAULT_HEADERS))
        self.session.params = session_cfg.get("params") or dict(C.DEFAULT_SESSION_PARAMS)
        self.session.trust_env = bool(session_cfg.get("trust_env", False))
        self.session.verify = bool(session_cfg.get("verify", False))

        requests.packages.urllib3.disable_warnings()

    def _record(self, category: str, message: str, exc: Exception | None = None) -> None:
        if self._instrumentation:
            self._instrumentation.record(category, message, exc, module=__name__)

    def request(self, method: str, url: str, data: dict | None = None) -> dict:
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
