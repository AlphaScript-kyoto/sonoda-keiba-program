"""オフライン用パーサテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.parser import parse_race_meta, parse_race_result

FIXTURE = ROOT / "tests" / "fixtures" / "result_202650052201.html"


def test_parse_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    meta = parse_race_meta(html)
    assert meta["distance"] == "1400m"
    assert meta["track"] == "重"
    assert meta["direction"] == "右"
    assert meta["weather"] == "晴"
    assert meta["head_count"] == "10"
    assert "C3" in meta["race_class"]

    rows = parse_race_result(html, "202650052201")
    assert len(rows) >= 8
    assert rows[0]["finish"] == 1
    assert rows[0]["horse_id"] == "2018110078"
    assert rows[0]["waku"] == "8"
    assert rows[0]["umaban"] == "9"
    assert rows[0]["margin"] == ""
    assert rows[0]["sex_age"] == "牝8"
    assert rows[0]["race_time"] == "1:34.8"
    assert rows[0]["last_3f"] == "41.8"

    row3 = next(r for r in rows if r["horse_name"] == "メイショウヨウホウ")
    assert row3["odds"] == "42.4"
    assert row3["margin"] == "1.3/4"

    row4 = next(r for r in rows if r["horse_name"] == "ニシノウインド")
    assert row4["last_3f"] == "44.1"
    assert row4["waku"] == "6"
    assert row4["umaban"] == "6"
    assert rows[0]["jockey_id"] == "00894"
    assert rows[0]["trainer_id"] == "a0242"


if __name__ == "__main__":
    test_parse_fixture()
    print("ok")
