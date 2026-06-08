"""horse_profile parser tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.horse_profile import parse_horse_profile

FIXTURE = ROOT / "tests" / "fixtures" / "horse_2018110078.html"


def test_parse_horse_profile_career_stats():
    html = FIXTURE.read_text(encoding="utf-8")
    entry = parse_horse_profile(html, "2018110078")
    assert entry.career_runs == 78
    assert entry.career_wins == 5
    assert entry.career_seconds == 8
    assert entry.career_thirds == 4
    assert entry.career_outs == 61
