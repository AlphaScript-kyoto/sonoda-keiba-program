"""血統（父・母父）の取得・キャッシュ。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from config.settings import DATA_PROCESSED_DIR
from src.scraper.client import NetkeibaBlockedError, fetch_html

BLOODLINE_CACHE_PATH = DATA_PROCESSED_DIR / "bloodline_cache.json"
_HORSE_DB_URL = "https://db.netkeiba.com/horse/{horse_id}/"


@dataclass
class BloodlineEntry:
    horse_id: str
    sire: str = ""
    dam_sire: str = ""


def parse_horse_bloodline(html: str, horse_id: str) -> BloodlineEntry:
    soup = BeautifulSoup(html, "lxml")
    sire = ""
    dam_sire = ""

    # 血統表: 父は1行目、母父は母の行から
    table = soup.select_one("table.blood_table") or soup.select_one("table.Blood_Table")
    if table:
        rows = table.select("tr")
        if rows:
            first_links = rows[0].select("a")
            if first_links:
                sire = first_links[0].get_text(strip=True)
        if len(rows) >= 3:
            dam_row_links = rows[2].select("a")
            if dam_row_links:
                dam_sire = dam_row_links[0].get_text(strip=True)

    if not sire:
        for dt in soup.select("dt"):
            label = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            link = dd.select_one("a")
            name = link.get_text(strip=True) if link else dd.get_text(strip=True)
            if label == "父":
                sire = name
            elif label in ("母父", "母の父"):
                dam_sire = name

    return BloodlineEntry(horse_id=horse_id, sire=sire, dam_sire=dam_sire)


def load_bloodline_cache(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or BLOODLINE_CACHE_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_bloodline_cache(cache: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or BLOODLINE_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_bloodlines(
    horse_ids: List[str],
    *,
    use_cache: bool = True,
    stop_on_block: bool = True,
) -> Dict[str, BloodlineEntry]:
    cache = load_bloodline_cache() if use_cache else {}
    out: Dict[str, BloodlineEntry] = {}

    for hid in horse_ids:
        if not hid or hid in ("", "nan"):
            continue
        if use_cache and hid in cache:
            out[hid] = BloodlineEntry(**{**cache[hid], "horse_id": hid})
            continue
        try:
            html = fetch_html(_HORSE_DB_URL.format(horse_id=hid))
            entry = parse_horse_bloodline(html, hid)
            out[hid] = entry
            cache[hid] = asdict(entry)
            save_bloodline_cache(cache)
        except NetkeibaBlockedError:
            if stop_on_block:
                raise
            break
    return out
