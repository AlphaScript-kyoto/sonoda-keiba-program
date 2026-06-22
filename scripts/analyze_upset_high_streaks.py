"""Analyze upset+high sanren streaks and formation-5 ROI."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY
from src.predictor.score import load_master
from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs

UPSET = "\u8352"
OUT = ROOT / "data" / "processed" / "logs" / "upset_high_streak_analysis.json"
CACHE_DIR = ROOT / "data" / "processed" / "logs" / "upset_high_cache"


def load_period(f: str, t: str, master, win_cfg, ex_cfg):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"records_{f}_{t}.json"
    if cache_path.exists():
        import json as _json

        raw = _json.loads(cache_path.read_text(encoding="utf-8"))
        return raw

    hist = master[(master["date"].astype(str) >= f) & (master["date"].astype(str) <= t)]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    recs = _collect_race_records(f, t, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY)
    raw = []
    for rec in recs:
        eh = _exotic_high_for_record(rec, DEFAULT_STRATEGY)
        raw.append(
            {
                "date": rec.date,
                "race_no": rec.race_no,
                "win_profile": rec.win_profile,
                "exotic_profile": rec.exotic_profile,
                "win_high": rec.win_high,
                "exotic_high": eh,
                "box_pts": rec.sanrenpuku_box_points,
                "box_hit": bool(rec.sanrenpuku_box_hit),
                "form_pts": rec.sanrenpuku_formation_points,
                "form_hit": bool(rec.sanrenpuku_formation_hit),
                "fuku3_yen": rec.fuku3_yen,
            }
        )
    cache_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return raw


def rows_from_recs(recs, year: str, segment: str):
    out = []
    for rec in recs:
        if segment == "exotic_upset_high":
            ok = (
                rec["exotic_profile"] == UPSET
                and rec["exotic_high"]
                and rec["box_pts"] > 0
            )
        else:
            ok = rec["win_profile"] == UPSET and rec["win_high"] and rec["box_pts"] > 0
        if not ok:
            continue
        box_pts = rec["box_pts"]
        form_pts = rec["form_pts"]
        out.append(
            {
                "year": year,
                "date": rec["date"],
                "race_no": rec["race_no"],
                "box_pts": box_pts,
                "box_inv": box_pts * BET_UNIT,
                "box_ret": rec["fuku3_yen"] if rec["box_hit"] else 0,
                "box_hit": rec["box_hit"],
                "form_pts": form_pts,
                "form_inv": form_pts * BET_UNIT,
                "form_ret": rec["fuku3_yen"] if rec["form_hit"] else 0,
                "form_hit": rec["form_hit"],
            }
        )
    return out


def roi_part(rows, inv_k, ret_k):
    inv = sum(r[inv_k] for r in rows)
    ret = sum(r[ret_k] for r in rows)
    n = len(rows)
    hits = sum(1 for r in rows if r[ret_k] > 0)
    return {
        "n_races": n,
        "invest_yen": inv,
        "return_yen": ret,
        "roi_pct": round(ret / inv * 100, 2) if inv else None,
        "hit_rate": round(hits / n, 4) if n else None,
    }


def streak_analysis(rows, hit_k, inv_k, ret_k):
    rows = sorted(rows, key=lambda r: (r["date"], r["race_no"]))
    max_streak = 0
    streak_lens = []
    cur = 0
    for r in rows:
        if not r[hit_k]:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            if cur:
                streak_lens.append(cur)
            cur = 0
    if cur:
        streak_lens.append(cur)

    cum_inv = 0
    cum_ret = 0
    cur = 0
    streak_ends = []
    for i, r in enumerate(rows):
        cum_inv += r[inv_k]
        cum_ret += r[ret_k]
        if not r[hit_k]:
            cur += 1
        else:
            if cur:
                streak_ends.append((i - 1, cur, cum_inv, cum_ret))
            cur = 0
    if cur:
        streak_ends.append((len(rows) - 1, cur, cum_inv, cum_ret))

    recoveries = []
    for last_i, slen, inv_a, ret_a in streak_ends:
        roi_now = ret_a / inv_a * 100 if inv_a else 100.0
        if roi_now >= 100:
            recoveries.append({"streak_len": slen, "races_to_100": 0, "recovered": True})
            continue
        ok = False
        ci, cr = inv_a, ret_a
        for j in range(last_i + 1, len(rows)):
            ci += rows[j][inv_k]
            cr += rows[j][ret_k]
            if cr / ci * 100 >= 100:
                recoveries.append(
                    {"streak_len": slen, "races_to_100": j - last_i, "recovered": True}
                )
                ok = True
                break
        if not ok:
            recoveries.append({"streak_len": slen, "races_to_100": None, "recovered": False})

    rec_ok = [x for x in recoveries if x["recovered"]]
    avg_rec = sum(x["races_to_100"] for x in rec_ok) / len(rec_ok) if rec_ok else None
    return {
        "max_consecutive_losses": max_streak,
        "streak_count": len(streak_lens),
        "streak_distribution": dict(sorted(Counter(streak_lens).items())),
        "streak_end_events": len(recoveries),
        "recovered_events": len(rec_ok),
        "avg_races_to_cumulative_100_after_streak": (
            round(avg_rec, 2) if avg_rec is not None else None
        ),
        "recovery_by_streak_len": _recovery_by_len(rec_ok),
    }


def _recovery_by_len(rec_ok):
    buckets = {}
    for x in rec_ok:
        buckets.setdefault(x["streak_len"], []).append(x["races_to_100"])
    return {
        str(k): {"n": len(v), "avg_races": round(sum(v) / len(v), 2)}
        for k, v in sorted(buckets.items())
    }


def main():
    master = load_master()
    win_cfg = ScoringConfig.load_tuned()
    _, ex_cfg = load_split_scoring_configs()
    periods = [
        ("2024", "20240101", "20241231"),
        ("2025", "20250101", "20251231"),
        ("2026", "20260101", "20261231"),
    ]

    report = {"segment_definitions": {}, "by_year": {}, "pooled": {}}
    for seg in ("exotic_upset_high", "win_upset_high"):
        all_rows = []
        for label, f, t in periods:
            print(f"loading {label} {seg}...", flush=True)
            recs = load_period(f, t, master, win_cfg, ex_cfg)
            yr = rows_from_recs(recs, label, seg)
            all_rows.extend(yr)
            box_pts = sorted({r["box_pts"] for r in yr})
            report.setdefault("by_year", {}).setdefault(seg, {})[label] = {
                "box_point_counts": box_pts,
                "box": roi_part(yr, "box_inv", "box_ret"),
                "formation5": roi_part(yr, "form_inv", "form_ret"),
                "streaks_box": streak_analysis(yr, "box_hit", "box_inv", "box_ret"),
            }
            print(f"  {label}: n={len(yr)} box_pts={box_pts}", flush=True)

        report.setdefault("pooled", {})[seg] = {
            "box": roi_part(all_rows, "box_inv", "box_ret"),
            "formation5": roi_part(all_rows, "form_inv", "form_ret"),
            "streaks_box": streak_analysis(all_rows, "box_hit", "box_inv", "box_ret"),
        }

    report["segment_definitions"] = {
        "exotic_upset_high": "exotic_profile=upset and exotic_high and sanren BOX",
        "win_upset_high": "win_profile=upset and win_high and sanren BOX",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
