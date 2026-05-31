"""馬券戦略のバックテスト・回収率計算。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from src.predictor.bets import (
    BetStrategyConfig,
    ConfidenceThresholds,
    DEFAULT_STRATEGY,
    DEFAULT_WIN_THRESHOLDS,
    assign_marks,
    build_race_bet_plan,
    build_sanrenpuku_box,
    build_sanrenpuku_nagashi,
    build_sanrentan_formation,
    build_wide_formation,
    build_wide_formation_upset,
    check_sanrenpuku_box_hit,
    check_sanrenpuku_hit,
    check_sanrentan_hit,
    check_wide_hits,
    detect_exotic_profile,
    detect_win_profile,
    collect_race_signals,
    is_volatile_race,
    is_high_confidence,
    matches_threshold,
)
from src.predictor.scoring_config import ScoringConfig
from src.predictor.score import load_master, predict_date, set_scoring_config
from src.scraper.payback import RacePayback, fetch_paybacks, load_payback_cache, payback_from_dict, wide_payout_yen

BET_UNIT = 100


@dataclass
class BetTypeResult:
    name: str
    races: int = 0
    points: int = 0
    hits: int = 0
    investment: int = 0
    return_yen: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.races if self.races else 0.0

    @property
    def roi(self) -> float:
        return self.return_yen / self.investment if self.investment else 0.0


@dataclass
class RaceBacktestRow:
    date: str
    race_no: int
    race_name: str
    pred_umaban: str
    pred_horse: str
    actual_1st: str
    win_hit: bool
    place_hit: bool
    confidence: str
    sanrenpuku_hit: Optional[bool] = None
    sanrentan_hit: Optional[bool] = None
    wide_hit: Optional[bool] = None
    win_prob_top: float = 0.0
    prob_gap: float = 0.0


@dataclass
class BacktestReport:
    from_date: str
    to_date: str
    race_count: int
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    win_pick: BetTypeResult = field(default_factory=lambda: BetTypeResult("単勝◎(堅のみ)"))
    place_pick: BetTypeResult = field(default_factory=lambda: BetTypeResult("複勝◎"))
    sanrenpuku: BetTypeResult = field(
        default_factory=lambda: BetTypeResult("三連複(自信度高)")
    )
    sanrentan: BetTypeResult = field(
        default_factory=lambda: BetTypeResult("三連単FM(堅・自信度高)")
    )
    wide: BetTypeResult = field(
        default_factory=lambda: BetTypeResult("ワイド(自信度高)")
    )
    rows: List[RaceBacktestRow] = field(default_factory=list)


@dataclass
class _RaceRecord:
    date: str
    race_no: int
    race_name: str
    pred_umaban: str
    pred_horse: str
    actual_1st: str
    win_prob_top: float
    prob_gap: float
    win_hit: bool
    place_hit: bool
    win_payout: int
    place_payout: int
    sanrenpuku_points: int
    sanrenpuku_box_points: int
    sanrentan_points: int
    sanrenpuku_hit: bool
    sanrenpuku_box_hit: bool
    sanrentan_hit: bool
    wide_firm_points: int
    wide_upset_points: int
    wide_firm_hit: bool
    wide_upset_hit: bool
    wide_firm_return_yen: int
    wide_upset_return_yen: int
    fuku3_yen: int
    tan3_yen: int
    win_profile: str = "堅"
    exotic_profile: str = "堅"
    race_profile: str = "堅"
    is_volatile: bool = False
    exotic_high: bool = False
    win_high: bool = False


def _finish_order(race_df: pd.DataFrame) -> List[str]:
    valid = race_df.copy()
    valid["finish"] = pd.to_numeric(valid["finish"], errors="coerce")
    valid = valid.dropna(subset=["finish"])
    valid = valid.sort_values("finish")
    return [str(u) for u in valid["umaban"]]


def _win_payout_yen(umaban: str, payback: Optional[RacePayback], odds: str) -> int:
    if payback and umaban in payback.tansho:
        return payback.tansho[umaban]
    val = pd.to_numeric(odds, errors="coerce")
    if pd.notna(val) and float(val) > 0:
        return int(round(float(val) * BET_UNIT))
    return 0


def _place_payout_yen(umaban: str, payback: Optional[RacePayback]) -> int:
    if payback and umaban in payback.fukusho:
        return payback.fukusho[umaban]
    return 0


def _load_paybacks_for_races(
    race_ids: List[str], *, fetch_missing: bool, refresh_if_missing_wide: bool = True
) -> Dict[str, RacePayback]:
    cache = load_payback_cache()
    out: Dict[str, RacePayback] = {}
    missing: List[str] = []

    for rid in race_ids:
        if rid in cache:
            entry = cache[rid]
            if refresh_if_missing_wide and not entry.get("wide"):
                missing.append(rid)
                continue
            out[rid] = payback_from_dict({**entry, "race_id": rid})
        elif fetch_missing:
            missing.append(rid)

    if missing:
        fetched = fetch_paybacks(
            missing,
            use_cache=True,
            stop_on_block=True,
            refresh_if_missing_wide=True,
        )
        out.update(fetched)

    return out


def _collect_race_records(
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    master: pd.DataFrame,
    paybacks: Dict[str, RacePayback],
    config: Optional[ScoringConfig] = None,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> List[_RaceRecord]:
    """予想・結果・払戻を1レース1行に事前集計（閾値探索用）。"""
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ].copy()
    records: List[_RaceRecord] = []

    for date in sorted(hist["date"].astype(str).unique()):
        scored = predict_date(date, master=master, fetch_entries=False, config=config)
        if scored.empty:
            continue

        actual_by_race = {
            rid: grp for rid, grp in hist[hist["date"].astype(str) == date].groupby("race_id")
        }

        for race_id, pred_group in scored.groupby("race_id", sort=False):
            race_id = str(race_id)
            actual = actual_by_race.get(race_id)
            if actual is None or actual.empty:
                continue

            finish = _finish_order(actual)
            if not finish:
                continue

            top5 = assign_marks(pred_group)
            win_high, p1, gap = is_high_confidence(pred_group, strategy.win)
            signals = collect_race_signals(pred_group, p1, gap)
            win_profile = detect_win_profile(signals, strategy)
            exotic_profile = detect_exotic_profile(signals, strategy)
            volatile = is_volatile_race(signals, strategy)
            top = pred_group.sort_values("rank_pred").iloc[0]
            pred_u = str(top["umaban"])
            race_no = int(pred_group["race_no"].iloc[0])
            race_name = str(pred_group.get("race_name", pd.Series([""])).iloc[0])
            win_hit = pred_u == finish[0]
            place_hit = pred_u in finish[:3]
            pb = paybacks.get(race_id)

            winner_row = actual.loc[actual["umaban"].astype(str) == pred_u]
            odds = winner_row["odds"].iloc[0] if not winner_row.empty else ""

            nagashi = build_sanrenpuku_nagashi(top5)
            box = build_sanrenpuku_box(
                top5,
                pred_group,
                core_count=strategy.upset_box_core,
                extra_longshots=strategy.upset_longshot_count,
            )
            formation = build_sanrentan_formation(top5)
            wide_firm = build_wide_formation(top5)
            wide_upset = build_wide_formation_upset(top5)

            sp_hit = check_sanrenpuku_hit(nagashi, finish) if nagashi else False
            box_hit = check_sanrenpuku_box_hit(box, finish) if box else False
            st_hit = check_sanrentan_hit(formation, finish) if formation else False
            wd_firm_ret = 0
            wd_upset_ret = 0
            wd_firm_hit = False
            wd_upset_hit = False
            if wide_firm:
                firm_hits = check_wide_hits(wide_firm, finish)
                wd_firm_hit = len(firm_hits) > 0
                wd_firm_ret = wide_payout_yen(firm_hits, pb)
            if wide_upset:
                upset_hits = check_wide_hits(wide_upset, finish)
                wd_upset_hit = len(upset_hits) > 0
                wd_upset_ret = wide_payout_yen(upset_hits, pb)

            records.append(
                _RaceRecord(
                    date=date,
                    race_no=race_no,
                    race_name=race_name,
                    pred_umaban=pred_u,
                    pred_horse=str(top.get("horse_name", "")),
                    actual_1st=finish[0],
                    win_prob_top=p1,
                    prob_gap=gap,
                    win_hit=win_hit,
                    place_hit=place_hit,
                    win_payout=_win_payout_yen(pred_u, pb, str(odds)),
                    place_payout=_place_payout_yen(pred_u, pb),
                    sanrenpuku_points=nagashi.points if nagashi else 0,
                    sanrenpuku_box_points=box.points if box else 0,
                    sanrentan_points=formation.points if formation else 0,
                    sanrenpuku_hit=sp_hit,
                    sanrenpuku_box_hit=box_hit,
                    sanrentan_hit=st_hit,
                    wide_firm_points=wide_firm.points if wide_firm else 0,
                    wide_upset_points=wide_upset.points if wide_upset else 0,
                    wide_firm_hit=wd_firm_hit,
                    wide_upset_hit=wd_upset_hit,
                    wide_firm_return_yen=wd_firm_ret,
                    wide_upset_return_yen=wd_upset_ret,
                    fuku3_yen=pb.fuku3_yen if pb else 0,
                    tan3_yen=pb.tan3_yen if pb else 0,
                    win_profile=win_profile,
                    exotic_profile=exotic_profile,
                    race_profile=exotic_profile,
                    is_volatile=volatile,
                    exotic_high=False,
                    win_high=win_high,
                )
            )

    records.sort(key=lambda r: (r.date, r.race_no))
    return records


def _exotic_high_for_record(
    rec: _RaceRecord, strategy: BetStrategyConfig = DEFAULT_STRATEGY
) -> bool:
    th = strategy.exotic_upset if rec.exotic_profile == "荒" else strategy.exotic_firm
    return matches_threshold(rec.win_prob_top, rec.prob_gap, th)


def _aggregate_records(
    records: List[_RaceRecord],
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    thresholds: Optional[ConfidenceThresholds] = None,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> BacktestReport:
    """事前集計レコードから回収率を算出。"""
    th = thresholds or DEFAULT_WIN_THRESHOLDS
    report = BacktestReport(
        from_date=from_yyyymmdd,
        to_date=to_yyyymmdd,
        race_count=len(records),
        thresholds=th,
    )

    for rec in records:
        win_high = matches_threshold(rec.win_prob_top, rec.prob_gap, th)
        exotic_high = _exotic_high_for_record(rec, strategy)
        row = RaceBacktestRow(
            date=rec.date,
            race_no=rec.race_no,
            race_name=rec.race_name,
            pred_umaban=rec.pred_umaban,
            pred_horse=rec.pred_horse,
            actual_1st=rec.actual_1st,
            win_hit=rec.win_hit,
            place_hit=rec.place_hit,
            confidence="高" if win_high else "通常",
            win_prob_top=rec.win_prob_top,
            prob_gap=rec.prob_gap,
        )

        skip_win = rec.win_profile == "荒" and strategy.skip_win_on_upset
        if not skip_win:
            report.win_pick.races += 1
            report.win_pick.points += 1
            report.win_pick.investment += BET_UNIT
            if rec.win_hit:
                report.win_pick.hits += 1
                report.win_pick.return_yen += rec.win_payout

        report.place_pick.races += 1
        report.place_pick.points += 1
        report.place_pick.investment += BET_UNIT
        if rec.place_hit:
            report.place_pick.hits += 1
            report.place_pick.return_yen += rec.place_payout

        if exotic_high:
            if rec.exotic_profile == "堅":
                sp_pts = rec.sanrenpuku_points
                sp_hit = rec.sanrenpuku_hit
                st_pts = rec.sanrentan_points
                st_hit = rec.sanrentan_hit
                if rec.is_volatile:
                    wd_pts = rec.wide_upset_points
                    wd_hit = rec.wide_upset_hit
                    wd_return = rec.wide_upset_return_yen
                else:
                    wd_pts = rec.wide_firm_points
                    wd_hit = rec.wide_firm_hit
                    wd_return = rec.wide_firm_return_yen
            else:
                sp_pts = rec.sanrenpuku_box_points
                sp_hit = rec.sanrenpuku_box_hit
                st_pts = 0
                st_hit = False
                wd_pts = rec.wide_upset_points
                wd_hit = rec.wide_upset_hit
                wd_return = rec.wide_upset_return_yen

            if sp_pts:
                row.sanrenpuku_hit = sp_hit
                report.sanrenpuku.races += 1
                report.sanrenpuku.points += sp_pts
                report.sanrenpuku.investment += sp_pts * BET_UNIT
                if sp_hit:
                    report.sanrenpuku.hits += 1
                    report.sanrenpuku.return_yen += rec.fuku3_yen

            if st_pts:
                row.sanrentan_hit = st_hit
                report.sanrentan.races += 1
                report.sanrentan.points += st_pts
                report.sanrentan.investment += st_pts * BET_UNIT
                if st_hit:
                    report.sanrentan.hits += 1
                    report.sanrentan.return_yen += rec.tan3_yen

            if wd_pts:
                row.wide_hit = wd_hit
                report.wide.races += 1
                report.wide.points += wd_pts
                report.wide.investment += wd_pts * BET_UNIT
                if wd_hit:
                    report.wide.hits += 1
                    report.wide.return_yen += wd_return

        report.rows.append(row)

    return report


def backtest_period(
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    fetch_payback: bool = False,
    thresholds: Optional[ConfidenceThresholds] = None,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
    records: Optional[List[_RaceRecord]] = None,
    config: Optional[ScoringConfig] = None,
) -> BacktestReport:
    """期間内の全レースをオフライン予想し、回収率を集計。"""
    th = thresholds or DEFAULT_WIN_THRESHOLDS
    master = master if master is not None else load_master()
    cfg = config or ScoringConfig.load_tuned()
    set_scoring_config(cfg)

    if records is None:
        hist = master[
            (master["date"].astype(str) >= from_yyyymmdd)
            & (master["date"].astype(str) <= to_yyyymmdd)
        ].copy()
        if hist.empty:
            return BacktestReport(from_date=from_yyyymmdd, to_date=to_yyyymmdd, race_count=0)

        race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
        paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)
        records = _collect_race_records(
            from_yyyymmdd, to_yyyymmdd, master, paybacks, cfg, strategy
        )

    return _aggregate_records(records, from_yyyymmdd, to_yyyymmdd, th, strategy)


@dataclass
class TuneResult:
    thresholds: ConfidenceThresholds
    high_races: int
    win_roi_high: float
    sanrenpuku_roi: float
    sanrentan_roi: float
    sanrenpuku_hit_rate: float
    sanrentan_hit_rate: float
    combined_roi: float


def tune_confidence_thresholds(
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    min_high_races: int = 5,
    max_high_races: int = 80,
) -> List[TuneResult]:
    """閾値グリッドを探索し、三連系回収率が良い組み合わせを返す。"""
    master = master if master is not None else load_master()
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    cfg = ScoringConfig.load_tuned()
    records = _collect_race_records(from_yyyymmdd, to_yyyymmdd, master, paybacks, cfg)

    win_probs = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
    alt_probs = [0.65, 0.70, 0.75, 0.80]
    gaps = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    modes = ["or", "and", "strict"]

    results: List[TuneResult] = []
    for mode in modes:
        for wp in win_probs:
            for gap in gaps:
                if mode == "and":
                    combos = [
                        ConfidenceThresholds(
                            win_prob=wp, win_prob_alt=wp, prob_gap=gap, mode="and"
                        )
                    ]
                else:
                    combos = [
                        ConfidenceThresholds(
                            win_prob=wp,
                            win_prob_alt=alt,
                            prob_gap=gap,
                            mode=mode,
                        )
                        for alt in alt_probs
                        if alt < wp
                    ]
                for th in combos:
                    report = _aggregate_records(
                        records, from_yyyymmdd, to_yyyymmdd, th
                    )
                    high = report.sanrenpuku.races
                    if high < min_high_races or high > max_high_races:
                        continue

                    win_inv = 0
                    win_ret = 0
                    for rec in records:
                        if matches_threshold(rec.win_prob_top, rec.prob_gap, th):
                            win_inv += BET_UNIT
                            if rec.win_hit:
                                win_ret += rec.win_payout
                    win_roi_high = win_ret / win_inv if win_inv else 0.0

                    inv = report.sanrenpuku.investment + report.sanrentan.investment
                    ret = report.sanrenpuku.return_yen + report.sanrentan.return_yen
                    combined = ret / inv if inv else 0.0

                    results.append(
                        TuneResult(
                            thresholds=th,
                            high_races=high,
                            win_roi_high=win_roi_high,
                            sanrenpuku_roi=report.sanrenpuku.roi,
                            sanrentan_roi=report.sanrentan.roi,
                            sanrenpuku_hit_rate=report.sanrenpuku.hit_rate,
                            sanrentan_hit_rate=report.sanrentan.hit_rate,
                            combined_roi=combined,
                        )
                    )

    results.sort(key=lambda r: (r.combined_roi, r.sanrenpuku_roi), reverse=True)
    return results
