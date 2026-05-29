"""netkeiba レース結果 HTML のパース。"""

import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from src.scraper.race_id import parse_race_id

_NO_RESULT_MARKERS = (
    "データがありません",
    "該当するレース",
    "ページが見つかりません",
)

_HORSE_ID_RE = re.compile(r"/horse/([^/?#]+)/?", re.I)


def has_result_table(html: str) -> bool:
    """結果テーブルがあるか（開催あり・レース成立）。"""
    if any(marker in html for marker in _NO_RESULT_MARKERS):
        return False
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("#All_Result_Table")
    return table is not None and len(table.select("tbody tr")) > 0


def _text(el) -> str:
    if el is None:
        return ""
    return el.get_text(strip=True)


def _parse_finish(cell) -> Optional[int]:
    rank = cell.select_one(".Rank") if cell else None
    if rank is None:
        return None
    text = rank.get_text(strip=True)
    if text.isdigit():
        return int(text)
    return None


def _parse_horse_link(horse_a) -> tuple[str, str]:
    """馬名リンクから URL と ID を取得。"""
    if horse_a is None:
        return "", ""
    href = horse_a.get("href", "").strip()
    if href and not href.startswith("http"):
        href = f"https://db.netkeiba.com{href}" if href.startswith("/") else href
    m = _HORSE_ID_RE.search(href)
    horse_id = m.group(1) if m else ""
    return href, horse_id


def _parse_sex_age(tr) -> str:
    detail = tr.select_one("td.Horse_Info .Horse_Info_Detail .Detail_Left")
    return _text(detail)


def _parse_race_time(tr) -> str:
    """走破タイム（着差列を除く）。"""
    for cell in tr.select("td.Time"):
        rt = cell.select_one("span.RaceTime")
        if not rt:
            continue
        value = rt.get_text(strip=True)
        if value and ":" in value:
            return value
    return ""


def _parse_popularity(tr) -> str:
    pop = tr.select_one("span.OddsPeople")
    return _text(pop)


def _parse_win_odds(tr) -> str:
    """単勝オッズ（Odds_Ninki 以外の span も拾う）。"""
    odds_td = tr.select_one("td.Odds.Txt_R")
    if odds_td is None:
        return ""
    span = odds_td.select_one("span.Odds_Ninki") or odds_td.select_one("span")
    return _text(span)


def _parse_last_3f(tr) -> str:
    """
    後3Fタイム。

    BgBlue02 等のクラスが付かない行（td.Time のみ）があるため、
    タイム列のうち RaceTime（走破・着差）以外の最後のセルを使う。
    """
    values: List[str] = []
    for cell in tr.select("td.Time"):
        if cell.select_one("span.RaceTime"):
            continue
        text = _text(cell)
        if text:
            values.append(text)
    return values[-1] if values else ""


def _parse_carried_weight(tr) -> str:
    jw = tr.select_one("span.JockeyWeight")
    return _text(jw)


def _parse_body_weight(tr) -> str:
    w = tr.select_one("td.Weight")
    return _text(w)


def _parse_waku_umaban(tr) -> tuple[str, str]:
    """枠番・馬番（td.Num の Waku8 / Waku クラス）。"""
    waku = ""
    umaban = ""
    for td in tr.select("td.Num"):
        classes = td.get("class") or []
        cls = " ".join(classes) if isinstance(classes, list) else str(classes)
        num = _text(td.select_one("div") or td)
        if re.search(r"Waku\d", cls):
            waku = num
        elif re.search(r"(?:^|\s)Waku(?:\s|$)", cls) and not re.search(r"Waku\d", cls):
            umaban = num
    return waku, umaban


def _parse_margin(tr) -> str:
    """着差（走破タイム列の次の RaceTime）。"""
    seen_race_time = False
    for cell in tr.select("td.Time"):
        rt = cell.select_one("span.RaceTime")
        if not rt:
            continue
        value = rt.get_text(strip=True)
        if not value:
            continue
        if ":" in value:
            seen_race_time = True
            continue
        if seen_race_time:
            return value
    return ""


