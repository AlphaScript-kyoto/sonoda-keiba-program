"""レース期待値スコアと SS〜C ティア（暫定ルール・閾値は JSON）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.predictor.bets import RaceBetPlan

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_TIERS_PATH = ROOT / "config" / "expectation_tiers.json"

TIER_ORDER: Tuple[str, ...] = ("SS", "S", "A", "B", "C")
TIER_RANK: Dict[str, int] = {t: i for i, t in enumerate(TIER_ORDER)}


@dataclass(frozen=True)
class ExpectationTierConfig:
    tier_min_scores: Dict[str, int]
    note_tiers: frozenset[str]
    x_tiers: frozenset[str]
    venue_label: str = "園田"

    @classmethod
    def from_dict(cls, data: dict) -> "ExpectationTierConfig":
        mins = {k: int(v) for k, v in data["tier_min_scores"].items()}
        for t in TIER_ORDER:
            if t not in mins:
                raise ValueError(f"tier_min_scores missing {t}")
        return cls(
            tier_min_scores=mins,
            note_tiers=frozenset(data.get("note_tiers", ["SS", "S"])),
            x_tiers=frozenset(data.get("x_tiers", ["A", "B", "C"])),
            venue_label=str(data.get("venue_label", "園田")),
        )


def load_expectation_config(path: Optional[Path] = None) -> ExpectationTierConfig:
    p = path or DEFAULT_TIERS_PATH
    with open(p, encoding="utf-8") as f:
        return ExpectationTierConfig.from_dict(json.load(f))


def is_ss_eligible(plan: RaceBetPlan) -> bool:
    """SS 付与の最低条件（厳しめ）。"""
    return (
        plan.exotic_confidence == "高"
        and plan.exotic_profile == "堅"
        and plan.win_prob_top >= 0.88
        and plan.prob_gap >= 0.70
    )


def compute_expectation_score(plan: RaceBetPlan) -> int:
    """暫定スコア（0〜100）。三連「高」以外は 0。"""
    if plan.exotic_confidence != "高":
        return 0

    score = 25
    if plan.exotic_profile == "堅":
        score += 15
    else:
        score += 5

    if plan.win_prob_top >= 0.90:
        score += 12
    elif plan.win_prob_top >= 0.85:
        score += 8
    elif plan.win_prob_top >= 0.82:
        score += 4

    if plan.prob_gap >= 0.75:
        score += 12
    elif plan.prob_gap >= 0.70:
        score += 8
    elif plan.prob_gap >= 0.60:
        score += 4

    if plan.confidence == "高":
        score += 8
    if plan.win_profile == "堅":
        score += 4

    return min(score, 100)


def tier_from_score(
    score: int,
    config: Optional[ExpectationTierConfig] = None,
    plan: Optional[RaceBetPlan] = None,
) -> str:
    cfg = config or load_expectation_config()
    tier = "C"
    for t in TIER_ORDER:
        if score >= cfg.tier_min_scores[t]:
            tier = t
            break
    if tier == "SS" and plan is not None and not is_ss_eligible(plan):
        tier = "S"
    return tier


def apply_expectation_to_plan(
    plan: RaceBetPlan,
    config: Optional[ExpectationTierConfig] = None,
) -> RaceBetPlan:
    """RaceBetPlan に expectation_score / expectation_tier を付与。"""
    cfg = config or load_expectation_config()
    score = compute_expectation_score(plan)
    plan.expectation_score = score
    plan.expectation_tier = tier_from_score(score, cfg, plan)
    return plan


def sort_plans_by_race_no(plans: List[RaceBetPlan]) -> List[RaceBetPlan]:
    return sorted(plans, key=lambda p: p.race_no)


def sort_plans_by_expectation(plans: List[RaceBetPlan]) -> List[RaceBetPlan]:
    return sorted(
        plans,
        key=lambda p: (TIER_RANK.get(p.expectation_tier, 99), p.race_no),
    )
