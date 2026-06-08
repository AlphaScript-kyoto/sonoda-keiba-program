"""Generator: writes scripts/fetch_odds.py and verify_scrape.py."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FETCH_ODDS = '''"""Backfill odds_cache.json for races in master."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.scraper.client import NetkeibaBlockedError
from src.scraper.odds import fetch_odds_to_cache, load_odds_cache


def _race_ids_in_range(master, from_yyyymmdd: str, to_yyyymmdd: str) -> list[str]:
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ]
    return sorted(hist["race_id"].astype(str).unique().tolist())


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch odds into odds_cache.json")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--win-only", action="store_true", help="b1 only (faster)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    master = load_master()
    race_ids = _race_ids_in_range(master, args.from_date, args.to_date)
    cache = load_odds_cache()
    missing = [r for r in race_ids if r not in cache]

    print(
        f"Range {args.from_date}-{args.to_date}: "
        f"{len(race_ids)} races, {len(missing)} missing odds"
    )
    if not missing:
        print("Nothing to fetch.")
        return

    if args.dry_run:
        for rid in missing:
            print(rid)
        return

    try:
        fetch_odds_to_cache(missing, include_exotic=not args.win_only)
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Done. cache size={len(load_odds_cache())}")


if __name__ == "__main__":
    main()
'''

VERIFY_SCRAPE = '''"""Live scrape sanity check (encoding, URLs, field coverage)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

from src.scraper.client import (
    _cjk_score,
    _decode_response_bytes,
    _detect_encoding,
    build_request_headers,
    build_result_url,
    fetch_html,
)
from src.scraper.odds import build_odds_url, fetch_race_odds_snapshot
from src.scraper.parser import parse_race_result
from src.scraper.payback import parse_race_payback
from src.scraper.running_style import parse_race_style_from_result


def _ok(label: str, cond: bool, detail: str = "") -> bool:
    mark = "OK" if cond else "FAIL"
    msg = f"  [{mark}] {label}"
    if detail:
        msg += f" -- {detail}"
    print(msg)
    return cond


def _fetch_raw(url: str) -> tuple[bytes, str]:
    resp = requests.get(url, headers=build_request_headers(), timeout=30)
    resp.raise_for_status()
    return resp.content, _detect_encoding(resp)


def _check_encoding(url: str, label: str) -> bool:
    content, preferred = _fetch_raw(url)
    text = _decode_response_bytes(content, preferred)
    score = _cjk_score(text)
    sample = text[:120].replace("\\n", " ")
    ok = score >= 3 and "\\ufffd" not in text[:2000].lower()
    return _ok(f"encoding {label}", ok, f"cjk={score} sample={sample[:80]!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify netkeiba scrape for one race")
    parser.add_argument("--race-id", required=True, help="e.g. 202650052201")
    args = parser.parse_args()
    rid = args.race_id

    print(f"race_id={rid}")
    all_ok = True

    result_url = build_result_url(rid)
    odds_b1 = build_odds_url(rid, "b1")

    for url, label in [
        (result_url, "result"),
        (odds_b1, "odds_b1"),
    ]:
        all_ok &= _check_encoding(url, label)

    result_html = fetch_html(result_url)
    rows = parse_race_result(result_html, rid)
    all_ok &= _ok("result rows", len(rows) >= 4, f"n={len(rows)}")
    if rows:
        r0 = rows[0]
        all_ok &= _ok("jockey_id", bool(r0.get("jockey_id")), str(r0.get("jockey_id")))
        all_ok &= _ok("trainer_id", bool(r0.get("trainer_id")), str(r0.get("trainer_id")))
        all_ok &= _ok("post_time", bool(r0.get("post_time")), str(r0.get("post_time")))

    pb = parse_race_payback(result_html, rid)
    all_ok &= _ok("payback parsed", pb is not None)
    if pb:
        all_ok &= _ok("payback fuku3", pb.fuku3_yen > 0, str(pb.fuku3_yen))
        all_ok &= _ok("payback umaren", len(pb.umaren) > 0, str(len(pb.umaren)))
        all_ok &= _ok("payback umatan", len(pb.umatan) > 0, str(len(pb.umatan)))

    style = parse_race_style_from_result(result_html, rid)
    n_style = len(style.horses) if style else 0
    all_ok &= _ok("running_style horses", n_style >= 4, f"n={n_style}")
    if style:
        h0 = next(iter(style.horses.values()))
        all_ok &= _ok("corner_pos_2", h0.corner_pos_2 > 0, str(h0.corner_pos_2))

    snap = fetch_race_odds_snapshot(rid, include_exotic=True)
    all_ok &= _ok("odds win", len(snap.win) >= 4, f"n={len(snap.win)}")
    all_ok &= _ok("odds place", len(snap.place) >= 4, f"n={len(snap.place)}")
    all_ok &= _ok("odds wide", len(snap.wide) >= 1, f"n={len(snap.wide)}")
    all_ok &= _ok("odds umaren", len(snap.umaren) >= 1, f"n={len(snap.umaren)}")
    all_ok &= _ok("odds sanrenpuku", len(snap.sanrenpuku_axis) >= 1, f"n={len(snap.sanrenpuku_axis)}")

    if rows and snap.win:
        names_in_odds = set()
        for u, odds in snap.win.items():
            for r in rows:
                if str(r.get("umaban")) == str(u):
                    names_in_odds.add(r.get("horse_name", ""))
                    break
        matched = len(names_in_odds)
        all_ok &= _ok("odds umaban align result", matched >= 4, f"matched={matched}")

    print("PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
'''


HORSE_PROFILE = '''"""Horse career stats (db.netkeiba) cache."""

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
_CAREER_RE = re.compile(r"(\\d+)\\u6226(\\d+)\\u52dd")
_BREAKDOWN_RE = re.compile(r"(\\d+)-(\\d+)-(\\d+)-(\\d+)")


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
        if th.get_text(strip=True) != "\\u901a\\u7b97\\u6210\\u7e3e":
            continue
        td = th.find_next_sibling("td")
        if td is None:
            break
        text = td.get_text(" ", strip=True)
        m = _CAREER_RE.search(text)
        if m:
            entry.career_runs = int(m.group(1))
            entry.career_wins = int(m.group(2))
        link = td.select_one("a[title='\\u5168\\u7af6\\u8d70\\u6210\\u7e3e']") or td.select_one("a")
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
'''

TEST_HORSE_PROFILE = '''"""horse_profile parser tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.horse_profile import parse_horse_profile

