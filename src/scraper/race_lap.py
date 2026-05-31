"""レースラップタイムのパース。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from config.settings import DATA_PROCESSED_DIR
from src.scraper.client import NetkeibaBlockedError, fetch_race_result_html

LAP_CACHE_PATH = DATA_PROCESSED_DIR / "race_lap_cache.json"


def _lap_to_seconds(text: str) -> float:
    text = text.strip()
    if not text:
        return float("nan")
    if ":" in text:
        parts = text.split(":", 1)
        try:
            return int(parts[0]) * 60.0 + float(parts[1])
        except ValueError:
            return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


@dataclass
class RaceLapData:
    race_id: str
    pace: str = ""
    cumulative: List[float] = None  # type: ignore[assignment]
    splits: List[float] = None  # type: ignore[assignment]
    first3f_sec: float = float("nan")
    last3f_sec: float = float("nan")

    def __post_init__(self) -> None:
        if self.cumulative is None:
            self.cumulative = []
        if self.splits is None:
            self.splits = []

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def parse_race_lap(html: str, race_id: str) -> Optional[RaceLapData]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.Race_HaronTime")
    if table is None:
        return None

    rows = table.select("tr.HaronTime")
    if len(rows) < 2:
        return None

    cum = [_lap_to_seconds(td.get_text(strip=True)) for td in rows[0].select("td")]
    splits = [_lap_to_seconds(td.get_text(strip=True)) for td in rows[1].select("td")]

    pace_el = soup.select_one(".RapPace_Title span")
    pace = pace_el.get_text(strip=True) if pace_el else ""

    first3f = float("nan")
    last3f = float("nan")
    if len(splits) >= 3:
        first3f = splits[0] + splits[1] + splits[2]
    if len(splits) >= 3:
        last3f = splits[-1] + splits[-2] + splits[-3]

    return RaceLapData(
        race_id=race_id,
        pace=pace,
        cumulative=cum,
        splits=splits,
        first3f_sec=round(first3f, 2) if first3f == first3f else float("nan"),
        last3f_sec=round(last3f, 2) if last3f == last3f else float("nan"),
    )


def load_lap_cache(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or LAP_CACHE_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_lap_cache(cache: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or LAP_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def lap_data_from_dict(d: dict) -> RaceLapData:
    return RaceLapData(
        race_id=d.get("race_id", ""),
        pace=d.get("pace", ""),
        cumulative=[float(x) for x in d.get("cumulative", [])],
        splits=[float(x) for x in d.get("splits", [])],
        first3f_sec=float(d.get("first3f_sec", float("nan"))),
        last3f_sec=float(d.get("last3f_sec", float("nan"))),
    )


def fetch_race_laps(
    race_ids: List[str],
    *,
    use_cache: bool = True,
    stop_on_block: bool = True,
) -> Dict[str, RaceLapData]:
    cache = load_lap_cache() if use_cache else {}
    out: Dict[str, RaceLapData] = {}

    for rid in race_ids:
        if use_cache and rid in cache:
            out[rid] = lap_data_from_dict({**cache[rid], "race_id": rid})
            continue
        try:
            html = fetch_race_result_html(rid)
            data = parse_race_lap(html, rid)
            if data:
                out[rid] = data
                cache[rid] = data.to_dict()
                save_lap_cache(cache)
        except NetkeibaBlockedError:
            if stop_on_block:
                raise
            break
    return out
