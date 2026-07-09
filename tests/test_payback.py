"""払戻パースのテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.payback import (
    RacePayback,
    finish_top3_from_payback,
    parse_race_payback,
)

FIXTURE = ROOT / "tests" / "fixtures" / "result_202650052201.html"


def _make_payback(*, tan3=("", "", ""), fuku3=("", "", "")) -> RacePayback:
    return RacePayback(
        race_id="x",
        tansho={},
        fukusho={},
        fuku3_umaban=fuku3,
        fuku3_yen=0,
        tan3_umaban=tan3,
        tan3_yen=0,
    )


def test_finish_top3_prefers_tan3():
    pb = _make_payback(tan3=("9", "3", "7"), fuku3=("3", "7", "9"))
    assert finish_top3_from_payback(pb) == ("9", "3", "7")


def test_finish_top3_falls_back_to_fuku3():
    pb = _make_payback(tan3=("", "", ""), fuku3=("3", "7", "9"))
    assert finish_top3_from_payback(pb) == ("3", "7", "9")


def test_finish_top3_none_when_unavailable():
    assert finish_top3_from_payback(None) is None
    assert finish_top3_from_payback(_make_payback()) is None


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
