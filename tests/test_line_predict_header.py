"""T-10 LINE predict header tests."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.race_day_notify import build_line_predict_header


def test_build_line_predict_header_full():
    plan = SimpleNamespace(race_no=3, post_time="11:10", race_name="C3\u4e09")
    assert build_line_predict_header(plan) == "3R\u300011:10\u767a\u8d70\u3000C3\u4e09"


def test_build_line_predict_header_post_only():
    plan = SimpleNamespace(race_no=1, post_time="10:40", race_name="")
    assert build_line_predict_header(plan) == "1R\u300010:40\u767a\u8d70"
