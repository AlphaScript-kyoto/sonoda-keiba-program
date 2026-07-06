"""Backtest: 4-principle rules vs win+place plan (2024-2026)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.expectation import (
    compute_expectation_score,
    load_expectation_config,
    tier_from_score,
)

UPSET = "\u8352"
FIRM = "\u5805"
DEFAULT_CSV = ROOT / "r_analysis" / "input" / "backtest_rows.csv"
OUT_TXT = ROOT / "data" / "processed" / "logs" / "ev_rules_backtest.txt"


@dataclass
class Result:
    name: str
    races: int = 0
    bet_units: int = 0
    investment: int = 0
    return_yen: int = 0
    hits: int = 0
    days: int = 0

    def roi_pct(self) -> float:
        return self.return_yen / self.investment * 100 if self.investment else 0.0

    def hit_rate(self) -> float:
        return self.hits / self.races if self.races else 0.0

    def profit(self) -> int:
        return self.return_yen - self.investment

    def races_per_day(self) -> float:
        return self.races / self.days if self.days else 0.0


def _plan_row(row: pd.Series) -> RaceBetPlan:
    return RaceBetPlan(
        race_id="",
        race_no=int(row["race_no"]),
        race_name=str(row.get("race_name", "")),
        confidence="\u9ad8" if row["win_high"] else "\u901a\u5e38",
        exotic_confidence="\u9ad8" if row["exotic_high"] else "\u901a\u5e38",
        win_profile=str(row["win_profile"]),
        exotic_profile=str(row["exotic_profile"]),
        win_prob_top=float(row["win_prob_top"]),
        prob_gap=float(row["prob_gap"]),
        marks=[],
        fav_odds=float(row["pred_odds"]) if pd.notna(row["pred_odds"]) else 0.0,
    )


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    cfg = load_expectation_config()
    out = df.copy()
    scores, tiers = [], []
    win_evs, place_evs = [], []
    for _, row in out.iterrows():
        plan = _plan_row(row)
        sc = compute_expectation_score(plan)
        scores.append(sc)
        tiers.append(tier_from_score(sc, cfg, plan))
        odds = plan.fav_odds
        wp = plan.win_prob_top
        win_evs.append(wp * odds if odds and odds > 0 else 0.0)
        p_place = min(0.92, wp * 2.1)
        place_odds_est = max(1.1, 1.0 + odds * 0.22) if odds and odds > 0 else 1.2
        place_evs.append(p_place * place_odds_est)
    out["expectation_score"] = scores
    out["expectation_tier"] = tiers
    out["win_ev"] = win_evs
    out["place_ev"] = place_evs
    out["combo_ev"] = out["win_ev"] + out["place_ev"] * 0.5
    return out


def _cap_per_day(pool: pd.DataFrame, score_col: str, max_races: int) -> pd.DataFrame:
    if max_races <= 0 or pool.empty:
        return pool
    parts = []
    for _, grp in pool.groupby("date", sort=True):
        parts.append(grp.nlargest(max_races, score_col))
    return pd.concat(parts, ignore_index=True)


def _agg_sanren(name: str, g: pd.DataFrame) -> Result:
    r = Result(name=name)
    if g.empty:
        return r
    r.races = len(g)
    r.days = g["date"].nunique()
    r.bet_units = int(g["sanrenpuku_points"].sum())
    r.investment = int(g["sanrenpuku_invest_yen"].sum())
    r.return_yen = int(g["sanrenpuku_return_yen"].sum())
    r.hits = int(g["sanrenpuku_hit"].sum())
    return r


def _agg_win_place(name: str, g: pd.DataFrame) -> Result:
    r = Result(name=name)
    if g.empty:
        return r
    r.races = len(g)
    r.days = g["date"].nunique()
    r.bet_units = r.races * 2
    r.investment = int(g["win_invest_yen"].sum() + g["place_invest_yen"].sum())
    r.return_yen = int(g["win_return_yen"].sum() + g["place_return_yen"].sum())
    r.hits = int((g["win_hit"] | g["place_hit"]).sum())
    return r


def run_four_principles(df: pd.DataFrame) -> List[Result]:
    base = df[(df["exotic_high"]) & (df["exotic_profile"] == UPSET)].copy()
    base = base[base["sanrenpuku_invest_yen"] > 0]
    p6 = base[base["is_volatile"] & (base["pred_odds"] >= 2.0)].sort_values(["date", "race_no"])

    def chron_cap(pool: pd.DataFrame, n: int) -> pd.DataFrame:
        parts = []
        for _, grp in pool.groupby("date", sort=True):
            parts.append(grp.head(n))
        return pd.concat(parts, ignore_index=True) if parts else pool.iloc[0:0]

    scenarios: List[tuple[str, pd.DataFrame]] = [
        ("P0_old_all_upset_high", base),
        ("P6_pool_no_cap", p6),
        ("P6_op_chron_cap2", chron_cap(p6, 2)),
        ("P6_op_chron_cap3", chron_cap(p6, 3)),
    ]
    return [_agg_sanren(name, g) for name, g in scenarios]


def run_win_place(df: pd.DataFrame) -> List[Result]:
    playable = df[~df["skip_win"]].copy()
    playable = playable[playable["win_invest_yen"] > 0]
    scenarios: List[tuple[str, pd.DataFrame]] = []
    scenarios.append(("WP0_all_playable", playable))
    ev1 = playable[playable["win_ev"] >= 1.0]
    scenarios.append(("WP1_win_ev_ge_1", ev1))
    ev11 = playable[playable["win_ev"] >= 1.1]
    scenarios.append(("WP2_win_ev_ge_1.1", ev11))
    combo_ev = playable[(playable["win_ev"] >= 1.0) | (playable["place_ev"] >= 1.0)]
    scenarios.append(("WP3_win_or_place_ev", combo_ev))
    firm_hi = playable[(playable["exotic_high"]) & (playable["exotic_profile"] == FIRM)]
    scenarios.append(("WP4_firm_high", firm_hi))
    contrarian = playable[playable["pred_odds"] >= 3.0]
    scenarios.append(("WP5_axis_odds3plus", contrarian))
    scenarios.append(("WP6_ev1_ken3day", _cap_per_day(ev1, "win_ev", 3)))
    scenarios.append(("WP7_ev11_ken3day", _cap_per_day(ev11, "win_ev", 3)))
    scenarios.append(("WP8_combo_ev_ken3", _cap_per_day(combo_ev, "combo_ev", 3)))
    scenarios.append(("WP9_firm_ken3", _cap_per_day(firm_hi, "expectation_score", 3)))
    return [_agg_win_place(name, g) for name, g in scenarios]


def _fmt(r: Result) -> str:
    return (
        f"{r.name:<28} {r.races:>5}R {r.races_per_day():>4.1f}/day "
        f"hit={r.hit_rate()*100:>5.1f}% ROI={r.roi_pct():>6.1f}% "
        f"inv={r.investment:>9,} ret={r.return_yen:>9,} P/L={r.profit():>+9,}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()
    df = enrich(pd.read_csv(args.csv))
    df["date"] = df["date"].astype(str)

    lines = [
        "EV rules backtest (2024-2026, strict sanren in export)",
        f"rows={len(df)} dates={df['date'].nunique()}",
        "",
        "=== 4 principles: P6 operational (upset, volatile, axis odds>=2) ===",
        "",
    ]
    p_results = run_four_principles(df)
    p_results.sort(key=lambda r: (-r.roi_pct(), -r.races))
    lines.extend(_fmt(r) for r in p_results)

    lines.extend(["", "=== Win + Place plan ===", ""])
    wp_results = run_win_place(df)
    wp_results.sort(key=lambda r: (-r.roi_pct(), -r.races))
    lines.extend(_fmt(r) for r in wp_results)

    def best(rs: List[Result]) -> Result:
        ok = [r for r in rs if r.races >= 20]
        return max(ok, key=lambda r: (r.roi_pct(), r.profit)) if ok else rs[0]

    bp, bw = best(p_results), best(wp_results)
    lines.extend(
        [
            "",
            "=== Best (n>=20) ===",
            f"4principles: {bp.name} ROI={bp.roi_pct():.1f}% {bp.races}R P/L={bp.profit():+,}",
            f"win+place:   {bw.name} ROI={bw.roi_pct():.1f}% {bw.races}R P/L={bw.profit():+,}",
            "",
            "place_ev estimated; win_ev = win_prob_top * pred_odds (final odds).",
        ]
    )
    text = "\n".join(lines)
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {OUT_TXT}")


if __name__ == "__main__":
    main()
