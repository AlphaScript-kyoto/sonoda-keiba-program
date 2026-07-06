"""P6 per-race payback evaluation (T-10 formation, admin notify)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.predictor.bets import (
    _race_class,
    check_sanrenpuku_formation_firm_hit,
)
from src.predictor.backtest import BET_UNIT, _finish_order
from src.predictor.score import load_master
from src.predictor.t10_daily_roi import _score_t10_race
from src.predictor.upset_p6_rules import is_p6_eligible_plan
from src.predictor.scoring_config import load_split_scoring_configs
from src.scraper.payback import RacePayback


@dataclass(frozen=True)
class P6PaybackEvaluation:
    hit: bool
    return_yen: int
    investment: int
    finish: tuple[str, str, str]
    race_class: str = ""


def evaluate_p6_payback_for_race(
    date_yyyymmdd: str,
    race_id: str,
    payback: Optional[RacePayback],
    master: Optional[pd.DataFrame] = None,
) -> Optional[P6PaybackEvaluation]:
    """T-10 P6 buy (sanren formation 5pt) hit check."""
    master_df = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    scored = _score_t10_race(date_yyyymmdd, race_id, master_df, win_cfg=win_cfg, ex_cfg=ex_cfg)
    if scored is None:
        return None

    plan, _top5, final_race, _snap = scored
    if not is_p6_eligible_plan(plan):
        return None

    formation = plan.sanrenpuku_formation
    if formation is None or formation.points <= 0:
        return None

    finish = _finish_order(final_race)
    if len(finish) < 3:
        return None

    hit = check_sanrenpuku_formation_firm_hit(formation, finish)
    return_yen = payback.fuku3_yen if hit and payback else 0
    invest = formation.points * BET_UNIT
    return P6PaybackEvaluation(
        hit=hit,
        return_yen=return_yen,
        investment=invest,
        finish=(finish[0], finish[1], finish[2]),
        race_class=_race_class(final_race),
    )


def build_p6_payback_message(
    *,
    race_no: int,
    race_name: str,
    evaluation: P6PaybackEvaluation,
) -> str:
    title_parts = [f"{int(race_no)}R"]
    name = str(race_name or "").strip()
    if name:
        title_parts.append(name)
    cls = str(evaluation.race_class or "").strip()
    if cls:
        title_parts.append(cls)
    title = "\u3000".join(title_parts)

    finish = "-".join(evaluation.finish)
    roi = (
        evaluation.return_yen / evaluation.investment * 100.0
        if evaluation.investment
        else 0.0
    )
    return "\n".join(
        [
            title,
            f"\u7d50\u679c {finish}",
            f"\u6255\u3044\u623b\u3057\uff1a{int(evaluation.return_yen):,}\u5186",
            f"\u56de\u53ce\u7387\uff1a{roi:.0f}\uff05",
        ]
    )
