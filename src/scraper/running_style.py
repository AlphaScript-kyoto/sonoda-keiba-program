"""脚質・コーナー通過順のパース。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from config.settings import DATA_PROCESSED_DIR, PROJECT_ROOT
from src.scraper.client import NetkeibaBlockedError, fetch_race_result_html

STYLE_CACHE_PATH = DATA_PROCESSED_DIR / "race_style_cache.json"

STYLE_LABELS = ("逃", "先", "差", "追")
_STYLE_TO_SCORE = {"逃": 3.0, "先": 2.0, "差": 1.0, "追": 0.0}
_SHUTUBA_STYLE_ROWS = {"逃げ": "逃", "先行": "先", "差し": "差", "追込": "追"}

_UMABAN_RE = re.compile(r"\b(\d{1,2})\b")


def style_to_score(style: str) -> float:
    return _STYLE_TO_SCORE.get(str(style).strip(), 0.0)


def classify_style_from_corner_avg(avg_pos: float) -> str:
    """1コーナー平均通過順位から脚質を推定。"""
    if avg_pos <= 2.5:
        return "逃"
    if avg_pos <= 4.5:
        return "先"
    if avg_pos <= 7.0:
        return "差"
    return "追"


def _extract_umaban_sequence(td) -> List[str]:
    """コーナー通過 td から馬番を出現順に抽出。"""
    if td is None:
        return []
    order: List[str] = []
    seen_at: Dict[str, int] = {}

    for child in td.children:
        if getattr(child, "name", None) == "span":
            text = child.get_text(strip=True)
            if text.isdigit():
                order.append(text)
            continue
        text = str(child)
        for m in _UMABAN_RE.finditer(text):
            num = m.group(1)
            if 1 <= int(num) <= 18:
                order.append(num)

    # 同一馬番が複数回出る場合は最初のみ
    deduped: List[str] = []
    for u in order:
        if u not in seen_at:
            seen_at[u] = len(deduped) + 1
            deduped.append(u)
    return deduped


def parse_corner_positions(html: str) -> Dict[str, Dict[int, int]]:
    """
    結果HTMLからコーナー通過順位をパース。

    Returns:
        umaban -> {corner_no: position}
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.Corner_Num")
    if table is None:
        return {}

    out: Dict[str, Dict[int, int]] = {}
    for i, tr in enumerate(table.select("tr"), start=1):
        td = tr.select_one("td")
        seq = _extract_umaban_sequence(td)
        for pos, umaban in enumerate(seq, start=1):
            out.setdefault(umaban, {})[i] = pos
    return out


def parse_kyakushitsu_from_shutuba(html: str) -> Dict[str, str]:
    """出馬表の展開予想ブロックから umaban -> 脚質。"""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.Kyaku_Type")
    if table is None:
        return {}

    mapping: Dict[str, str] = {}
    for tr in table.select("tr"):
        th = tr.select_one("th")
        if th is None:
            continue
        label = th.get_text(strip=True)
        style = _SHUTUBA_STYLE_ROWS.get(label)
        if not style:
            continue
        td = tr.select_one("td")
        if td is None or td.get_text(strip=True) in ("", "−", "-"):
            continue
        for span in td.select("span.Kyaku_Type_Num"):
            u = span.get_text(strip=True)
            if u.isdigit():
                mapping[u] = style
    return mapping


@dataclass
class HorseStyleEntry:
    running_style: str
    corner_pos_avg: float
    corner_pos_1: float = 0.0
    corner_pos_2: float = 0.0
    corner_pos_3: float = 0.0
    corner_pos_4: float = 0.0


@dataclass
class RaceStyleData:
    race_id: str
    horses: Dict[str, HorseStyleEntry]

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "horses": {u: asdict(v) for u, v in self.horses.items()},
        }


def build_race_style_from_corners(
    corner_map: Dict[str, Dict[int, int]],
    race_id: str = "",
) -> RaceStyleData:
    horses: Dict[str, HorseStyleEntry] = {}
    for umaban, corners in corner_map.items():
        if not corners:
            continue
        positions = list(corners.values())
        avg = sum(positions) / len(positions)
        c1 = float(corners.get(1, avg))
        c2 = float(corners.get(2, avg))
        c3 = float(corners.get(3, avg))
        c4 = float(corners.get(4, corners.get(max(corners.keys()), avg)))
        style = classify_style_from_corner_avg(c1)
        horses[umaban] = HorseStyleEntry(
            running_style=style,
            corner_pos_avg=round(avg, 2),
            corner_pos_1=c1,
            corner_pos_2=c2,
            corner_pos_3=c3,
            corner_pos_4=c4,
        )
    return RaceStyleData(race_id=race_id, horses=horses)


def parse_race_style_from_result(html: str, race_id: str) -> Optional[RaceStyleData]:
    corner_map = parse_corner_positions(html)
    if not corner_map:
        return None
    return build_race_style_from_corners(corner_map, race_id)


def load_style_cache(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or STYLE_CACHE_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_style_cache(cache: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or STYLE_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def style_data_from_dict(d: dict) -> RaceStyleData:
    horses = {
        u: HorseStyleEntry(**v)
        for u, v in d.get("horses", {}).items()
    }
    return RaceStyleData(race_id=d.get("race_id", ""), horses=horses)


def fetch_race_styles(
    race_ids: List[str],
    *,
    use_cache: bool = True,
    stop_on_block: bool = True,
) -> Dict[str, RaceStyleData]:
    cache = load_style_cache() if use_cache else {}
    out: Dict[str, RaceStyleData] = {}

    for rid in race_ids:
        if use_cache and rid in cache:
            out[rid] = style_data_from_dict({**cache[rid], "race_id": rid})
            continue
        try:
            html = fetch_race_result_html(rid)
            data = parse_race_style_from_result(html, rid)
            if data:
                out[rid] = data
                cache[rid] = data.to_dict()
                save_style_cache(cache)
        except NetkeibaBlockedError:
            if stop_on_block:
                raise
            break
    return out
