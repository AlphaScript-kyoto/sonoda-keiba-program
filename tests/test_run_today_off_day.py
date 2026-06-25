"""run_today off-day message tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_today import build_run_today_off_day_message


def test_build_run_today_off_day_message_with_next():
    msg = build_run_today_off_day_message("20260622", "20260624")
    assert msg == (
        "\u3010\u591c\u9593\u51e6\u7406\u3011\n"
        "6\u670822\u65e5\u306f\u4f11\u5834\u306e\u305f\u3081\u3001"
        "\u30c7\u30fc\u30bf\u53d6\u5f97\u30fb\u5b9f\u7e3e\u96c6\u8a08\u306f\u884c\u3044\u307e\u305b\u3093\u3067\u3057\u305f\u3002\n"
        "\u6b21\u56de\u958b\u50ac\u306f6\u670824\u65e5\u3067\u3059\u3002"
    )


def test_build_run_today_off_day_message_without_next():
    msg = build_run_today_off_day_message("20260622", None)
    assert "\u73fe\u5728\u78ba\u5b9a\u3067\u304d\u3066\u304a\u308a\u307e\u305b\u3093" in msg
