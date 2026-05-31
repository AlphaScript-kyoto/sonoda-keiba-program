"""脚質・コーナーパースのテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.running_style import (
    classify_style_from_corner_avg,
    parse_corner_positions,
    parse_kyakushitsu_from_shutuba,
    parse_race_style_from_result,
)

RESULT_FIXTURE = ROOT / "tests" / "fixtures" / "result_202650052201.html"
SHUTUBA_FIXTURE = ROOT / "tests" / "fixtures" / "shutuba_202650052901.html"


def test_parse_corner_positions():
    html = RESULT_FIXTURE.read_text(encoding="utf-8")
    corners = parse_corner_positions(html)
    assert "9" in corners
    assert corners["9"][1] == 3
    assert corners["9"][4] == 1


def test_parse_race_style_from_result():
    html = RESULT_FIXTURE.read_text(encoding="utf-8")
    data = parse_race_style_from_result(html, "202650052201")
    assert data is not None
    assert data.horses["9"].running_style in STYLE_LABELS


def test_parse_kyakushitsu_from_shutuba():
    html = SHUTUBA_FIXTURE.read_text(encoding="utf-8")
    kyaku = parse_kyakushitsu_from_shutuba(html)
    assert kyaku.get("9") == "逃"
    assert kyaku.get("1") == "差"


def test_classify_style():
    assert classify_style_from_corner_avg(1.5) == "逃"
    assert classify_style_from_corner_avg(4.0) == "先"
    assert classify_style_from_corner_avg(6.0) == "差"
    assert classify_style_from_corner_avg(10.0) == "追"


STYLE_LABELS = ("逃", "先", "差", "追")

if __name__ == "__main__":
    test_parse_corner_positions()
    test_parse_race_style_from_result()
    test_parse_kyakushitsu_from_shutuba()
    test_classify_style()
    print("ok")
