"""HTTP クライアントのテスト。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.client import NetkeibaBlockedError, build_request_headers, fetch_html


def test_build_request_headers():
    headers = build_request_headers()
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://nar.netkeiba.com/"
    assert "ja" in headers["Accept-Language"]
    assert "text/html" in headers["Accept"]


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
