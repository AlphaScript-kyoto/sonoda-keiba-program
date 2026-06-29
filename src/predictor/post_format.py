"""note / X 投稿用テキスト生成。"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from src.predictor.bets import RaceBetPlan
from src.predictor.marks_display import sort_marks
from src.predictor.rationale import build_note_rationale_sections
from src.predictor.expectation import (
    ExpectationTierConfig,
    load_expectation_config,
    sort_plans_by_expectation,
)

MarkLine = Tuple[str, str, str]
X_MARKS_WITH_NAME = frozenset({"◎", "○", "▲"})


def _format_mark_line(mark: str, umaban: str, horse_name: str) -> str:
    if mark in X_MARKS_WITH_NAME:
        return f"{mark}：{umaban}　{horse_name}"
    return f"{mark}：{umaban}"


def format_marks_lines(
    marks: Sequence[MarkLine],
    *,
    name_marks: frozenset[str] = X_MARKS_WITH_NAME,
) -> List[str]:
    lines: List[str] = []
    for mark, umaban, horse_name in sort_marks(marks):
        if mark in name_marks:
            lines.append(f"{mark}：{umaban}　{horse_name}")
        else:
            lines.append(f"{mark}：{umaban}")
    return lines


def _format_note_race_sections(
    plan: RaceBetPlan,
    flow_lines: List[str],
    mark_lines: List[str],
    config: ExpectationTierConfig,
) -> str:
    lines = [
        f"【{config.venue_label} {plan.race_no}R】{plan.race_name}　期待値{plan.expectation_tier}",
    ]
    if flow_lines:
        lines.extend(["", "▼ レースの展開", *[f"・{ln}" for ln in flow_lines]])
    lines.extend(["", "▼ 印と根拠", *mark_lines])
    return "\n".join(lines)


def format_note_race_rich(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame] = None,
    config: Optional[ExpectationTierConfig] = None,
) -> str:
    """SS/S/A 用（展開・印と根拠）。"""
    cfg = config or load_expectation_config()
    flow_lines, mark_lines = build_note_rationale_sections(
        plan, win_df, exotic_df, sort_marks(plan.marks)
    )
    return _format_note_race_sections(plan, flow_lines, mark_lines, cfg)


def format_x_race(
    plan: RaceBetPlan,
    config: Optional[ExpectationTierConfig] = None,
) -> str:
    """B〜C 用（印中心・短文）。"""
    cfg = config or load_expectation_config()
    header = f"【{cfg.venue_label} {plan.race_no}R】　期待値{plan.expectation_tier}"
    body = format_marks_lines(plan.marks)
    return "\n".join([header, *body])


def format_race_copy(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame] = None,
    config: Optional[ExpectationTierConfig] = None,
) -> str:
    """期待値ティアに応じて note 詳細 / X 簡易 を切り替え。"""
    cfg = config or load_expectation_config()
    if plan.expectation_tier in cfg.note_tiers:
        return format_note_race_rich(plan, win_df, exotic_df, cfg)
    return format_x_race(plan, cfg)


def copy_channel_label(tier: str, config: Optional[ExpectationTierConfig] = None) -> str:
    cfg = config or load_expectation_config()
    if tier in cfg.note_tiers:
        return "詳細（展開・根拠）"
    return "簡易（印のみ）"


def _filter_tiers(
    plans: Iterable[RaceBetPlan],
    tiers: frozenset[str],
) -> List[RaceBetPlan]:
    return [p for p in plans if p.expectation_tier in tiers]


def format_x_day(
    plans: Iterable[RaceBetPlan],
    config: Optional[ExpectationTierConfig] = None,
) -> str:
    cfg = config or load_expectation_config()
    selected = sort_plans_by_expectation(_filter_tiers(plans, cfg.x_tiers))
    if not selected:
        return ""
    blocks = [format_x_race(p, cfg) for p in selected]
    return "\n\n".join(blocks)


def format_note_day(
    plans: Iterable[RaceBetPlan],
    config: Optional[ExpectationTierConfig] = None,
    *,
    win_df: Optional[pd.DataFrame] = None,
    exotic_df: Optional[pd.DataFrame] = None,
) -> str:
    cfg = config or load_expectation_config()
    selected = sort_plans_by_expectation(_filter_tiers(plans, cfg.note_tiers))
    if not selected or win_df is None or win_df.empty:
        return ""
    blocks = [format_note_race_rich(p, win_df, exotic_df, cfg) for p in selected]
    return "\n\n".join(blocks)


def day_post_summary(plans: Sequence[RaceBetPlan]) -> str:
    counts = {t: 0 for t in ("SS", "S", "A", "B", "C")}
    for p in plans:
        counts[p.expectation_tier] = counts.get(p.expectation_tier, 0) + 1
    parts = [f"{t}:{counts[t]}" for t in ("SS", "S", "A", "B", "C") if counts.get(t)]
    return " / ".join(parts)
