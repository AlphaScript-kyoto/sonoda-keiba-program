"""S+ sanrenpuku formation 5-point ROI (strict 5-ticket match)."""
from collections import defaultdict
from dataclasses import dataclass
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
from src.predictor.t10_daily_roi import S_PLUS_BUY_LABEL, build_t10_daily_roi_report, is_tier_s_plus
from src.predictor.snapshot_compare import list_snapshot_race_ids


@dataclass
class Stats:
    races: int = 0
    hits: int = 0
    investment: int = 0
    return_yen: int = 0
    ss: int = 0
    s: int = 0
    no_pb: int = 0

    def roi(self) -> float:
        return self.return_yen / self.investment * 100 if self.investment else 0.0


def _check_loose_hit(formation, finish_order):
    if len(finish_order) < 3:
        return False
    top3 = set(finish_order[:3])
    if formation.axis_umaban not in top3:
        return False
    others = top3 - {formation.axis_umaban}
    return bool(others & set(formation.key_partner_umaban))


def main() -> None:
    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    dates = sorted(d for d in master["date"].astype(str).unique() if d[:4] in ("2024", "2025", "2026"))
    rids = sorted(master.loc[master["date"].astype(str).isin(dates), "race_id"].astype(str).unique())
    pb = _load_paybacks_for_races(rids, fetch_missing=False)

    strict = Stats()
    loose = Stats()
    byy_strict = defaultdict(Stats)
    byy_loose = defaultdict(Stats)
    byt = defaultdict(Stats)
    false_pos = 0

    for i, date in enumerate(dates, 1):
        if i % 25 == 0:
            print(f"progress {i}/{len(dates)} {date}", flush=True)
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
            fr = master[master["race_id"].astype(str) == rid]
            fin = _finish_order(fr)
            if len(fin) < 3:
                continue
            eg = ex.get(rid, wg)
            plan = build_race_bet_plan(wg, exotic_race=eg, strategy=DEFAULT_STRATEGY, master=hist, before_date=date)
            if not is_tier_s_plus(plan.expectation_tier):
                continue
            form = build_sanrenpuku_formation_firm(assign_marks(eg))
            if not form or form.points <= 0:
                continue

            inv = form.points * BET_UNIT
            hit_strict = check_sanrenpuku_formation_firm_hit(form, fin)
            hit_loose = _check_loose_hit(form, fin)
            if hit_loose and not hit_strict:
                false_pos += 1

            ret_strict = ret_loose = 0
            if hit_strict:
                p = pb.get(rid)
                if p:
                    ret_strict = p.fuku3_yen
                else:
                    strict.no_pb += 1
                    byy_strict[y].no_pb += 1
            if hit_loose:
                p = pb.get(rid)
                if p:
                    ret_loose = p.fuku3_yen
                else:
                    loose.no_pb += 1
                    byy_loose[y].no_pb += 1

            for bucket in (strict, byy_strict[y], byt[plan.expectation_tier]):
                bucket.races += 1
                bucket.investment += inv
                bucket.return_yen += ret_strict
                if hit_strict:
                    bucket.hits += 1
            for bucket in (loose, byy_loose[y]):
                bucket.races += 1
                bucket.investment += inv
                bucket.return_yen += ret_loose
                if hit_loose:
                    bucket.hits += 1
            if plan.expectation_tier == "SS":
                byy_strict[y].ss += 1
                byy_loose[y].ss += 1
            else:
                byy_strict[y].s += 1
                byy_loose[y].s += 1

    lines = []
    lines.append("Sonoda S+ ROI 2024-2026 (final odds)")
    lines.append("sanrenpuku formation 5pt strict ticket match")
    lines.append(S_PLUS_BUY_LABEL)
    lines.append("")
    lines.append("[strict] top3 must match one of 5 purchased tickets")
    for y in ("2024", "2025", "2026"):
        s = byy_strict[y]
        p = s.return_yen - s.investment
        sg = "+" if p > 0 else ""
        lines.append(f"{y}: {s.races}R SS{s.ss}/S{s.s} invest={s.investment:,} return={s.return_yen:,} P/L={sg}{p:,} ROI={s.roi():.1f}% hits={s.hits}/{s.races}")
    p = strict.return_yen - strict.investment
    sg = "+" if p > 0 else ""
    lines.append(f"TOTAL: {strict.races}R invest={strict.investment:,} return={strict.return_yen:,} P/L={sg}{p:,} ROI={strict.roi():.1f}% hits={strict.hits}/{strict.races}")
    for t in ("SS", "S"):
        s = byt[t]
        if s.races:
            lines.append(f" tier {t}: {s.races}R ROI={s.roi():.1f}% hits={s.hits}/{s.races}")

    lines.append("")
    lines.append("[diff vs old loose hit check]")
    lines.append(f"false positives removed: {false_pos}R")
    lines.append(f"old TOTAL: ROI={loose.roi():.1f}% hits={loose.hits}/{loose.races} return={loose.return_yen:,}")
    lines.append(f"strict TOTAL: ROI={strict.roi():.1f}% hits={strict.hits}/{strict.races} return={strict.return_yen:,}")
    lines.append(f"delta: hits -{loose.hits - strict.hits} return -{loose.return_yen - strict.return_yen:,} ROI {strict.roi() - loose.roi():+.1f}pt")

    t10 = Stats()
    t10y = defaultdict(Stats)
    for date in dates:
        if not list_snapshot_race_ids(date, label="t_minus_10"):
            continue
        rep = build_t10_daily_roi_report(date, master=master, fetch_payback=False)
        y = date[:4]
        for row in rep.races:
            for bucket in (t10, t10y[y]):
                bucket.races += 1
                bucket.investment += row.investment
                bucket.return_yen += row.return_yen
                if row.sanren_hit:
                    bucket.hits += 1
    lines.append("")
    lines.append("T-10 snapshot days only (strict via t10_daily_roi)")
    for y in sorted(t10y):
        s = t10y[y]
        lines.append(f" {y}: {s.races}R ROI={s.roi():.1f}% hits={s.hits}/{s.races}")
    lines.append(f" T10 TOTAL: {t10.races}R ROI={t10.roi():.1f}% hits={t10.hits}/{t10.races}")

    out = ROOT / "data" / "processed" / "logs" / "s_plus_roi_2024_2026_strict.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
