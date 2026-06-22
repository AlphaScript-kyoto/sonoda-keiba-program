"""Off-day LINE message tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.race_day_notify import build_no_race_line_message


def test_build_no_race_line_message_with_next_date():
    msg = build_no_race_line_message("20260622", "20260624")
    assert msg == (
        "\u3010\u4f11\u5834\u306e\u304a\u77e5\u3089\u305b\u3011\n"
        "\u672c\u65e5\u306f\u4f11\u5834\u306e\u305f\u3081\u3001\u5712\u7530\u7af6\u99ac\u306e\u958b\u50ac\u306f\u3042\u308a\u307e\u305b\u3093\u3002\n"
        "\u6b21\u56de\u306e\u958b\u50ac\u65e5\u306f6\u670824\u65e5\u306b\u306a\u308a\u307e\u3059\u3002"
    )


def test_build_no_race_line_message_without_next_date():
    msg = build_no_race_line_message("20260622", None)
    assert "\u3010\u4f11\u5834\u306e\u304a\u77e5\u3089\u305b\u3011" in msg
    assert "\u73fe\u5728\u78ba\u5b9a\u3067\u304d\u3066\u304a\u308a\u307e\u305b\u3093" in msg
