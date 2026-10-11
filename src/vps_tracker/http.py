"""共享限速器：包括重试和重定向在内，同一商家请求起点至少间隔两秒。"""

import threading
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "VPS-Tracker/0.1 (+https://github.com/limail8866-prog/vps; daily price research)"


class Requester:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        interval: float = 2.0,
        attempts: int = 3,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if interval < 2 or attempts < 1:
            raise ValueError("请求间隔至少 2 秒，尝试次数至少 1 次")
        self.client = client
        self.interval = interval
        self.attempts = attempts
        self.clock, self.sleep = clock, sleep
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def _wait(self, url: str) -> None:
        # 同一注册域下的 www/app 等主机也共享限速（本项目商家均为 .com）。
        host = urlsplit(url).hostname or ""
        key = ".".join(host.split(".")[-2:])
        with self._lock:
            if key in self._last:
                remaining = self.interval - (self.clock() - self._last[key])
                if remaining > 0:
                    self.sleep(remaining)
            self._last[key] = self.clock()

    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        for attempt in range(self.attempts):
            try:
                current = url
                for redirect in range(6):
                    self._wait(current)
                    response = client.get(current, follow_redirects=False)
                    if response.is_redirect:
                        if redirect == 5:
                            raise httpx.TooManyRedirects(
                                "重定向超过 5 次", request=response.request
                            )
                        current = urljoin(current, response.headers["location"])
                        if urlsplit(current).scheme != "https":
                            raise ValueError("拒绝重定向到非 HTTPS 地址")
                        continue
                    response.raise_for_status()
                    return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    if status != 429 and not 500 <= status < 600:
                        raise
                if attempt == self.attempts - 1:
                    raise
                delay = float(2**attempt)
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        delay = max(
                            delay, min(60, float(exc.response.headers.get("retry-after", 0)))
                        )
                    except ValueError:
                        pass
                self.sleep(delay)
        raise RuntimeError("请求未完成")  # 防御性分支

    def get(self, url: str) -> httpx.Response:
        if urlsplit(url).scheme != "https":
            raise ValueError("仅支持 HTTPS")
        if self.client is not None:
            return self._get(self.client, url)
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(20.0, connect=10.0),
        ) as client:
            return self._get(client, url)


requester = Requester()
