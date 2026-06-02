"""出馬表ページの取得・パース。"""

import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from config.settings import URL_SHUTUBA
from src.scraper.client import fetch_html
from src.scraper.odds import fetch_win_odds_map
from src.scraper.parser import _parse_horse_link, _text, parse_race_meta
from src.scraper.race_id import parse_race_id
from src.scraper.running_style import parse_kyakushitsu_from_shutuba

_ODDS_IN_CELL_RE = re.compile(r"(\d+(?:\.\d+)?)")

_NO_SHUTUBA_MARKERS = (
    "データがありません",
    "該当するレース",
    "ページが見つかりません",
)


def fetch_shutuba_html(race_id: str) -> str:
    url = URL_SHUTUBA.format(race_id=race_id)
    return fetch_html(url)


def has_shutuba_table(html: str) -> bool:
    if any(marker in html for marker in _NO_SHUTUBA_MARKERS):
        return False
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.ShutubaTable")
    if table is None:
        return False
    return len(table.select("tr.HorseList td.HorseInfo")) > 0


def _parse_waku_umaban_shutuba(tr) -> tuple[str, str]:
    waku = ""
    umaban = ""
    for td in tr.find_all("td"):
        cls = " ".join(td.get("class", []))
        if re.search(r"Waku\d", cls):
            waku = _text(td)
        elif re.search(r"Umaban\d", cls):
            umaban = _text(td)
    return waku, umaban


def _parse_odds_from_td(odds_td) -> str:
    if odds_td is None:
        return ""
    odds_el = odds_td.select_one("span.Odds_Ninki") or odds_td.select_one("span.Odds")
    if odds_el:
        text = _text(odds_el)
        if text:
            return text
    raw = odds_td.get_text(strip=True)
    m = _ODDS_IN_CELL_RE.search(raw)
    return m.group(1) if m else ""


def _parse_odds_popularity(tr) -> tuple[str, str]:
    odds = ""
    pop = ""
    odds_td = tr.select_one("td.Popular.Txt_R")
    if odds_td is None:
        odds_td = tr.select_one("td.Odds.Txt_R")
    odds = _parse_odds_from_td(odds_td)
    if not odds:
        odds = _parse_odds_from_td(tr.select_one("td.Odds"))

    pop_td = tr.select_one("td.Popular.Txt_C")
    if pop_td is None:
        for td in tr.find_all("td"):
            cls = " ".join(td.get("class", []))
            if "Popular" in cls and "Txt_C" in cls:
                pop_td = td
                break
    if pop_td:
        pop = _text(pop_td.select_one("span") or pop_td)
    return odds, pop


def _needs_odds_supplement(rows: List[Dict[str, Any]]) -> bool:
    for row in rows:
        odds = str(row.get("odds", "")).strip()
        if not odds or not _ODDS_IN_CELL_RE.search(odds):
            return True
    return False


def _fill_popularity_from_odds(rows: List[Dict[str, Any]]) -> None:
    ranked: List[tuple[Dict[str, Any], float]] = []
    for row in rows:
        m = _ODDS_IN_CELL_RE.search(str(row.get("odds", "")))
        if not m:
            continue
        ranked.append((row, float(m.group(1))))
    ranked.sort(key=lambda x: x[1])
    for i, (row, _) in enumerate(ranked, start=1):
        if not str(row.get("popularity", "")).strip():
            row["popularity"] = str(i)


def supplement_odds_from_win_page(rows: List[Dict[str, Any]], race_id: str) -> List[Dict[str, Any]]:
    """出馬表で欠けた単勝オッズをオッズページで補完。"""
    if not rows or not _needs_odds_supplement(rows):
        _fill_popularity_from_odds(rows)
        return rows
    try:
        odds_map = fetch_win_odds_map(race_id)
    except Exception:
        _fill_popularity_from_odds(rows)
        return rows
    for row in rows:
        u = str(row.get("umaban", "")).strip()
        if not u:
            continue
        current = str(row.get("odds", "")).strip()
        if current and _ODDS_IN_CELL_RE.search(current):
            continue
        if u in odds_map:
            row["odds"] = odds_map[u]
    _fill_popularity_from_odds(rows)
    return rows


def parse_shutuba(html: str, race_id: str) -> List[Dict[str, Any]]:
    """出馬表から出走馬一覧を返す（結果確定前の予想用）。"""
    if not has_shutuba_table(html):
        return []

    meta = parse_race_id(race_id) or {
        "date": race_id[:4] + race_id[6:10],
        "race_no": int(race_id[-2:]),
    }
    race_meta = parse_race_meta(html)
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.ShutubaTable")
    if table is None:
        return []

    rows: List[Dict[str, Any]] = []
    for tr in table.select("tr.HorseList"):
        horse_a = tr.select_one("td.HorseInfo .HorseName a")
        if horse_a is None:
            horse_a = tr.select_one("td.HorseInfo a[id^='umalink_']")
        if horse_a is None:
            continue

        horse_name = horse_a.get("title") or _text(horse_a)
        horse_url, horse_id = _parse_horse_link(horse_a)
        if not horse_name:
            continue

        waku, umaban = _parse_waku_umaban_shutuba(tr)
        jockey_a = tr.select_one("td.Jockey a")
        trainer_a = tr.select_one("td.Trainer a")
        odds, popularity = _parse_odds_popularity(tr)
        sex_age = _text(tr.select_one("span.Age"))

        rows.append(
            {
                "race_id": race_id,
                "date": meta["date"],
                "race_no": meta["race_no"],
                "horse_id": horse_id,
                "horse_url": horse_url,
                "horse_name": horse_name,
                "sex_age": sex_age,
                "waku": waku,
                "umaban": umaban,
                "odds": odds,
                "popularity": popularity,
                "carried_weight": _text(tr.select_one("td.Dredging")),
                "body_weight": _text(tr.select_one("td.Weight")),
                "distance": race_meta["distance"],
                "track": race_meta["track"],
                "direction": race_meta["direction"],
                "surface": race_meta["surface"],
                "weather": race_meta["weather"],
                "race_class": race_meta["race_class"],
                "race_name": race_meta["race_name"],
                "post_time": race_meta.get("post_time", ""),
                "jockey": _text(jockey_a),
                "trainer": _text(trainer_a),
            }
        )

    kyaku = parse_kyakushitsu_from_shutuba(html)
    if kyaku:
        for row in rows:
            u = str(row.get("umaban", ""))
            if u in kyaku:
                row["entry_running_style"] = kyaku[u]

    return supplement_odds_from_win_page(rows, race_id)
