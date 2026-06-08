"""払戻パースのテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.payback import parse_race_payback

FIXTURE = ROOT / "tests" / "fixtures" / "result_202650052201.html"


def test_parse_race_payback():
    html = FIXTURE.read_text(encoding="utf-8")
    pb = parse_race_payback(html, "202650052201")
    assert pb is not None
    assert pb.tansho["9"] == 170
    assert pb.fukusho["9"] == 120
    assert pb.fuku3_umaban == ("3", "7", "9")
    assert pb.fuku3_yen == 4160
    assert pb.tan3_umaban == ("9", "3", "7")
    assert pb.tan3_yen == 10920
    assert pb.wide["3-9"] == 390
    assert pb.wide["7-9"] == 1020
    assert pb.wide["3-7"] == 3030
    assert pb.umaren["3-9"] == 610
    assert pb.umatan["9-3"] == 980
