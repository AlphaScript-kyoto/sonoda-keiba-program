"""自信度が高いレース向けの馬券フォーメーション生成。"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from math import comb
from typing import List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class ConfidenceThresholds:
    """自信度「高」の判定閾値。"""

    win_prob: float = 0.85
    win_prob_alt: float = 0.75
    prob_gap: float = 0.60
    mode: str = "and"  # "or": どちらか / "and": 両方 / "strict": 厳格OR

    def label(self) -> str:
        ge = ">="
        if self.mode == "and":
            return f"勝率{ge}{self.win_prob:.0%} かつ 差{ge}{self.prob_gap:.0%}"
        if self.mode == "strict":
            return (
                f"勝率{ge}{self.win_prob:.0%} かつ 差{ge}{self.prob_gap:.0%} "
                f"（または 勝率{ge}{self.win_prob_alt:.0%} かつ "
                f"差{ge}{self.prob_gap + 0.10:.0%}）"
            )
        return (
            f"勝率{ge}{self.win_prob:.0%} "
            f"または (勝率{ge}{self.win_prob_alt:.0%} かつ 差{ge}{self.prob_gap:.0%})"
        )


DEFAULT_WIN_THRESHOLDS = ConfidenceThresholds(
    win_prob=0.85,
    win_prob_alt=0.75,
    prob_gap=0.60,
    mode="and",
)

# 三連系（堅いレース）: 1-2位差を厳しめ
DEFAULT_EXOTIC_FIRM_THRESHOLDS = ConfidenceThresholds(
    win_prob=0.85,
    win_prob_alt=0.75,
    prob_gap=0.75,
    mode="and",
)

# 三連系（荒れレース）: BOX買い用にやや緩め
DEFAULT_EXOTIC_UPSET_THRESHOLDS = ConfidenceThresholds(
    win_prob=0.80,
    win_prob_alt=0.75,
    prob_gap=0.55,
    mode="and",
)

# 後方互換
DEFAULT_THRESHOLDS = DEFAULT_WIN_THRESHOLDS

MARKS = ("◎", "○", "▲", "△", "☆")


@dataclass(frozen=True)
class BetStrategyConfig:
    """レースタイプ別の馬券戦略設定。"""

    fav_odds_upset: float = 3.0
    upset_score_min: int = 3
    upset_longshot_count: int = 2
    exotic_firm: ConfidenceThresholds = DEFAULT_EXOTIC_FIRM_THRESHOLDS
    exotic_upset: ConfidenceThresholds = DEFAULT_EXOTIC_UPSET_THRESHOLDS
    win: ConfidenceThresholds = DEFAULT_WIN_THRESHOLDS


DEFAULT_STRATEGY = BetStrategyConfig()


@dataclass
class SanrenpukuNagashi:
    """三連複1軸流し。"""

    axis_umaban: str
    axis_name: str
    partner_umaban: List[str]
    partner_names: List[str]
    points: int
    label: str = field(default="", init=False)

    def __post_init__(self) -> None:
        partner_txt = ",".join(self.partner_umaban)
        self.label = (
            f"三連複1軸流し: 軸{self.axis_umaban} {self.axis_name} "
            f"× 相手 {partner_txt} ({self.points}点)"
        )


@dataclass
class SanrenpukuBox:
    """三連複BOX（軸なし）。"""

    umaban: List[str]
    names: List[str]
    points: int
    label: str = field(default="", init=False)

    def __post_init__(self) -> None:
        nums = ",".join(self.umaban)
        self.label = f"三連複BOX: [{nums}] ({self.points}点)"


@dataclass
class SanrentanFormation:
    """三連単フォーメーション。"""

    first_umaban: List[str]
    second_umaban: List[str]
    third_umaban: List[str]
    tickets: List[Tuple[str, str, str]]
    points: int
    label: str = field(default="", init=False)

    def __post_init__(self) -> None:
        f = ",".join(self.first_umaban)
        s = ",".join(self.second_umaban)
        t = ",".join(self.third_umaban)
        self.label = f"三連単: 1着[{f}] → 2着[{s}] → 3着[{t}] ({self.points}点)"


@dataclass
class WideFormation:
    """ワイド: ◎-○▲（1位×2-3位）。"""

    pairs: List[Tuple[str, str]]
    points: int
    label: str = field(default="", init=False)

    def __post_init__(self) -> None:
        parts = [f"{a}-{b}" for a, b in self.pairs]
        self.label = f"ワイド: {', '.join(parts)} ({self.points}点)"


@dataclass
class RaceBetPlan:
    race_id: str
    race_no: int
    race_name: str
    confidence: str
    win_prob_top: float
    prob_gap: float
    marks: List[Tuple[str, str, str]]
    race_profile: str = "堅"
    exotic_confidence: str = "通常"
    fav_odds: float = 0.0
    sanrenpuku: Optional[SanrenpukuNagashi] = None
    sanrenpuku_box: Optional[SanrenpukuBox] = None
    sanrentan: Optional[SanrentanFormation] = None
    wide: Optional[WideFormation] = None


def _horse_label(row: pd.Series) -> Tuple[str, str]:
    return str(row["umaban"]), str(row.get("horse_name", ""))


def assign_marks(scored_race: pd.DataFrame) -> pd.DataFrame:
    """上位5頭に印（◎～☆）を付与。"""
    out = scored_race.sort_values("rank_pred").head(5).copy()
    out["mark"] = [MARKS[i] if i < len(MARKS) else "" for i in range(len(out))]
    return out


def is_high_confidence(
    scored_race: pd.DataFrame,
    thresholds: Optional[ConfidenceThresholds] = None,
) -> Tuple[bool, float, float]:
    """自信度判定と1位勝率・1-2位差。"""
    th = thresholds or DEFAULT_THRESHOLDS
    top = scored_race.sort_values("rank_pred")
    if len(top) < 3:
        return False, 0.0, 0.0

    p1 = float(top.iloc[0]["win_prob"])
    p2 = float(top.iloc[1]["win_prob"])
    gap = p1 - p2

    alt_gap = th.prob_gap + 0.10
    if th.mode == "and":
        high = p1 >= th.win_prob and gap >= th.prob_gap
    elif th.mode == "strict":
        high = (p1 >= th.win_prob and gap >= th.prob_gap) or (
            p1 >= th.win_prob_alt and gap >= alt_gap
        )
    else:
        high = p1 >= th.win_prob or (
            p1 >= th.win_prob_alt and gap >= th.prob_gap
        )
    return high, p1, gap


def matches_threshold(
    win_prob_top: float, prob_gap: float, thresholds: ConfidenceThresholds
) -> bool:
    """閾値設定で自信度「高」か判定。"""
    th = thresholds
    alt_gap = th.prob_gap + 0.10
    if th.mode == "and":
        return win_prob_top >= th.win_prob and prob_gap >= th.prob_gap
    if th.mode == "strict":
        return (win_prob_top >= th.win_prob and prob_gap >= th.prob_gap) or (
            win_prob_top >= th.win_prob_alt and prob_gap >= alt_gap
        )
    return win_prob_top >= th.win_prob or (
        win_prob_top >= th.win_prob_alt and prob_gap >= th.prob_gap
    )


def _fav_odds(scored_race: pd.DataFrame) -> float:
    odds = pd.to_numeric(scored_race.get("odds", pd.Series(dtype=float)), errors="coerce")
    if odds.notna().any():
        return float(odds.min())
    return 99.0


def _head_count(scored_race: pd.DataFrame) -> int:
    if "head_count" in scored_race.columns:
        val = pd.to_numeric(scored_race["head_count"].iloc[0], errors="coerce")
        if pd.notna(val):
            return int(val)
    return len(scored_race)


def compute_upset_score(
    fav_odds: float,
    prob_gap: float,
    head_count: int,
    win_prob_top: float,
) -> int:
    score = 0
    if fav_odds >= 3.0:
        score += 2
    if prob_gap <= 0.65:
        score += 1
    if head_count >= 12:
        score += 1
    if win_prob_top < 0.88:
        score += 1
    return score


def detect_race_profile(
    scored_race: pd.DataFrame,
    win_prob_top: float,
    prob_gap: float,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> Tuple[str, float, int]:
    """レースプロファイル（堅/荒）と1番人気オッズ・upset_scoreを返す。"""
    fav = _fav_odds(scored_race)
    head = _head_count(scored_race)
    score = compute_upset_score(fav, prob_gap, head, win_prob_top)
    if fav >= strategy.fav_odds_upset or score >= strategy.upset_score_min:
        return "荒", fav, score
    return "堅", fav, score


def build_sanrenpuku_nagashi(top5: pd.DataFrame) -> Optional[SanrenpukuNagashi]:
    """1位を軸、2～5位を相手とする三連複1軸流し。"""
    if len(top5) < 4:
        return None

    axis_u, axis_n = _horse_label(top5.iloc[0])
    partners = top5.iloc[1:5]
    partner_u = [str(u) for u in partners["umaban"]]
    partner_n = [str(n) for n in partners["horse_name"]]
    points = comb(len(partner_u), 2)

    return SanrenpukuNagashi(
        axis_umaban=axis_u,
        axis_name=axis_n,
        partner_umaban=partner_u,
        partner_names=partner_n,
        points=points,
    )


def build_sanrenpuku_box(
    top5: pd.DataFrame,
    scored_race: pd.DataFrame,
    *,
    extra_longshots: int = 0,
) -> Optional[SanrenpukuBox]:
    """予想上位＋任意で穴馬を足した三連複BOX。"""
    if len(top5) < 3:
        return None

    horses = top5.copy()
    selected_u = {str(u) for u in horses["umaban"]}
    if extra_longshots > 0:
        rest = scored_race[~scored_race["umaban"].astype(str).isin(selected_u)].copy()
        rest["odds_n"] = pd.to_numeric(rest.get("odds", pd.Series(dtype=float)), errors="coerce")
        longs = rest.nlargest(extra_longshots, "odds_n")
        if not longs.empty:
            horses = pd.concat([horses, longs], ignore_index=True)

    umaban = [str(u) for u in horses["umaban"]]
    if len(umaban) < 3:
        return None
    names = [str(n) for n in horses["horse_name"]]
    points = comb(len(umaban), 3)
    return SanrenpukuBox(umaban=umaban, names=names, points=points)


def build_sanrentan_formation(top5: pd.DataFrame) -> Optional[SanrentanFormation]:
    """
    三連単フォーメーション。
    1着=◎、2着=○▲、3着=△☆
    """
    if len(top5) < 5:
        return None

    first = [str(top5.iloc[0]["umaban"])]
    second = [str(u) for u in top5.iloc[1:3]["umaban"]]
    third = [str(u) for u in top5.iloc[3:5]["umaban"]]

    tickets: List[Tuple[str, str, str]] = []
    for a, b, c in product(first, second, third):
        if len({a, b, c}) == 3:
            tickets.append((a, b, c))

    if not tickets:
        return None

    return SanrentanFormation(
        first_umaban=first,
        second_umaban=second,
        third_umaban=third,
        tickets=tickets,
        points=len(tickets),
    )


def build_wide_formation(top5: pd.DataFrame) -> Optional[WideFormation]:
    """1位（◎）と2-3位（○▲）のワイド2点。"""
    if len(top5) < 3:
        return None
    axis = str(top5.iloc[0]["umaban"])
    partners = [str(u) for u in top5.iloc[1:3]["umaban"]]
    pairs = [(axis, p) for p in partners]
    return WideFormation(pairs=pairs, points=len(pairs))


def build_wide_formation_upset(top5: pd.DataFrame) -> Optional[WideFormation]:
    """荒れ想定: ◎-○▲△ のワイド3点。"""
    if len(top5) < 4:
        return build_wide_formation(top5)
    axis = str(top5.iloc[0]["umaban"])
    partners = [str(u) for u in top5.iloc[1:4]["umaban"]]
    pairs = [(axis, p) for p in partners]
    return WideFormation(pairs=pairs, points=len(pairs))


def build_race_bet_plan(
    scored_race: pd.DataFrame,
    thresholds: Optional[ConfidenceThresholds] = None,
    strategy: Optional[BetStrategyConfig] = None,
) -> RaceBetPlan:
    """1レース分の印・馬券案を生成。"""
    st = strategy or DEFAULT_STRATEGY
    win_th = thresholds or st.win

    race_id = str(scored_race["race_id"].iloc[0])
    race_no = int(scored_race["race_no"].iloc[0])
    race_name = str(scored_race.get("race_name", pd.Series([""])).iloc[0])

    top5 = assign_marks(scored_race)
    marks = [
        (str(row["mark"]), str(row["umaban"]), str(row["horse_name"]))
        for _, row in top5.iterrows()
    ]

    win_high, p1, gap = is_high_confidence(scored_race, win_th)
    profile, fav, _ = detect_race_profile(scored_race, p1, gap, st)
    exotic_th = st.exotic_upset if profile == "荒" else st.exotic_firm
    exotic_high = matches_threshold(p1, gap, exotic_th)

    plan = RaceBetPlan(
        race_id=race_id,
        race_no=race_no,
        race_name=race_name,
        confidence="高" if win_high else "通常",
        exotic_confidence="高" if exotic_high else "通常",
        race_profile=profile,
        fav_odds=fav,
        win_prob_top=p1,
        prob_gap=gap,
        marks=marks,
    )

    if not exotic_high:
        return plan

    if profile == "堅":
        plan.sanrenpuku = build_sanrenpuku_nagashi(top5)
        plan.sanrentan = build_sanrentan_formation(top5)
        plan.wide = build_wide_formation(top5)
    else:
        plan.sanrenpuku_box = build_sanrenpuku_box(
            top5,
            scored_race,
            extra_longshots=st.upset_longshot_count,
        )
        plan.wide = build_wide_formation_upset(top5)

    return plan


def build_day_bet_plans(
    scored: pd.DataFrame,
    thresholds: Optional[ConfidenceThresholds] = None,
    strategy: Optional[BetStrategyConfig] = None,
) -> List[RaceBetPlan]:
    """日付全体のレースごと馬券案。"""
    if scored.empty:
        return []
    plans: List[RaceBetPlan] = []
    for _, group in scored.groupby("race_id", sort=False):
        plans.append(build_race_bet_plan(group, thresholds, strategy))
    plans.sort(key=lambda p: p.race_no)
    return plans


def check_sanrenpuku_box_hit(box: SanrenpukuBox, finish_order: List[str]) -> bool:
    """三連複BOXが的中したか。"""
    if len(finish_order) < 3:
        return False
    return set(finish_order[:3]).issubset(set(box.umaban))


def check_sanrenpuku_hit(
    nagashi: SanrenpukuNagashi, finish_order: List[str]
) -> bool:
    """三連複1軸流しが的中したか（finish_order=1-3着馬番）。"""
    if len(finish_order) < 3:
        return False
    top3 = set(finish_order[:3])
    if nagashi.axis_umaban not in top3:
        return False
    others = top3 - {nagashi.axis_umaban}
    return others.issubset(set(nagashi.partner_umaban)) and len(others) == 2


def check_sanrentan_hit(
    formation: SanrentanFormation, finish_order: List[str]
) -> bool:
    """三連単フォーメーションが的中したか。"""
    if len(finish_order) < 3:
        return False
    key = (finish_order[0], finish_order[1], finish_order[2])
    return key in formation.tickets


def check_wide_hits(
    formation: WideFormation, finish_order: List[str]
) -> List[Tuple[str, str]]:
    """3着以内に両方入ったワイドペアを返す。"""
    if len(finish_order) < 3:
        return []
    top3 = set(finish_order[:3])
    hits: List[Tuple[str, str]] = []
    for a, b in formation.pairs:
        if a in top3 and b in top3:
            hits.append((a, b))
    return hits