def parse_race_meta(html: str) -> Dict[str, str]:
    """
    レース共通情報（全馬同一）をパース。

    例: ダ1400m (右) / 天候:晴 / 馬場:重、RaceData02 のクラス・頭数
    """
    soup = BeautifulSoup(html, "lxml")
    block01 = soup.select_one(".RaceData01")
    block02 = soup.select_one(".RaceData02")
    text01 = block01.get_text(" ", strip=True) if block01 else ""
    text02 = block02.get_text(" ", strip=True) if block02 else ""

    distance = ""
    m = re.search(r"(\d{3,4})m", text01)
    if m:
        distance = f"{m.group(1)}m"

    track = ""
    m = re.search(r"馬場[:：]\s*(\S+)", text01)
    if m:
        track = m.group(1)

    direction = ""
    m = re.search(r"\((右|左)\)", text01)
    if m:
        direction = m.group(1)

    surface = ""
    m = re.search(r"(ダ|芝)\s*\d+m", text01)
    if m:
        surface = m.group(1)

    weather = ""
    m = re.search(r"天候[:：]\s*(\S+)", text01)
    if m:
        weather = m.group(1)

    head_count = ""
    m = re.search(r"(\d+)頭", text02)
    if m:
        head_count = m.group(1)

    race_condition = ""
    m = re.search(
        r"(サラ系\d+歳以上\s*[A-Z]\d+[一二三四五六七八]?|重賞[^\s]+|障害[^\s]+)",
        text02,
    )
    if m:
        race_condition = m.group(1).strip()
    else:
        spans = block02.select("span") if block02 else []
        for sp in spans:
            t = sp.get_text(strip=True)
            if "歳" in t or re.search(r"[A-Z]\d", t):
                race_condition = t
                break

    race_class = ""
    m = re.search(r"\b([A-Z]\d+[一二三四五六七八]?)\b", race_condition)
    if m:
        race_class = m.group(1)
    m = re.search(r"\b([A-Z]\d+)\b", text02)
    if not race_class and m:
        race_class = m.group(1)

    race_name = _text(soup.select_one(".RaceName"))

    return {
        "distance": distance,
        "track": track,
        "direction": direction,
        "surface": surface,
        "weather": weather,
        "head_count": head_count,
        "race_condition": race_condition,
        "race_class": race_class,
        "race_name": race_name,
    }


def parse_race_result(html: str, race_id: str) -> List[Dict[str, Any]]:
    """
    結果ページ HTML をパースし、1頭1行の辞書リストを返す。
    """
    if not has_result_table(html):
        return []

    meta = parse_race_id(race_id) or {
        "date": race_id[:4] + race_id[6:10],
        "race_no": int(race_id[-2:]),
    }
    race_meta = parse_race_meta(html)
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("#All_Result_Table")
    if table is None:
        return []

    rows: List[Dict[str, Any]] = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        finish = _parse_finish(tds[0])
        if finish is None:
            continue

        horse_a = tr.select_one("td.Horse_Info .Horse_Name a")
        horse_name = ""
        horse_url = ""
        horse_id = ""
        if horse_a:
            horse_name = horse_a.get("title") or _text(horse_a)
            horse_url, horse_id = _parse_horse_link(horse_a)

        jockey_a = tr.select_one("td.Jockey a")
        trainer_a = tr.select_one("td.Trainer a")
        waku, umaban = _parse_waku_umaban(tr)

        row: Dict[str, Any] = {
            "race_id": race_id,
            "date": meta["date"],
            "race_no": meta["race_no"],
            "horse_id": horse_id,
            "horse_url": horse_url,
            "horse_name": horse_name,
            "sex_age": _parse_sex_age(tr),
            "waku": waku,
            "umaban": umaban,
            "finish": finish,
            "race_time": _parse_race_time(tr),
            "margin": _parse_margin(tr),
            "popularity": _parse_popularity(tr),
            "odds": _parse_win_odds(tr),
            "last_3f": _parse_last_3f(tr),
            "carried_weight": _parse_carried_weight(tr),
            "body_weight": _parse_body_weight(tr),
            "distance": race_meta["distance"],
            "track": race_meta["track"],
            "direction": race_meta["direction"],
            "surface": race_meta["surface"],
            "weather": race_meta["weather"],
            "head_count": race_meta["head_count"],
            "race_condition": race_meta["race_condition"],
            "race_class": race_meta["race_class"],
            "race_name": race_meta["race_name"],
            "jockey": _text(jockey_a),
            "trainer": _text(trainer_a),
        }
        rows.append(row)

    return rows


def extract_race_title(html: str) -> str:
    """ページタイトル（レース名確認用）。"""
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    return m.group(1).strip() if m else ""
