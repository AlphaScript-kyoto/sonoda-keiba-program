"""単勝オッズページの取得・パース（出馬表の欠損補完用）。"""

from __future__ import annotations

import re
from typing import Dict

from bs4 import BeautifulSoup

from config.settings import NAR_BASE_URL
from src.scraper.client import fetch_html

URL_ODDS_WIN = f"{NAR_BASE_URL}/odds/?race_id={{race_id}}&type=b1"

_ODDS_NUM_RE = re.compile(r"^\d+(\.\d+)?$")


def fetch_win_odds_html(race_id: str) -> str:
    return fetch_html(URL_ODDS_WIN.format(race_id=race_id))


def parse_win_odds_map(html: str) -> Dict[str, str]:
    """馬番 -> 単勝オッズ文字列。"""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.RaceOdds_HorseList_Table")
    if table is None:
        return {}

    out: Dict[str, str] = {}
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
        if odds and _ODDS_NUM_RE.match(odds):
            out[umaban] = odds
    return out


def fetch_win_odds_map(race_id: str) -> Dict[str, str]:
    return parse_win_odds_map(fetch_win_odds_html(race_id))
