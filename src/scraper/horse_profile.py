"""Horse career stats (db.netkeiba) cache."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from config.settings import DATA_PROCESSED_DIR
from src.scraper.client import NetkeibaBlockedError, fetch_html

HORSE_PROFILE_CACHE_PATH = DATA_PROCESSED_DIR / "horse_profile_cache.json"
_HORSE_DB_URL = "https://db.netkeiba.com/horse/{horse_id}/"
_CAREER_RE = re.compile(r"(\d+)\u6226(\d+)\u52dd")
_BREAKDOWN_RE = re.compile(r"(\d+)-(\d+)-(\d+)-(\d+)")


@dataclass
class HorseProfileEntry:
    horse_id: str
    career_runs: int = 0
    career_wins: int = 0
    career_seconds: int = 0
    career_thirds: int = 0
    career_outs: int = 0

    @property
    def career_win_rate(self) -> float:
        return self.career_wins / self.career_runs if self.career_runs else 0.0


def parse_horse_profile(html: str, horse_id: str) -> HorseProfileEntry:
    soup = BeautifulSoup(html, "lxml")
    entry = HorseProfileEntry(horse_id=horse_id)

    for th in soup.select("th"):
        if th.get_text(strip=True) != "\u901a\u7b97\u6210\u7e3e":
            continue
        td = th.find_next_sibling("td")
        if td is None:
            break
        text = td.get_text(" ", strip=True)
        m = _CAREER_RE.search(text)
        if m:
            entry.career_runs = int(m.group(1))
            entry.career_wins = int(m.group(2))
        link = td.select_one("a[title='\u5168\u7af6\u8d70\u6210\u7e3e']") or td.select_one("a")
        if link:
            bm = _BREAKDOWN_RE.search(link.get_text(strip=True))
            if bm:
                entry.career_wins = int(bm.group(1))
                entry.career_seconds = int(bm.group(2))
                entry.career_thirds = int(bm.group(3))
                entry.career_outs = int(bm.group(4))
                entry.career_runs = (
                    entry.career_wins
                    + entry.career_seconds
                    + entry.career_thirds
                    + entry.career_outs
                )
        break

    return entry


def load_horse_profile_cache(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or HORSE_PROFILE_CACHE_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_horse_profile_cache(cache: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or HORSE_PROFILE_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_horse_profiles(
    horse_ids: List[str],
    *,
    use_cache: bool = True,
    stop_on_block: bool = True,
) -> Dict[str, HorseProfileEntry]:
    cache = load_horse_profile_cache() if use_cache else {}
    out: Dict[str, HorseProfileEntry] = {}

    for hid in horse_ids:
        if not hid or hid in ("", "nan"):
            continue
        if use_cache and hid in cache:
            out[hid] = HorseProfileEntry(**{**cache[hid], "horse_id": hid})
            continue
        try:
            html = fetch_html(_HORSE_DB_URL.format(horse_id=hid))
            entry = parse_horse_profile(html, hid)
            out[hid] = entry
            cache[hid] = asdict(entry)
            save_horse_profile_cache(cache)
        except NetkeibaBlockedError:
            if stop_on_block:
                raise
            break
    return out
