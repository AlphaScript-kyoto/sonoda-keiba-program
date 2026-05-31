"""レース結果ページから払戻金を取得・キャッシュ。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from config.settings import DATA_PROCESSED_DIR
from src.scraper.client import NetkeibaBlockedError, fetch_race_result_html

PAYBACK_CACHE_PATH = DATA_PROCESSED_DIR / "payback_cache.json"


@dataclass
class RacePayback:
    race_id: str
    tansho: Dict[str, int]
    fukusho: Dict[str, int]
    fuku3_umaban: Tuple[str, str, str]
    fuku3_yen: int
    tan3_umaban: Tuple[str, str, str]
    tan3_yen: int
    wide: Dict[str, int] = field(default_factory=dict)  # "3-9" -> yen


def _parse_yen(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _umaban_from_result_td(td) -> List[str]:
    nums: List[str] = []
    if td is None:
        return nums
    for span in td.select("span"):
        t = span.get_text(strip=True)
        if t.isdigit():
            nums.append(t)
    for ul in td.select("ul"):
        for li in ul.select("li span"):
            t = li.get_text(strip=True)
            if t.isdigit():
                nums.append(t)
    return nums


def _payout_values(td) -> List[int]:
    if td is None:
        return []
    raw = td.get_text("\n", strip=True)
    return [_parse_yen(part) for part in raw.split("\n") if part.strip()]


def _wide_pair_key(a: str, b: str) -> str:
    x, y = sorted((str(a), str(b)))
    return f"{x}-{y}"


def _parse_wide(result_td, payout_td) -> Dict[str, int]:
    """ワイド払戻: 馬番ペア -> 円。"""
    wide: Dict[str, int] = {}
    if result_td is None or payout_td is None:
        return wide
    uls = result_td.select("ul")
    pays = _payout_values(payout_td)
    if not uls:
        return wide
    # Payout は <br> 区切りで複数行のことが多い
    raw = payout_td.get_text("\n", strip=True)
    pay_parts = [_parse_yen(part) for part in raw.split("\n") if part.strip()]
    if not pay_parts:
        pay_parts = pays
    for i, ul in enumerate(uls):
        nums: List[str] = []
        for li in ul.select("li"):
            span = li.select_one("span")
            if span:
                t = span.get_text(strip=True)
                if t.isdigit():
                    nums.append(t)
        if len(nums) >= 2 and i < len(pay_parts):
            wide[_wide_pair_key(nums[0], nums[1])] = pay_parts[i]
    return wide


def wide_pair_key(a: str, b: str) -> str:
    """ワイド馬番ペアの辞書キー（小さい方-大きい方）。"""
    return _wide_pair_key(a, b)


def wide_payout_yen(
    pairs: List[Tuple[str, str]], payback: Optional["RacePayback"]
) -> int:
    """的中したワイドペアの払戻合計。"""
    if not payback or not pairs:
        return 0
    total = 0
    for a, b in pairs:
        total += payback.wide.get(wide_pair_key(a, b), 0)
    return total


def parse_race_payback(html: str, race_id: str) -> Optional[RacePayback]:
    """結果HTMLから単勝・複勝・三連複・三連単の払戻をパース。"""
    soup = BeautifulSoup(html, "lxml")
    tansho: Dict[str, int] = {}
    fukusho: Dict[str, int] = {}
    fuku3_umaban: Tuple[str, str, str] = ("", "", "")
    fuku3_yen = 0
    tan3_umaban: Tuple[str, str, str] = ("", "", "")
    tan3_yen = 0
    wide: Dict[str, int] = {}

    for tr in soup.select("table.Payout_Detail_Table tr"):
        classes = tr.get("class") or []
        cls = " ".join(classes) if isinstance(classes, list) else str(classes)
        result_td = tr.select_one("td.Result")
        payout_td = tr.select_one("td.Payout")

        if "Tansho" in cls:
            nums = _umaban_from_result_td(result_td)
            pays = _payout_values(payout_td)
            if nums and pays:
                tansho[nums[0]] = pays[0]
        elif "Fukusho" in cls:
            nums = _umaban_from_result_td(result_td)
            pays = _payout_values(payout_td)
            for u, p in zip(nums, pays):
                fukusho[u] = p
        elif "Fuku3" in cls:
            nums = _umaban_from_result_td(result_td)
            pays = _payout_values(payout_td)
            if len(nums) >= 3 and pays:
                fuku3_umaban = (nums[0], nums[1], nums[2])
                fuku3_yen = pays[0]
        elif "Tan3" in cls:
            nums = _umaban_from_result_td(result_td)
            pays = _payout_values(payout_td)
            if len(nums) >= 3 and pays:
                tan3_umaban = (nums[0], nums[1], nums[2])
                tan3_yen = pays[0]
        elif "Wide" in cls:
            wide = _parse_wide(result_td, payout_td)

    if not tansho and not fuku3_yen:
        return None

    return RacePayback(
        race_id=race_id,
        tansho=tansho,
        fukusho=fukusho,
        fuku3_umaban=fuku3_umaban,
        fuku3_yen=fuku3_yen,
        tan3_umaban=tan3_umaban,
        tan3_yen=tan3_yen,
        wide=wide,
    )


def load_payback_cache(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or PAYBACK_CACHE_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_payback_cache(cache: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or PAYBACK_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def payback_to_dict(pb: RacePayback) -> dict:
    d = asdict(pb)
    d["fuku3_umaban"] = list(d["fuku3_umaban"])
    d["tan3_umaban"] = list(d["tan3_umaban"])
    return d


def payback_from_dict(d: dict) -> RacePayback:
    return RacePayback(
        race_id=d["race_id"],
        tansho=d.get("tansho", {}),
        fukusho=d.get("fukusho", {}),
        fuku3_umaban=tuple(d.get("fuku3_umaban", ("", "", ""))),
        fuku3_yen=int(d.get("fuku3_yen", 0)),
        tan3_umaban=tuple(d.get("tan3_umaban", ("", "", ""))),
        tan3_yen=int(d.get("tan3_yen", 0)),
        wide={str(k): int(v) for k, v in d.get("wide", {}).items()},
    )


def fetch_paybacks(
    race_ids: List[str],
    *,
    use_cache: bool = True,
    stop_on_block: bool = True,
    refresh_if_missing_wide: bool = True,
) -> Dict[str, RacePayback]:
    """払戻を取得（キャッシュ優先、未取得分のみHTTP）。"""
    cache = load_payback_cache() if use_cache else {}
    out: Dict[str, RacePayback] = {}

    for rid in race_ids:
        if rid in cache:
            entry = cache[rid]
            needs_refresh = refresh_if_missing_wide and not entry.get("wide")
            if use_cache and not needs_refresh:
                out[rid] = payback_from_dict({**entry, "race_id": rid})
                continue

        try:
            html = fetch_race_result_html(rid)
            pb = parse_race_payback(html, rid)
            if pb:
                out[rid] = pb
                cache[rid] = payback_to_dict(pb)
                save_payback_cache(cache)
        except NetkeibaBlockedError:
            if stop_on_block:
                raise
            break

    return out
