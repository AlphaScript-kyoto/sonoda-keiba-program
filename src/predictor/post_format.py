"""note / X 投稿用テキスト生成。"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from src.predictor.bets import RaceBetPlan
from src.predictor.marks_display import filter_race_df, sort_marks
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


def _exotic_summary(plan: RaceBetPlan) -> str:
    if plan.exotic_confidence != "高":
        return "三連複・三連単・ワイドは今回見送り（展開の読みが難しいため）。"
    if plan.exotic_profile == "荒":
        return "波乱寄り。三連複は広めの買い方（BOXなど）を想定しています。"
    return "展開が読みやすめ。三連複・ワイドなどを中心に検討しています。"


def _win_summary(plan: RaceBetPlan) -> str:
    if "見送り" in plan.confidence:
        return "単勝・複勝は見送り（荒れ要素があるため）。"
    if plan.confidence == "高" and plan.win_profile == "堅":
        return "単勝・複勝も◎中心で堅めに見ています。"
    if plan.confidence == "高":
        return "単勝・複勝も◎を軸に検討できます。"
    return "単勝・複勝は通常どおり◎を中心に。"


def _tier_recommendation_line(tier: str) -> str:
    return {
        "SS": "本日いちばんおすすめのレースです（noteで詳しく書きます）。",
        "S": "おすすめ度は高めです（noteで印と買い目の考え方を説明します）。",
    }.get(tier, "note向けのレースです。")


def _race_view_lines_note(
    plan: RaceBetPlan,
    *,
    exotic_df: Optional[pd.DataFrame] = None,
) -> List[str]:
    from src.predictor.score import race_display_model_probs

    disp_top, disp_gap = 0.0, 0.0
    if exotic_df is not None and not exotic_df.empty:
        race = filter_race_df(exotic_df, plan.race_no)
        disp_top, disp_gap = race_display_model_probs(race)
    disp_top_pct = f"{disp_top:.0%}".replace("%", "％")
    disp_gap_pct = f"{disp_gap:.0%}".replace("%", "％")
    return [
        "▼ このレースの見方",
        f"・{_tier_recommendation_line(plan.expectation_tier)}",
        f"・{_exotic_summary(plan)}",
        f"・{_win_summary(plan)}",
        f"・1番人気は{plan.fav_odds:.1f}倍。モデル上の本命度（レース内相対）はおおよそ{disp_top_pct}（2番手との差{disp_gap_pct}）。",
        "・※ モデル確率＝レース内の相対評価。勝率・連対率＝予想日より前の園田成績。",
    ]


def _bet_lines_note(plan: RaceBetPlan) -> List[str]:
    lines = ["", "▼ 買い目の目安（資金に合わせて調整してください）"]
    if plan.exotic_confidence != "高":
        lines.append("三連系は見送りのため、買い目の参考は控えめにしています。")
        return lines
    labels: List[str] = []
    for attr in ("sanrenpuku", "sanrenpuku_box", "sanrentan", "wide"):
        bet = getattr(plan, attr, None)
        if bet is not None:
            labels.append(_bet_label_plain(bet.label))
    if labels:
        lines.extend(labels)
    else:
        lines.append("（買い目は算出できませんでした）")
    lines.append("※ 1レースに全資金をのせすぎないでください。アレンジ歓迎です。")
    return lines


def _bet_label_plain(label: str) -> str:
    """技術的な label を読みやすく（数字・馬番はそのまま）。"""
    return (
        label.replace("三連複:", "三連複の目安：")
        .replace("三連複BOX:", "三連複BOXの目安：")
        .replace("三連単:", "三連単の目安：")
        .replace("ワイド:", "ワイドの目安：")
    )


def format_note_race_rich(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame] = None,
    config: Optional[ExpectationTierConfig] = None,
) -> str:
    """note 用（SS/S・根拠つき・一般読者向け）。"""
    cfg = config or load_expectation_config()
    flow_lines, mark_lines = build_note_rationale_sections(
        plan, win_df, exotic_df, sort_marks(plan.marks)
    )

    lines = [
        f"【{cfg.venue_label} {plan.race_no}R】{plan.race_name}　期待値{plan.expectation_tier}",
        "",
        *_race_view_lines_note(plan, exotic_df=exotic_df),
    ]
    if flow_lines:
        lines.extend(["", "▼ レースの展開", *[f"・{ln}" for ln in flow_lines]])
    lines.extend(["", "▼ 印と根拠", *mark_lines])
    lines.extend(_bet_lines_note(plan))
    return "\n".join(lines)


def _x_intro_line(plan: RaceBetPlan) -> str:
    tier = plan.expectation_tier
    if plan.exotic_confidence != "高":
        return "※ 印のみ参考（買い目は出していません）"
    if plan.exotic_profile == "荒":
        base = "※ 波乱寄り。印は参考用です"
    elif tier == "A":
        base = "※ X用・印のみ（軽めの参考）"
    elif tier == "B":
        base = "※ X用・印のみ（参考程度）"
    else:
        base = "※ X用・印のみ（控えめに見てください）"
    return base


def format_x_race(
    plan: RaceBetPlan,
    config: Optional[ExpectationTierConfig] = None,
) -> str:
    """X 用（A〜C・印中心・短文）。"""
    cfg = config or load_expectation_config()
    header = f"【{cfg.venue_label} {plan.race_no}R】　期待値{plan.expectation_tier}"
    body = format_marks_lines(plan.marks)
    return "\n".join([header, _x_intro_line(plan), *body])


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
        return "note用（根拠付き）"
    return "X用（簡易）"


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
