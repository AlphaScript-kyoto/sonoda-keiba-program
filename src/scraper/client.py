"""netkeiba への HTTP リクエスト。"""

import random
import re
import time
from typing import Dict, List, Optional

import requests

from config.settings import (
    NAR_BASE_URL,
    REQUEST_INTERVAL_MAX_SEC,
    REQUEST_INTERVAL_MIN_SEC,
    REQUEST_MAX_PER_HOUR,
    REQUEST_TIMEOUT_SEC,
    URL_RESULT,
    USER_AGENT,
)

_last_request_at: float = 0.0
_next_interval_sec: float = 0.0
_MAX_RETRIES = 3
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_HOURLY_WINDOW_SEC = 3600.0


class NetkeibaBlockedError(requests.HTTPError):
    """通信制限等で netkeiba が HTTP 400 を返した場合。"""


class _HourlyRateLimiter:
    """直近1時間のリクエスト数を制限する。"""

    def __init__(self, max_per_hour: int) -> None:
        self._max = max_per_hour
        self._times: List[float] = []

    def wait_if_needed(self) -> None:
        now = time.monotonic()
        self._times = [t for t in self._times if now - t < _HOURLY_WINDOW_SEC]
        if len(self._times) < self._max:
            return

        sleep_for = _HOURLY_WINDOW_SEC - (now - self._times[0]) + 0.1
        if sleep_for > 0:
            print(
                f"  待機: 1時間リクエスト上限 ({self._max}/h) ... {sleep_for:.0f}秒",
                flush=True,
            )
            time.sleep(sleep_for)

        now = time.monotonic()
        self._times = [t for t in self._times if now - t < _HOURLY_WINDOW_SEC]

    def record(self) -> None:
        self._times.append(time.monotonic())


_hourly_limiter = _HourlyRateLimiter(REQUEST_MAX_PER_HOUR)


def build_request_headers(*, referer: Optional[str] = None) -> Dict[str, str]:
    """ブラウザに近いリクエストヘッダーを返す。"""
    return {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer or f"{NAR_BASE_URL}/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _pick_interval() -> float:
    return random.uniform(REQUEST_INTERVAL_MIN_SEC, REQUEST_INTERVAL_MAX_SEC)


def _normalize_charset_name(name: str) -> str:
    """Content-Type / meta の charset 名を Python codec 名に揃える。"""
    key = name.strip().strip('"').strip("'").lower().replace("_", "-")
    aliases = {
        "eucjp": "euc-jp",
        "euc-jp": "euc-jp",
        "utf8": "utf-8",
        "utf-8": "utf-8",
        "shift-jis": "cp932",
        "shift_jis": "cp932",
        "sjis": "cp932",
        "windows-31j": "cp932",
    }
    return aliases.get(key, key)


def _charset_from_content_type(content_type: str) -> str | None:
    for part in content_type.split(";"):
        part = part.strip().lower()
        if part.startswith("charset="):
            return _normalize_charset_name(part.split("=", 1)[1])
    return None


def _charset_from_html_head(content: bytes) -> str | None:
    head = content[:8192].decode("ascii", errors="ignore").lower()
    for pattern in (
        r'<meta[^>]+charset\s*=\s*["\']?([\w-]+)',
        r'charset\s*=\s*["\']?([\w-]+)',
    ):
        m = re.search(pattern, head)
        if m:
            return _normalize_charset_name(m.group(1))
    return None


def _detect_encoding(response: requests.Response) -> str:
    """netkeiba の文字コードを判定（Content-Type / meta を優先。旧ページは EUC-JP）。"""
    content_type = (response.headers.get("Content-Type") or "").lower()
    from_header = _charset_from_content_type(content_type)
    if from_header:
        return from_header

    from_meta = _charset_from_html_head(response.content)
    if from_meta:
        return from_meta

    if "euc-jp" in content_type or "eucjp" in content_type:
        return "euc-jp"

    head = response.content[:8192].decode("ascii", errors="ignore").lower()
    if "euc-jp" in head or "euc_jp" in head:
        return "euc-jp"

    return response.apparent_encoding or "utf-8"


def fetch_html(url: str, *, respect_interval: bool = True) -> str:
    """URL から HTML を取得する。"""
    global _last_request_at, _next_interval_sec

    last_error: Optional[requests.RequestException] = None
    for attempt in range(_MAX_RETRIES):
        _hourly_limiter.wait_if_needed()

        if respect_interval and _last_request_at > 0:
            elapsed = time.monotonic() - _last_request_at
            if elapsed < _next_interval_sec:
                time.sleep(_next_interval_sec - elapsed)

        try:
            response = requests.get(
                url,
                headers=build_request_headers(),
                timeout=REQUEST_TIMEOUT_SEC,
            )
            _hourly_limiter.record()

            if response.status_code == 400:
                raise NetkeibaBlockedError(
                    f"400 Client Error: 通信制限の可能性 ({response.url})",
                    response=response,
                )
            if response.status_code in _RETRY_STATUS_CODES:
                raise requests.HTTPError(
                    f"{response.status_code} Client Error",
                    response=response,
                )
            response.raise_for_status()
            response.encoding = _detect_encoding(response)
            _last_request_at = time.monotonic()
            _next_interval_sec = _pick_interval()
            return response.text
        except NetkeibaBlockedError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < _MAX_RETRIES:
                time.sleep(REQUEST_INTERVAL_MAX_SEC * (attempt + 1))

    assert last_error is not None
    raise last_error


def fetch_race_result_html(race_id: str) -> str:
    """レース結果ページの HTML を取得する。"""
    url = URL_RESULT.format(race_id=race_id)
    return fetch_html(url)


def build_result_url(race_id: str) -> str:
    return URL_RESULT.format(race_id=race_id)
