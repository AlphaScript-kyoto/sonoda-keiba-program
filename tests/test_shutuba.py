"""出馬表パーサのオフラインテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.shutuba import has_shutuba_table, parse_shutuba

FIXTURE = ROOT / "tests" / "fixtures" / "shutuba_202650052901.html"


def test_parse_shutuba_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    assert has_shutuba_table(html)
    rows = parse_shutuba(html, "202650052901")
    assert len(rows) == 10
    assert rows[0]["horse_name"] == "グランディーヴァ"
    assert rows[0]["horse_id"] == "2021102932"
    assert rows[0]["umaban"] == "1"
    assert rows[0]["odds"] == "4.8"
    assert rows[2]["umaban"] == "3"
    assert rows[2]["odds"] == "80.0"
    empty = [r for r in rows if not str(r.get("odds", "")).strip()]
    assert not empty, f"missing odds: {empty}"


if __name__ == "__main__":
    test_parse_shutuba_fixture()
    print("ok")
