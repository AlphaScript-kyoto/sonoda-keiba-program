"""Portfolio backtest: firm win+wide+5pt sanren / upset sanren BOX only."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.predictor.backtest import (
    BET_UNIT,
    BetTypeResult,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import BetStrategyConfig, DEFAULT_STRATEGY, should_skip_win_bet
from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs
from src.predictor.score import load_master, set_scoring_config


@dataclass
class PortfolioReport:
    from_date: str
    to_date: str
    race_count: int
    win: BetTypeResult = field(default_factory=lambda: BetTypeResult("単勝◎(堅)"))
    wide: BetTypeResult = field(
        default_factory=lambda: BetTypeResult("ワイド◎-○▲(堅・自信度高)")
    )
    sanrenpuku_firm: BetTypeResult = field(
        default_factory=lambda: BetTypeResult("三連複5点(堅・自信度高)")
    )
    sanrenpuku_box: BetTypeResult = field(
        default_factory=lambda: BetTypeResult("三連複BOX(荒・自信度高)")
    )
    firm_exotic_races: int = 0
    upset_exotic_races: int = 0
    any_hit_races: int = 0

    @property
    def total_investment(self) -> int:
        return (
            self.win.investment
            + self.wide.investment
            + self.sanrenpuku_firm.investment
            + self.sanrenpuku_box.investment
        )

    @property
    def total_return(self) -> int:
        return (
            self.win.return_yen
            + self.wide.return_yen
            + self.sanrenpuku_firm.return_yen
            + self.sanrenpuku_box.return_yen
        )

    @property
    def total_roi(self) -> float:
        return self.total_return / self.total_investment if self.total_investment else 0.0

    @property
    def total_hit_rate(self) -> float:
        return self.any_hit_races / self.race_count if self.race_count else 0.0


def backtest_portfolio_period(
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    master=None,
    *,
    fetch_payback: bool = False,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> PortfolioReport:
    """
    Firm (堅): win + wide + 5pt sanren when exotic confidence high.
    Upset (荒): sanrenpuku BOX only when exotic confidence high.
    """
    st = strategy
    master_df = master if master is not None else load_master()
    win_cfg = ScoringConfig.load_tuned()
    ex_cfg = None
    if st.split_scoring:
        _, ex_cfg = load_split_scoring_configs()
    set_scoring_config(win_cfg)

    hist = master_df[
        (master_df["date"].astype(str) >= from_yyyymmdd)
        & (master_df["date"].astype(str) <= to_yyyymmdd)
    ]
    if hist.empty:
        return PortfolioReport(from_yyyymmdd, to_yyyymmdd, 0)

    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)
    records = _collect_race_records(
        from_yyyymmdd,
        to_yyyymmdd,
        master_df,
        paybacks,
        win_cfg,
        ex_cfg,
        st,
    )

    report = PortfolioReport(from_yyyymmdd, to_yyyymmdd, len(records))

    for rec in records:
        exotic_high = _exotic_high_for_record(rec, st)
        skip_win = should_skip_win_bet(rec.win_profile, rec.pred_odds, st)
        race_hit = False

        if rec.exotic_profile == "荒":
            if exotic_high and rec.sanrenpuku_box_points:
                report.upset_exotic_races += 1
                report.sanrenpuku_box.races += 1
                report.sanrenpuku_box.points += rec.sanrenpuku_box_points
                report.sanrenpuku_box.investment += rec.sanrenpuku_box_points * BET_UNIT
                if rec.sanrenpuku_box_hit:
                    report.sanrenpuku_box.hits += 1
                    report.sanrenpuku_box.return_yen += rec.fuku3_yen
                    race_hit = True
        else:
            if exotic_high:
                report.firm_exotic_races += 1
                if rec.wide_firm_points:
                    report.wide.races += 1
                    report.wide.points += rec.wide_firm_points
                    report.wide.investment += rec.wide_firm_points * BET_UNIT
                    if rec.wide_firm_hit:
                        report.wide.hits += 1
                        report.wide.return_yen += rec.wide_firm_return_yen
                        race_hit = True
                if rec.sanrenpuku_formation_points:
                    report.sanrenpuku_firm.races += 1
                    report.sanrenpuku_firm.points += rec.sanrenpuku_formation_points
                    report.sanrenpuku_firm.investment += (
                        rec.sanrenpuku_formation_points * BET_UNIT
                    )
                    if rec.sanrenpuku_formation_hit:
                        report.sanrenpuku_firm.hits += 1
                        report.sanrenpuku_firm.return_yen += rec.fuku3_yen
                        race_hit = True
            if not skip_win:
                report.win.races += 1
                report.win.points += 1
                report.win.investment += BET_UNIT
                if rec.win_hit:
                    report.win.hits += 1
                    report.win.return_yen += rec.win_payout
                    race_hit = True

        if race_hit:
            report.any_hit_races += 1

    return report
