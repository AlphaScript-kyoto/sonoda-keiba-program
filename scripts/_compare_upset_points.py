"""Compare sanren bet styles by point count for upset x High (strict hits)."""
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
    build_sanrenpuku_box,
    build_sanrenpuku_formation_firm,
    build_sanrenpuku_nagashi,
    check_sanrenpuku_box_hit,
    check_sanrenpuku_formation_firm_hit,
    check_sanrenpuku_hit,
)
from src.predictor.score import load_master, predict_date
from src.predictor.scoring_config import load_split_scoring_configs

UPSET = "\u8352"


def main() -> None:
    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    dates = sorted(
        d for d in master["date"].astype(str).unique() if d[:4] in ("2024", "2025", "2026")
    )
    rids = sorted(
        master.loc[master["date"].astype(str).isin(dates), "race_id"].astype(str).unique()
    )
    pb = _load_paybacks_for_races(rids, fetch_missing=False)
    stats = defaultdict(lambda: {"r": 0, "pts": 0, "inv": 0, "ret": 0, "hits": 0})

    for i, date in enumerate(dates, 1):
        if i % 50 == 0:
            print(f"progress {i}/{len(dates)}", flush=True)
        dw = predict_date(date, master=master, fetch_entries=False, config=win_cfg)
        de = predict_date(date, master=master, fetch_entries=False, config=ex_cfg)
        ex = {str(r): g for r, g in de.groupby("race_id", sort=False)}
        hist = master[master["date"].astype(str) < date]
        day = master[master["date"].astype(str) == date]
        for rid in sorted(day["race_id"].astype(str).unique()):
            wg = dw[dw["race_id"].astype(str) == rid]
            if wg.empty:
                continue
            fin = _finish_order(master[master["race_id"].astype(str) == rid])
            if len(fin) < 3:
                continue
            eg = ex.get(rid, wg)
            plan = build_race_bet_plan(
                wg, exotic_race=eg, strategy=DEFAULT_STRATEGY, master=hist, before_date=date
            )
            if plan.exotic_profile != UPSET or plan.exotic_confidence != "\u9ad8":
                continue
            top5 = assign_marks(eg)
            pay = pb.get(rid)
            fuku = pay.fuku3_yen if pay else 0

            candidates = []
            f = build_sanrenpuku_formation_firm(top5)
            if f:
                candidates.append(
                    ("form5", f.points, check_sanrenpuku_formation_firm_hit(f, fin))
                )
            n = build_sanrenpuku_nagashi(top5)
            if n:
                candidates.append(("nagashi6", n.points, check_sanrenpuku_hit(n, fin)))
            for label, core, extra in [
                ("box4_top4", 4, 0),
                ("box10_top5", 5, 0),
                ("box20_4+2", 4, 1),
            ]:
                b = build_sanrenpuku_box(top5, eg, core_count=core, extra_longshots=extra)
                if b and b.points:
                    candidates.append((label, b.points, check_sanrenpuku_box_hit(b, fin)))

            for label, pts, hit in candidates:
                s = stats[label]
                s["r"] += 1
                s["pts"] += pts
                s["inv"] += pts * BET_UNIT
                s["ret"] += fuku if hit else 0
                if hit:
                    s["hits"] += 1

    lines = ["upset x High: points vs ROI (2024-2026, strict, final odds)", ""]
    lines.append(
        "buy            R  pts/R  hit%   ROI%     profit  yen/hit  inv/R"
    )
    order = ["form5", "nagashi6", "box4_top4", "box10_top5", "box20_4+2"]
    for label in order:
        s = stats[label]
        if not s["r"]:
            continue
        roi = s["ret"] / s["inv"] * 100
        hr = s["hits"] / s["r"] * 100
        pts_r = s["pts"] / s["r"]
        rph = s["ret"] / s["hits"] if s["hits"] else 0
        pl = s["ret"] - s["inv"]
        inv_r = s["inv"] / s["r"]
        lines.append(
            f"{label:<14} {s['r']:>3} {pts_r:>5.0f} {hr:>5.1f}% {roi:>6.1f}% "
            f"{pl:>+9,} {rph:>7,.0f} {inv_r:>6,.0f}"
        )

    text = "\n".join(lines)
    out = ROOT / "data" / "processed" / "logs" / "upset_points_compare.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
