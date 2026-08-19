"""T-10 notify / HTTP transient retry tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import requests

from src.predictor.race_day_notify import (
    LINE_NOTIFY_REWAKE_SEC,
    next_line_notify_retry_wake,
)
from src.scraper.client import (
    NetkeibaBlockedError,
    fetch_html,
    is_transient_network_error,
)
from src.scraper.race_snapshots import CaptureJob


def test_is_transient_network_error_detects_dns():
    exc = requests.ConnectionError(
        "HTTPSConnectionPool(host='nar.netkeiba.com', port=443): "
        "Max retries exceeded with url: /race/shutuba.html?race_id=1 "
        "(Caused by NameResolutionError(\"Failed to resolve 'nar.netkeiba.com'\"))"
    )
    assert is_transient_network_error(exc) is True


def test_is_transient_network_error_ignores_netkeiba_block():
    resp = MagicMock()
    resp.status_code = 400
    resp.url = "https://nar.netkeiba.com/"
    exc = NetkeibaBlockedError("400", response=resp)
    assert is_transient_network_error(exc) is False


def test_fetch_html_retries_connection_error_then_succeeds():
    ok = MagicMock()
    ok.status_code = 200
    ok.headers = {"Content-Type": "text/html; charset=UTF-8"}
    ok.content = b"<html><body>\xe3\x81\x82</body></html>"
    ok.url = "https://nar.netkeiba.com/x"
    ok.raise_for_status = MagicMock()

    calls = {"n": 0}

    def _get(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("Failed to resolve host")
        return ok

    with (
        patch("src.scraper.client.requests.get", side_effect=_get),
        patch("src.scraper.client.time.sleep"),
        patch("src.scraper.client._hourly_limiter") as limiter,
    ):
        limiter.wait_if_needed = MagicMock()
        limiter.record = MagicMock()
        text = fetch_html("https://nar.netkeiba.com/x", respect_interval=False)

    assert "\u3042" in text
    assert calls["n"] == 3


def test_next_line_notify_retry_wake_when_pending():
    schedule = {
        "races": [
            {
                "race_id": "202650073005",
                "race_no": 5,
                "post_time": "12:45",
                "race_name": "C2",
            }
        ]
    }
    now = datetime(2026, 7, 30, 12, 36, 0)
    job = CaptureJob(
        race_id="202650073005",
        race_no=5,
        post_time="12:45",
        race_name="C2",
        minutes_before=10,
        label="t_minus_10",
    )
    with patch(
        "src.predictor.race_day_notify.due_line_notify_jobs",
        return_value=[job],
    ):
        wake = next_line_notify_retry_wake(
            "20260730",
            schedule,
            now=now,
            rewake_sec=LINE_NOTIFY_REWAKE_SEC,
        )
    assert wake == now + timedelta(seconds=LINE_NOTIFY_REWAKE_SEC)


def test_next_line_notify_retry_wake_none_when_empty():
    now = datetime(2026, 7, 30, 12, 36, 0)
    with patch(
        "src.predictor.race_day_notify.due_line_notify_jobs",
        return_value=[],
    ):
        wake = next_line_notify_retry_wake(
            "20260730",
            {"races": []},
            now=now,
        )
    assert wake is None
