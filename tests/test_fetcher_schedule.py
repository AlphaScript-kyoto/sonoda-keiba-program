from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.scraper.fetcher import resolve_race_ids_for_fetch

def test_resolve_race_ids_includes_schedule(monkeypatch):
    monkeypatch.setattr(
        "src.scraper.fetcher._race_ids_from_schedule",
        lambda _date: ["202650062601", "202650062612"],
    )
    monkeypatch.setattr(
        "src.scraper.fetcher.list_race_ids_for_date",
        lambda _date: ["202650062601", "202650062607"],
    )
    ids = resolve_race_ids_for_fetch("20260626")
    assert ids == ["202650062601", "202650062607", "202650062612"]
