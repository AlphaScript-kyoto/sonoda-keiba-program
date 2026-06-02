import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.race_schedule import is_race_started, race_post_datetime
from src.scraper.parser import parse_race_meta
from src.scraper.shutuba import parse_shutuba

FIXTURE = ROOT / "tests" / "fixtures" / "shutuba_202650052901.html"


def test_parse_post_time_from_shutuba_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    meta = parse_race_meta(html)
    assert meta["post_time"] == "14:30"
    rows = parse_shutuba(html, "202650052901")
    assert rows[0]["post_time"] == "14:30"


def test_is_race_started():
    post = race_post_datetime("20260603", "14:30")
    assert post == datetime(2026, 6, 3, 14, 30)
    assert not is_race_started("20260603", "14:30", now=datetime(2026, 6, 3, 14, 29))
    assert is_race_started("20260603", "14:30", now=datetime(2026, 6, 3, 14, 30))
    assert is_race_started("20260603", "14:30", now=datetime(2026, 6, 3, 15, 0))
    assert not is_race_started("20260603", "", now=datetime(2026, 6, 3, 15, 0))