FIXTURE = ROOT / "tests" / "fixtures" / "horse_2018110078.html"


def test_parse_horse_profile_career_stats():
    html = FIXTURE.read_text(encoding="utf-8")
    entry = parse_horse_profile(html, "2018110078")
    assert entry.career_runs == 78
    assert entry.career_wins == 5
    assert entry.career_seconds == 8
    assert entry.career_thirds == 4
    assert entry.career_outs == 61
'''

FETCH_HORSE_PROFILES = '''"""Backfill horse_profile_cache.json from master horse_ids."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.scraper.client import NetkeibaBlockedError
from src.scraper.horse_profile import fetch_horse_profiles, load_horse_profile_cache


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch horse career stats into cache")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    master = load_master()
    hist = master[
        (master["date"].astype(str) >= args.from_date)
        & (master["date"].astype(str) <= args.to_date)
    ]
    horse_ids = sorted(hist["horse_id"].astype(str).unique().tolist())
    cache = load_horse_profile_cache()
    missing = [h for h in horse_ids if h and h not in cache]

    print(
        f"Range {args.from_date}-{args.to_date}: "
        f"{len(horse_ids)} horses, {len(missing)} missing profiles"
    )
    if not missing:
        print("Nothing to fetch.")
        return

    if args.dry_run:
        for hid in missing:
            print(hid)
        return

    try:
        fetch_horse_profiles(missing)
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Done. cache size={len(load_horse_profile_cache())}")


if __name__ == "__main__":
    main()
'''


def main() -> None:
    for rel, content in (
        ("scripts/fetch_odds.py", FETCH_ODDS),
        ("scripts/verify_scrape.py", VERIFY_SCRAPE),
        ("scripts/fetch_horse_profiles.py", FETCH_HORSE_PROFILES),
        ("src/scraper/horse_profile.py", HORSE_PROFILE),
        ("tests/test_horse_profile.py", TEST_HORSE_PROFILE),
    ):
        path = ROOT / rel
        path.write_text(content, encoding="utf-8")
        print(f"wrote {rel} nulls={path.read_bytes().count(b'\\x00')}")


if __name__ == "__main__":
    main()
