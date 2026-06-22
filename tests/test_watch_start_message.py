"""Watch start LINE message tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.race_day_notify import build_watch_start_line_message


def test_build_watch_start_line_message():
    schedule = {
        "races": [
            {"race_no": 2, "post_time": "11:10"},
            {"race_no": 1, "post_time": "10:40"},
            {"race_no": 12, "post_time": "16:50"},
        ]
    }
    msg = build_watch_start_line_message("20260619", schedule)
    lines = msg.splitlines()
    assert lines[0] == "6\u670819\u65e5\u3000\u5712\u7530\u7af6\u99ac\u5834"
    assert lines[1] == "\u51683R"
    assert lines[3] == "\u5404\u30ec\u30fc\u30b910\u5206\u524d\u306b\u4e88\u60f3\u5370\u3092\u914d\u4fe1\u3057\u307e\u3059\u3002"
    assert lines[4] == "\u672c\u65e5\u3082\u5f35\u308a\u5207\u3063\u3066\u3044\u304d\u307e\u3057\u3087\u3046\uff01"
    assert lines[6] == "\u3010\u5404\u30ec\u30fc\u30b9\u51fa\u8d70\u6642\u9593\u3011"
    assert lines[7] == "1R\u300010:40"
    assert lines[8] == "2R\u300011:10"
    assert lines[9] == "12R\u300016:50"
