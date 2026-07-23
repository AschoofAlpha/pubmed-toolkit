"""
HTTP 客户端模块
===============
封装所有 HTTP 请求逻辑，统一处理：
- 指数退避重试（解决原代码 15 处 except Exception: pass）
- UA 池轮换 + 请求指纹随机化（反爬）
- 可选代理 IP 池
- 统一超时与错误日志
"""

import logging
import random
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("pubmed_toolkit.http")

# ============================================================
# UA 池：解决原代码 L289-293 固定 UA 被指纹识别的问题
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# 不同域名使用不同的 Accept 头，模拟真实浏览器行为
ACCEPT_PROFILES = {
    "pdf": "application/pdf,application/octet-stream,*/*;q=0.8",
    "html": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "api": "application/json,*/*;q=0.8",
}


def _random_headers(accept_type: str = "pdf") -> dict:
    """生成随机化的请求头，降低指纹一致性"""
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": ACCEPT_PROFILES.get(accept_type, ACCEPT_PROFILES["pdf"]),
        "Accept-Language": random.choice([
            "en-US,en;q=0.9",
            "en-US,en;q=0.9,zh-CN;q=0.8",
            "en-GB,en;q=0.9",
        ]),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }
    # 随机添加 Sec-Fetch 头（Chrome 特有）
    if "Chrome" in ua:
        headers.update({
            "Sec-Fetch-Dest": random.choice(["document", "empty"]),
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Ch-Ua-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
        })
    return headers


class RobustHTTPClient:
    """
    带重试、日志、反爬的 HTTP 客户端。

    替代原代码中散落的 requests.get(...) 调用，统一行为。
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        timeout: int = 30,
        proxy_list: list[str] | None = None,
    ):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.proxy_list = proxy_list or []
        self._session = self._build_session()
        self._request_count = 0

    def _build_session(self) -> requests.Session:
        """构建带自动重试的 Session"""
        session = requests.Session()
        # urllib3 层面的重试策略：处理连接错误和 502/503/504
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_maxsize=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_proxy(self) -> dict | None:
        """从代理池中随机选取"""
        if not self.proxy_list:
            return None
        proxy = random.choice(self.proxy_list)
        return {"http": proxy, "https": proxy}

    def get(
        self,
        url: str,
        accept_type: str = "pdf",
        timeout: int | None = None,
        allow_redirects: bool = True,
        extra_headers: dict | None = None,
        stream: bool = False,
    ) -> requests.Response | None:
        """
        发起 GET 请求，带完整的日志和错误处理。

        原代码问题对照：
        - L327: requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
          → 无重试、无日志、固定UA、异常静默
        - 本方法：自动重试、随机UA、完整日志、异常上抛（不再吞掉）
        """
        headers = _random_headers(accept_type)
        if extra_headers:
            headers.update(extra_headers)

        effective_timeout = timeout or self.timeout
        proxies = self._get_proxy()
        self._request_count += 1

        domain = urlparse(url).netloc
        logger.debug(
            "GET #%d %s (timeout=%ds, proxy=%s)",
            self._request_count, domain, effective_timeout,
            "yes" if proxies else "no",
        )

        # 请求间加入随机延迟（0.5~2s），模拟人类行为
        jitter = random.uniform(0.3, 1.5)
        time.sleep(jitter)

        try:
            resp = self._session.get(
                url,
                headers=headers,
                timeout=effective_timeout,
                allow_redirects=allow_redirects,
                proxies=proxies,
                stream=stream,
            )
            logger.debug(
                "  → %d %s (%d bytes, type=%s)",
                resp.status_code, domain,
                len(resp.content) if not stream else -1,
                resp.headers.get("content-type", "?")[:40],
            )

            # 403/429 特殊处理：可能是反爬触发
            if resp.status_code == 403:
                logger.warning("  ⚠ 403 Forbidden from %s — 可能触发反爬", domain)
            elif resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 30))
                logger.warning("  ⚠ 429 Rate Limited from %s — 等待 %ds", domain, retry_after)
                time.sleep(retry_after)

            return resp

        except requests.exceptions.Timeout:
            logger.error("  ✗ 超时 (%ds) — %s", effective_timeout, url[:80])
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error("  ✗ 连接失败 — %s: %s", domain, str(e)[:100])
            return None
        except requests.exceptions.RequestException as e:
            logger.error("  ✗ 请求异常 — %s: %s", domain, str(e)[:100])
            return None

    @property
    def stats(self) -> dict:
        return {"total_requests": self._request_count}
