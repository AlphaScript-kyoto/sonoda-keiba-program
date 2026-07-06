"""Scan ROI by bet type, segment, and tier (strict hit logic, 2024-2026 default).

Uses backtest pre-aggregated race records (formation = strict 5-ticket match).
Outputs:
  data/processed/logs/roi_scan_detail.csv
  data/processed/logs/roi_scan_summary.txt
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (  # noqa: E402
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY, should_skip_win_bet  # noqa: E402
from src.predictor.expectation import (  # noqa: E402
    TIER_RANK,
    compute_expectation_score,
    load_expectation_config,
    tier_from_score,
)
from src.predictor.bets import RaceBetPlan  # noqa: E402
from src.predictor.score import load_master  # noqa: E402
from src.predictor.scoring_config import load_split_scoring_configs  # noqa: E402

UPSET = "\u8352"
FIRM = "\u5805"
MIN_RACES_DEFAULT = 30


@dataclass
class Agg:
    races: int = 0
    points: int = 0
    investment: int = 0
    return_yen: int = 0
    hits: int = 0

    def add(self, pts: int, hit: bool, ret: int) -> None:
        self.races += 1
        self.points += pts
        self.investment += pts * BET_UNIT
        self.return_yen += ret
        if hit:
            self.hits += 1

    def roi_pct(self) -> float:
        return self.return_yen / self.investment * 100.0 if self.investment else 0.0

    def hit_rate(self) -> float:
        return self.hits / self.races if self.races else 0.0

    def profit(self) -> int:
        return self.return_yen - self.investment


def _tier_for_record(rec, exotic_high: bool, cfg) -> str:
    if not exotic_high:
        return "non-high"
    plan = RaceBetPlan(
        race_id="",
        race_no=rec.race_no,
        race_name=rec.race_name,
        confidence="\u9ad8" if rec.win_high else "\u901a\u5e38",
        exotic_confidence="\u9ad8",
        win_profile=rec.win_profile,
        exotic_profile=rec.exotic_profile,
        win_prob_top=rec.win_prob_top,
        prob_gap=rec.prob_gap,
        marks=[],
        fav_odds=rec.pred_odds,
    )
    score = compute_expectation_score(plan)
    return tier_from_score(score, cfg, plan)


def _segment(rec, exotic_high: bool) -> str:
    return f"{rec.exotic_profile}x{'High' if exotic_high else 'Normal'}"


def _fav_bucket(odds: float) -> str:
    if odds != odds or odds <= 0:  # NaN
        return "fav_unknown"
    if odds <= 1.5:
        return "fav_le1.5"
    if odds <= 2.0:
        return "fav_1.5-2.0"
    if odds <= 3.0:
        return "fav_2.0-3.0"
    return "fav_gt3.0"


@dataclass
class Scenario:
    key: str
    label: str
    bet_type: str
    profile_filter: Optional[str] = None  # e.g. "XxHigh"
    min_points: int = 1

    def matches(self, rec, exotic_high: bool, seg: str) -> bool:
        if self.profile_filter and seg != self.profile_filter:
            return False
        return True


def _iter_bet_legs(rec, exotic_high: bool, st=DEFAULT_STRATEGY) -> Iterable[Tuple[str, str, int, bool, int]]:
    """Yield (scenario_key, bet_type, points, hit, return_yen)."""
    skip_win = should_skip_win_bet(rec.win_profile, rec.pred_odds, st)
    seg = _segment(rec, exotic_high)

    if not skip_win:
        yield ("win", "tansho", 1, rec.win_hit, rec.win_payout if rec.win_hit else 0)

    if exotic_high and rec.exotic_profile == FIRM:
        if rec.is_volatile:
            if rec.wide_upset_points:
                yield (
                    "wide3_volatile",
                    "wide",
                    rec.wide_upset_points,
                    rec.wide_upset_hit,
                    rec.wide_upset_return_yen,
                )
            if rec.sanrenpuku_firm_box_points:
                yield (
                    "sanren_firm_box10",
                    "sanrenpuku_box",
                    rec.sanrenpuku_firm_box_points,
                    rec.sanrenpuku_firm_box_hit,
                    rec.fuku3_yen if rec.sanrenpuku_firm_box_hit else 0,
                )
        else:
            if rec.wide_firm_points:
                yield (
                    "wide2_firm",
                    "wide",
                    rec.wide_firm_points,
                    rec.wide_firm_hit,
                    rec.wide_firm_return_yen,
                )
            if rec.sanrenpuku_points:
                yield (
                    "sanren_nagashi6",
                    "sanrenpuku_nagashi",
                    rec.sanrenpuku_points,
                    rec.sanrenpuku_hit,
                    rec.fuku3_yen if rec.sanrenpuku_hit else 0,
                )
        if rec.sanrentan_points:
            yield (
                "sanrentan4",
                "sanrentan",
                rec.sanrentan_points,
                rec.sanrentan_hit,
                rec.tan3_yen if rec.sanrentan_hit else 0,
            )

    if exotic_high and rec.exotic_profile == UPSET:
        if rec.sanrenpuku_formation_points:
            yield (
                "sanren_form5",
                "sanrenpuku_formation",
                rec.sanrenpuku_formation_points,
                rec.sanrenpuku_formation_hit,
                rec.fuku3_yen if rec.sanrenpuku_formation_hit else 0,
            )
        if rec.sanrenpuku_box_points:
            yield (
                "sanren_box20",
                "sanrenpuku_box",
                rec.sanrenpuku_box_points,
                rec.sanrenpuku_box_hit,
                rec.fuku3_yen if rec.sanrenpuku_box_hit else 0,
            )
        if rec.wide_upset_points:
            yield (
                "wide3_upset",
                "wide",
                rec.wide_upset_points,
                rec.wide_upset_hit,
                rec.wide_upset_return_yen,
            )

    # Reference: formation 5pt on ALL exotic-high (incl. firm) for comparison
    if exotic_high and rec.sanrenpuku_formation_points:
        yield (
            "sanren_form5_ref",
            "sanrenpuku_formation_ref",
            rec.sanrenpuku_formation_points,
            rec.sanrenpuku_formation_hit,
            rec.fuku3_yen if rec.sanrenpuku_formation_hit else 0,
        )


def scan_records(
    records,
    *,
    min_races: int = MIN_RACES_DEFAULT,
) -> Tuple[List[dict], List[dict]]:
    cfg = load_expectation_config()
    cells: Dict[Tuple[str, str, str, str, str], Agg] = defaultdict(Agg)
    port_current_firm = Agg()
    port_upset_form = Agg()
    port_firm_sanren_only = Agg()

    for rec in records:
        eh = _exotic_high_for_record(rec, DEFAULT_STRATEGY)
        seg = _segment(rec, eh)
        tier = _tier_for_record(rec, eh, cfg)
        vol = "volatile" if rec.is_volatile else "stable"
        fav_b = _fav_bucket(rec.pred_odds)
        skip_win = should_skip_win_bet(rec.win_profile, rec.pred_odds, DEFAULT_STRATEGY)

        for scenario_key, _bet_type, pts, hit, ret in _iter_bet_legs(rec, eh):
            if pts <= 0:
                continue
            dims = (
                (scenario_key, seg, tier, vol, fav_b),
                (scenario_key, seg, "ALL", vol, fav_b),
                (scenario_key, seg, tier, "ALL", fav_b),
                (scenario_key, seg, tier, vol, "ALL"),
                (scenario_key, seg, "ALL", "ALL", "ALL"),
            )
            for key in dims:
                cells[key].add(pts, hit, ret)

            if eh and rec.exotic_profile == FIRM:
                if scenario_key == "win" and skip_win:
                    pass
                elif scenario_key in (
                    "win",
                    "wide2_firm",
                    "wide3_volatile",
                    "sanren_nagashi6",
                    "sanren_firm_box10",
                    "sanrentan4",
                ):
                    port_current_firm.add(pts, hit, ret)
                if scenario_key in ("sanren_nagashi6", "sanren_firm_box10"):
                    port_firm_sanren_only.add(pts, hit, ret)
            if eh and rec.exotic_profile == UPSET and scenario_key == "sanren_form5":
                port_upset_form.add(pts, hit, ret)

    rows: List[dict] = []
    for (scenario, seg, tier, vol, fav_b), agg in cells.items():
        if agg.races < min_races:
            continue
        rows.append(
            {
                "scenario": scenario,
                "segment": seg,
                "tier": tier,
                "volatile": vol,
                "fav_bucket": fav_b,
                "races": agg.races,
                "points": agg.points,
                "investment": agg.investment,
                "return_yen": agg.return_yen,
                "profit": agg.profit(),
                "roi_pct": round(agg.roi_pct(), 2),
                "hit_rate": round(agg.hit_rate(), 4),
                "hits": agg.hits,
            }
        )
    rows.sort(key=lambda r: (-r["roi_pct"], -r["races"]))

    portfolios = [
        _portfolio_row("current_firm_high_all_tickets", port_current_firm),
        _portfolio_row("firm_sanren_only", port_firm_sanren_only),
        _portfolio_row("upset_form5_only", port_upset_form),
    ]
    return rows, portfolios


def _portfolio_row(name: str, agg: Agg) -> dict:
    return {
        "scenario": name,
        "segment": "portfolio",
        "tier": "ALL",
        "volatile": "ALL",
        "fav_bucket": "ALL",
        "races": agg.races,
        "points": agg.points,
        "investment": agg.investment,
        "return_yen": agg.return_yen,
        "profit": agg.profit(),
        "roi_pct": round(agg.roi_pct(), 2),
        "hit_rate": round(agg.hit_rate(), 4),
        "hits": agg.hits,
    }


def _write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _format_summary(rows: List[dict], portfolios: List[dict], from_d: str, to_d: str, min_races: int) -> str:
    lines = [
        f"ROI scan {from_d}-{to_d} (strict formation / nagashi / box hits)",
        f"min_races per cell: {min_races}",
        "",
        "=== Portfolios ===",
    ]
    for p in sorted(portfolios, key=lambda r: -r["roi_pct"]):
        lines.append(
            f"  {p['scenario']}: {p['races']} bets ROI={p['roi_pct']}% "
            f"hit={p['hit_rate']*100:.1f}% inv={p['investment']:,} ret={p['return_yen']:,} "
            f"P/L={p['profit']:+,}"
        )

    lines.extend(["", "=== Top 25 cells (roi_pct, min races) ==="])
    lines.append(
        f"{'scenario':<22} {'segment':<14} {'tier':<8} {'vol':<8} {'fav':<12} "
        f"{'R':>5} {'hit%':>6} {'ROI%':>7} {'P/L':>10}"
    )
    lines.append("-" * 95)
    for r in rows[:25]:
        lines.append(
            f"{r['scenario']:<22} {r['segment']:<14} {r['tier']:<8} {r['volatile']:<8} "
            f"{r['fav_bucket']:<12} {r['races']:>5} {r['hit_rate']*100:>5.1f}% "
            f"{r['roi_pct']:>6.1f}% {r['profit']:>+10,}"
        )

    over100 = [r for r in rows if r["roi_pct"] >= 100.0]
    lines.extend(["", f"=== ROI >= 100% ({len(over100)} cells) ==="])
    for r in over100[:40]:
        lines.append(
            f"  {r['scenario']} | {r['segment']} | tier={r['tier']} | "
            f"{r['races']}R ROI={r['roi_pct']}% hit={r['hit_rate']*100:.1f}%"
        )

    # scenario x segment summary rows
    roll_rows = [
        r
        for r in rows
        if r["tier"] == "ALL" and r["volatile"] == "ALL" and r["fav_bucket"] == "ALL"
    ]
    roll_rows.sort(key=lambda r: (-r["roi_pct"], -r["races"]))
    lines.extend(["", "=== By scenario x segment (rolled up) ==="])
    for r in roll_rows:
        lines.append(
            f"  {r['scenario']:<22} {r['segment']:<14} {r['races']:>5}R "
            f"hit={r['hit_rate']*100:.1f}% ROI={r['roi_pct']:.1f}% P/L={r['profit']:+,}"
        )

    lines.extend(
        [
            "",
            "Note: fav_bucket uses pred_odds (axis horse) as proxy; tier uses same.",
            "R analysis not required for this scan; re-run with T-10 odds later.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan bet ROI by type and segment")
    parser.add_argument("--from", dest="from_date", default="20240101")
    parser.add_argument("--to", dest="to_date", default="20261231")
    parser.add_argument("--min-races", type=int, default=MIN_RACES_DEFAULT)
    args = parser.parse_args()

    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    hist = master[
        (master["date"].astype(str) >= args.from_date)
        & (master["date"].astype(str) <= args.to_date)
    ]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    print(f"Loading paybacks for {len(race_ids)} races...", flush=True)
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    print(f"Collecting records {args.from_date}-{args.to_date}...", flush=True)
    records = _collect_race_records(
        args.from_date, args.to_date, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
    )
    print(f"Records: {len(records)}", flush=True)

    rows, portfolios = scan_records(records, min_races=args.min_races)

    out_dir = ROOT / "data" / "processed" / "logs"
    csv_path = out_dir / "roi_scan_detail.csv"
    txt_path = out_dir / "roi_scan_summary.txt"
    _write_csv(csv_path, rows + portfolios)
    summary = _format_summary(rows, portfolios, args.from_date, args.to_date, args.min_races)
    txt_path.write_text(summary, encoding="utf-8")
    print(summary)
    print(f"\nWrote {csv_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()
