"""Live scrape sanity check (encoding, URLs, field coverage)."""

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
    sample = text[:120].replace("\n", " ")
    ok = score >= 3 and "\ufffd" not in text[:2000].lower()
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
