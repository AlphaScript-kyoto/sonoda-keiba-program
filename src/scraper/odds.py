"""Odds pages: win/place/wide/sanrenpuku (nar.netkeiba.com)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from config.settings import DATA_PROCESSED_DIR, NAR_BASE_URL
from src.scraper.client import fetch_html

ODDS_CACHE_PATH = DATA_PROCESSED_DIR / "odds_cache.json"
URL_ODDS_TEMPLATE = f"{NAR_BASE_URL}/odds/?race_id={{race_id}}&type={{odds_type}}"
URL_ODDS_WIN = f"{NAR_BASE_URL}/odds/?race_id={{race_id}}&type=b1"

_ODDS_NUM_RE = re.compile(r"^\d+(\.\d+)?$")
_ODDS_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$")


def build_odds_url(race_id: str, odds_type: str) -> str:
    return URL_ODDS_TEMPLATE.format(race_id=race_id, odds_type=odds_type)


def fetch_odds_html(race_id: str, odds_type: str) -> str:
    return fetch_html(build_odds_url(race_id, odds_type))


def fetch_win_odds_html(race_id: str) -> str:
    return fetch_odds_html(race_id, "b1")


def _parse_horse_odds_tables(html: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.select("table.RaceOdds_HorseList_Table")
    win: Dict[str, str] = {}
    place: Dict[str, str] = {}
    for ti, table in enumerate(tables):
        target = win if ti == 0 else place
        for tr in table.select("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            umaban = tds[1].get_text(strip=True)
            if not umaban.isdigit():
                continue
            odds_td = tr.select_one("td.Odds")
            if odds_td is None:
                continue
            odds_span = odds_td.select_one("span.Odds") or odds_td.select_one("span")
            odds = odds_span.get_text(strip=True) if odds_span else odds_td.get_text(strip=True)
            odds = odds.replace(",", "")
            if not odds:
                continue
            if ti == 0 and _ODDS_NUM_RE.match(odds):
                target[umaban] = odds
            elif ti >= 1 and _ODDS_RANGE_RE.match(odds):
                target[umaban] = odds
    return win, place


def parse_win_odds_map(html: str) -> Dict[str, str]:
    win, _ = _parse_horse_odds_tables(html)
    return win


def parse_place_odds_map(html: str) -> Dict[str, str]:
    _, place = _parse_horse_odds_tables(html)
    return place


def _parse_axis_odds_tables(html: str) -> Dict[str, Dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out: Dict[str, Dict[str, str]] = {}
    for table in soup.select("table.Odds_Table"):
        rows = table.select("tr")
        if not rows:
            continue
        axis = rows[0].find("th") or rows[0].find("td")
        if axis is None:
            continue
        axis_u = axis.get_text(strip=True)
        if not axis_u.isdigit():
            continue
        partners: Dict[str, str] = {}
        for tr in rows[1:]:
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            partner = tds[0].get_text(strip=True)
            odds_td = tr.select_one("td.Odds") or (tds[1] if len(tds) > 1 else None)
            odds = odds_td.get_text(strip=True).replace(",", "") if odds_td else ""
            if partner.isdigit() and odds:
                partners[partner] = odds
        if partners:
            out[axis_u] = partners
    return out


def _flat_pair_odds(axis: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    flat: Dict[str, str] = {}
    for a, partners in axis.items():
        for b, odds in partners.items():
            key = "-".join(sorted((a, b), key=lambda x: int(x)))
            flat[key] = odds
    return flat


def parse_wide_odds_map(html: str) -> Dict[str, str]:
    return _flat_pair_odds(_parse_axis_odds_tables(html))


def parse_umaren_odds_map(html: str) -> Dict[str, str]:
    return _flat_pair_odds(_parse_axis_odds_tables(html))


def parse_sanrenpuku_axis_odds(html: str) -> Dict[str, Dict[str, str]]:
    return _parse_axis_odds_tables(html)


@dataclass
class RaceOddsSnapshot:
    race_id: str
    win: Dict[str, str] = field(default_factory=dict)
    place: Dict[str, str] = field(default_factory=dict)
    wide: Dict[str, str] = field(default_factory=dict)
    umaren: Dict[str, str] = field(default_factory=dict)
    sanrenpuku_axis: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_race_odds_bundle(
    html_b1: str,
    html_b4: str = "",
    html_b5: str = "",
    html_b7: str = "",
) -> RaceOddsSnapshot:
    win, place = _parse_horse_odds_tables(html_b1)
    snap = RaceOddsSnapshot(race_id="", win=win, place=place)
    if html_b5:
        snap.wide = parse_wide_odds_map(html_b5)
    if html_b4:
        snap.umaren = parse_umaren_odds_map(html_b4)
    if html_b7:
        snap.sanrenpuku_axis = parse_sanrenpuku_axis_odds(html_b7)
    return snap


def fetch_race_odds_snapshot(race_id: str, *, include_exotic: bool = True) -> RaceOddsSnapshot:
    html_b1 = fetch_odds_html(race_id, "b1")
    snap = parse_race_odds_bundle(html_b1)
    snap.race_id = race_id
    if include_exotic:
        snap.wide = parse_wide_odds_map(fetch_odds_html(race_id, "b5"))
        snap.umaren = parse_umaren_odds_map(fetch_odds_html(race_id, "b4"))
        snap.sanrenpuku_axis = parse_sanrenpuku_axis_odds(fetch_odds_html(race_id, "b7"))
    return snap


def fetch_win_odds_map(race_id: str) -> Dict[str, str]:
    return parse_win_odds_map(fetch_win_odds_html(race_id))


def load_odds_cache(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or ODDS_CACHE_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_odds_cache(cache: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or ODDS_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_odds_to_cache(
    race_ids: List[str],
    *,
    include_exotic: bool = True,
    stop_on_block: bool = True,
) -> Dict[str, dict]:
    from src.scraper.client import NetkeibaBlockedError

    cache = load_odds_cache()
    for i, race_id in enumerate(race_ids, start=1):
        if race_id in cache:
            continue
        try:
            snap = fetch_race_odds_snapshot(race_id, include_exotic=include_exotic)
            cache[race_id] = snap.to_dict()
            if i % 10 == 0:
                save_odds_cache(cache)
                print(f"  odds cache: {i}/{len(race_ids)}", flush=True)
        except NetkeibaBlockedError:
            save_odds_cache(cache)
            if stop_on_block:
                raise
        except Exception as exc:
            print(f"  WARN odds {race_id}: {exc}", flush=True)
    save_odds_cache(cache)
    return cache
