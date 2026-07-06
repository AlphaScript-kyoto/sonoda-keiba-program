"""P6 upset-high buy rules: volatile + axis odds + sanren form 5pt, daily chronological cap."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.predictor.bets import RaceBetPlan
    from src.predictor.upset_high_bet_gate import UpsetHighBetState

UPSET = "\u8352"
P6_MIN_AXIS_ODDS = 2.0
P6_DAILY_MAX_RACES = 2


def is_p6_eligible_plan(
    plan: "RaceBetPlan",
    *,
    min_axis_odds: float = P6_MIN_AXIS_ODDS,
) -> bool:
    """Race-level P6 pool: upset x High, volatile, axis odds floor, formation 5pt."""
    formation = plan.sanrenpuku_formation
    axis_odds = plan.axis_odds if plan.axis_odds > 0 else plan.fav_odds
    return (
        plan.exotic_profile == UPSET
        and plan.exotic_confidence == "\u9ad8"
        and formation is not None
        and formation.points > 0
        and plan.is_volatile
        and axis_odds >= min_axis_odds
    )


def count_bets_on_date(state: "UpsetHighBetState", date_yyyymmdd: str) -> int:
    """Bets already signaled or settled today (unique race_no)."""
    race_nos: set[int] = set()
    for sig in state.pending_signals:
        if sig.date == date_yyyymmdd:
            race_nos.add(int(sig.race_no))
    for rec in state.recent_bets:
        if rec.date == date_yyyymmdd:
            race_nos.add(int(rec.race_no))
    return len(race_nos)


def p6_daily_cap_reason(
    state: "UpsetHighBetState",
    date_yyyymmdd: str,
    *,
    max_races: int = P6_DAILY_MAX_RACES,
) -> Optional[str]:
    if count_bets_on_date(state, date_yyyymmdd) >= max_races:
        return f"\u672c\u65e5{max_races}R\u4e0a\u9650"
    return None
