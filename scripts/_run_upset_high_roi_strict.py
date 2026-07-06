"""Upset x High sanren formation 5pt ROI (strict ticket match)."""
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import BET_UNIT, _finish_order, _load_paybacks_for_races
from src.predictor.bets import (
    DEFAULT_STRATEGY,
    assign_marks,
    build_race_bet_plan,
    build_sanrenpuku_formation_firm,
    check_sanrenpuku_formation_firm_hit,
)
from src.predictor.score import load_master, predict_date
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.upset_high_bet_gate import UPSET
from src.predictor.expectation import apply_expectation_to_plan

def loose_hit(form, fin):
    top3 = set(fin[:3])
    if form.axis_umaban not in top3:
        return False
    return bool((top3 - {form.axis_umaban}) & set(form.key_partner_umaban))

def main():
    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    dates = sorted(d for d in master["date"].astype(str).unique() if d[:4] in ("2024", "2025", "2026"))
    rids = sorted(master.loc[master["date"].astype(str).isin(dates), "race_id"].astype(str).unique())
    pb = _load_paybacks_for_races(rids, fetch_missing=False)

    strict = defaultdict(lambda: {"r": 0, "h": 0, "inv": 0, "ret": 0})
    loose = defaultdict(lambda: {"r": 0, "h": 0, "inv": 0, "ret": 0})
    tiers = defaultdict(int)
    box_skip = 0

    for i, date in enumerate(dates, 1):
        if i % 40 == 0:
            print(f"progress {i}/{len(dates)}", flush=True)
        y = date[:4]
        day = master[master["date"].astype(str) == date]
        dw = predict_date(date, master=master, fetch_entries=False, config=win_cfg)
        de = predict_date(date, master=master, fetch_entries=False, config=ex_cfg)
        ex = {str(r): g for r, g in de.groupby("race_id", sort=False)}
        hist = master[master["date"].astype(str) < date]

        for rid in sorted(day["race_id"].astype(str).unique()):
            wg = dw[dw["race_id"].astype(str) == rid]
            if wg.empty:
                continue
            fin = _finish_order(master[master["race_id"].astype(str) == rid])
            if len(fin) < 3:
                continue
            eg = ex.get(rid, wg)
            plan = build_race_bet_plan(wg, exotic_race=eg, strategy=DEFAULT_STRATEGY, master=hist, before_date=date)
            if plan.exotic_profile != UPSET or plan.exotic_confidence != "\u9ad8":
                continue
            if plan.sanrenpuku_box is not None:
                box_skip += 1
                continue
            form = plan.sanrenpuku_formation or build_sanrenpuku_formation_firm(assign_marks(eg))
            if not form or form.points <= 0:
                continue

            tiers[plan.expectation_tier or "?"] += 1
            inv = form.points * BET_UNIT
            hs = check_sanrenpuku_formation_firm_hit(form, fin)
            hl = loose_hit(form, fin)
            p = pb.get(rid)
            ret_s = p.fuku3_yen if hs and p else 0
            ret_l = p.fuku3_yen if hl and p else 0

            for key in ("all", y):
                strict[key]["r"] += 1
                strict[key]["inv"] += inv
                strict[key]["ret"] += ret_s
                if hs:
                    strict[key]["h"] += 1
                loose[key]["r"] += 1
                loose[key]["inv"] += inv
                loose[key]["ret"] += ret_l
                if hl:
                    loose[key]["h"] += 1

    lines = []
    lines.append("Upset x High sanren formation 5pt ROI 2024-2026 (final odds, strict)")
    lines.append(f"skipped 247/box: {box_skip}R")
    lines.append(f"tier dist: {dict(tiers)}")
    lines.append("")
    for key in ("2024", "2025", "2026", "all"):
        s = strict[key]
        if not s["r"]:
            continue
        roi = s["ret"] / s["inv"] * 100
        hr = s["h"] / s["r"] * 100
        pl = s["ret"] - s["inv"]
        lines.append(
            f"{key}: {s['r']}R hits={s['h']}/{s['r']} ({hr:.1f}%) "
            f"invest={s['inv']:,} return={s['ret']:,} P/L={pl:+,} ROI={roi:.1f}%"
        )
    sa, la = strict["all"], loose["all"]
    lines.append("")
    lines.append(f"old loose: hits={la['h']}/{la['r']} ROI={la['ret']/la['inv']*100:.1f}% return={la['ret']:,}")
    lines.append(f"strict: hits={sa['h']}/{sa['r']} ROI={sa['ret']/sa['inv']*100:.1f}% return={sa['ret']:,}")
    lines.append(f"delta: hits -{la['h']-sa['h']} return -{la['ret']-sa['ret']:,}")

    out = ROOT / "data" / "processed" / "logs" / "upset_high_roi_2024_2026_strict.txt"
    text = "\n".join(lines)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {out}")

if __name__ == "__main__":
    main()
