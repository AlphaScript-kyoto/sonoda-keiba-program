"""HTTP クライアントのテスト。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.client import (
    NetkeibaBlockedError,
    _cjk_score,
    _decode_response_bytes,
    _detect_encoding,
    build_request_headers,
    fetch_html,
)


def test_build_request_headers():
    headers = build_request_headers()
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://nar.netkeiba.com/"
    assert "ja" in headers["Accept-Language"]
    assert "text/html" in headers["Accept"]


def test_detect_encoding_prefers_utf8_content_type():
    response = MagicMock()
    response.headers = {"Content-Type": "text/html; charset=UTF-8"}
    response.content = (
        b"<html><head><meta charset=EUC-JP></head>"
        b"<body><a href='/horse/1/'>"
        b"\xe3\x82\xb5\xe3\x83\x8b\xe3\x83\xbc\xe3\x82\xa2\xe3\x83\xbc\xe3\x83\xab"
        b"</a></body></html>"
    )
    response.url = "https://nar.netkeiba.com/race/result.html?race_id=1"
    assert _detect_encoding(response) == "utf-8"


def test_detect_encoding_uses_meta_euc_jp_when_no_header():
    response = MagicMock()
    response.headers = {"Content-Type": "text/html"}
    # EUC-JP: サニー (example bytes minimal - use fixture style)
    response.content = (
        b"<html><head><meta charset=EUC-JP></head><body></body></html>"
    )
    response.url = "https://nar.netkeiba.com/race/result.html?race_id=1"
    assert _detect_encoding(response) == "euc-jp"


def test_decode_response_bytes_prefers_valid_japanese():
    # UTF-8 label but CP932 body (odds page pattern)
    body = (
        b"<html><head><meta charset=UTF-8></head><body>"
        b"<td class=\"Horse_Name\">\x83G\x83C\x83V\x83\x93\x83}\x83V\x81\x5b\x83\x93</td>"
        b"</body></html>"
    )
    text = _decode_response_bytes(body, "utf-8")
    assert "エイシンマシーン" in text
    assert _cjk_score(text) >= 5


def test_fetch_html_raises_on_400():
    response = MagicMock()
    response.status_code = 400
    response.url = "https://nar.netkeiba.com/race/result.html?race_id=1"

    with patch("src.scraper.client.requests.get", return_value=response):
        try:
            fetch_html("https://nar.netkeiba.com/race/result.html?race_id=1")
            assert False, "expected NetkeibaBlockedError"
        except NetkeibaBlockedError:
            pass


if __name__ == "__main__":
    test_build_request_headers()
    test_fetch_html_raises_on_400()
    print("ok")
