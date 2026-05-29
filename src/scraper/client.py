"""netkeiba への HTTP リクエスト。"""

import time
from typing import Optional

import requests

from config.settings import (
    REQUEST_INTERVAL_SEC,
    REQUEST_TIMEOUT_SEC,
    URL_RESULT,
    USER_AGENT,
)

_last_request_at: float = 0.0


def _detect_encoding(response: requests.Response) -> str:
    """nar.netkeiba 等 EUC-JP ページの文字コードを判定。"""
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "euc-jp" in content_type or "eucjp" in content_type:
        return "euc-jp"

    head = response.content[:8192].decode("ascii", errors="ignore").lower()
    if "euc-jp" in head or "euc_jp" in head:
        return "euc-jp"

    if "nar.netkeiba.com" in (response.url or ""):
        return "euc-jp"

    return response.apparent_encoding or "utf-8"


def fetch_html(url: str, *, respect_interval: bool = True) -> str:
    """URL から HTML を取得する。"""
    global _last_request_at

    if respect_interval:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < REQUEST_INTERVAL_SEC:
            time.sleep(REQUEST_INTERVAL_SEC - elapsed)

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()
    response.encoding = _detect_encoding(response)

    _last_request_at = time.monotonic()
    return response.text


def fetch_race_result_html(race_id: str) -> str:
    """レース結果ページの HTML を取得する。"""
    url = URL_RESULT.format(race_id=race_id)
    return fetch_html(url)


def build_result_url(race_id: str) -> str:
    return URL_RESULT.format(race_id=race_id)
