"""自信度が高いレース向けの馬券フォーメーション生成。"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from math import comb
from typing import List, Optional, Tuple

import pandas as pd

from src.features.utils import parse_distance_m


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

# 三連系（堅いレース）: 1-2位差をやや緩め（Q1 2026 チューニング）
DEFAULT_EXOTIC_FIRM_THRESHOLDS = ConfidenceThresholds(
    win_prob=0.85,
    win_prob_alt=0.75,
    prob_gap=0.70,
    mode="and",
)

# 三連系（荒れレース）: 勝率を厳しめ・gap 緩め（Q1 2026 チューニング）
DEFAULT_EXOTIC_UPSET_THRESHOLDS = ConfidenceThresholds(
    win_prob=0.82,
    win_prob_alt=0.75,
    prob_gap=0.50,
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
    upset_box_core: int = 4
    upset_longshot_count: int = 2
    skip_win_on_upset: bool = True
    skip_place_on_upset: bool = True
    # 単勝用プロファイル（厳しめ: 見送り判定）
    win_fav_odds_skip: float = 3.0
    win_upset_score_min: int = 4
    win_prob_gap_max: float = 0.65
    win_fav_soft: float = 2.5
    # 三連系用プロファイル（広め: BOX切替）
    exotic_head_min: int = 12
    exotic_odds_std_min: float = 88.0
    exotic_upset_classes: tuple = ("C1", "C2", "C3", "B2")
    exotic_class_score_min: int = 2
    exotic_dist_min_m: float = 1700.0
    exotic_dist_score_min: int = 2
    exotic_firm: ConfidenceThresholds = DEFAULT_EXOTIC_FIRM_THRESHOLDS
    exotic_upset: ConfidenceThresholds = DEFAULT_EXOTIC_UPSET_THRESHOLDS
    win: ConfidenceThresholds = DEFAULT_WIN_THRESHOLDS
    split_scoring: bool = True


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
    win_profile: str = "堅"
    exotic_profile: str = "堅"
    race_profile: str = "堅"  # exotic_profile のエイリアス（後方互換）
    exotic_confidence: str = "通常"
    fav_odds: float = 0.0
    sanrenpuku: Optional[SanrenpukuNagashi] = None
    sanrenpuku_box: Optional[SanrenpukuBox] = None
    sanrentan: Optional[SanrentanFormation] = None
    wide: Optional[WideFormation] = None
    expectation_score: int = 0
    expectation_tier: str = "C"


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


def _odds_series(scored_race: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(scored_race.get("odds", pd.Series(dtype=float)), errors="coerce")


def compute_upset_score(
    fav_odds: float,
    prob_gap: float,
    head_count: int,
    win_prob_top: float,
    *,
    odds_std: float = 0.0,
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
    # オッズのばらつき（園田では std 80+ が荒れ寄り）
    if odds_std >= 88.0:
        score += 1
    return score


def _race_class(scored_race: pd.DataFrame) -> str:
    if "race_class" in scored_race.columns:
        val = str(scored_race["race_class"].iloc[0]).strip()
        if val and val.lower() != "nan":
            return val
    return ""


@dataclass(frozen=True)
class RaceSignals:
    """堅/荒判定に使うレース指標。"""

    fav_odds: float
    head_count: int
    odds_std: float
    prob_gap: float
    win_prob_top: float
    upset_score: int
    race_class: str
    distance_m: float


def _race_distance_m(scored_race: pd.DataFrame) -> float:
    if "distance" not in scored_race.columns:
        return float("nan")
    val = parse_distance_m(scored_race["distance"].iloc[0])
    return float(val) if val == val else float("nan")


def _is_lower_class(race_class: str, classes: tuple) -> bool:
    cls = race_class.upper()
    return bool(cls) and any(cls.startswith(c) for c in classes)


def _class_upset_signal(signals: RaceSignals, strategy: BetStrategyConfig) -> bool:
    return (
        _is_lower_class(signals.race_class, strategy.exotic_upset_classes)
        and signals.upset_score >= strategy.exotic_class_score_min
    )


def _distance_upset_signal(signals: RaceSignals, strategy: BetStrategyConfig) -> bool:
    if signals.distance_m != signals.distance_m:  # NaN
        return False
    return (
        signals.distance_m >= strategy.exotic_dist_min_m
        and signals.upset_score >= strategy.exotic_dist_score_min
    )


def collect_race_signals(
    scored_race: pd.DataFrame,
    win_prob_top: float,
    prob_gap: float,
) -> RaceSignals:
    fav = _fav_odds(scored_race)
    head = _head_count(scored_race)
    odds = _odds_series(scored_race).dropna()
    odds_std = float(odds.std()) if len(odds) >= 2 else 0.0
    score = compute_upset_score(
        fav, prob_gap, head, win_prob_top, odds_std=odds_std,
    )
    return RaceSignals(
        fav_odds=fav,
        head_count=head,
        odds_std=odds_std,
        prob_gap=prob_gap,
        win_prob_top=win_prob_top,
        upset_score=score,
        race_class=_race_class(scored_race),
        distance_m=_race_distance_m(scored_race),
    )


def detect_win_profile(
    signals: RaceSignals,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> str:
    """単勝向け堅/荒。荒=単勝見送り候補（厳しめ判定）。"""
    if signals.fav_odds >= strategy.win_fav_odds_skip:
        return "荒"
    if (
        signals.upset_score >= strategy.win_upset_score_min
        and signals.fav_odds >= strategy.win_fav_soft
        and signals.prob_gap <= strategy.win_prob_gap_max
    ):
        return "荒"
    if _class_upset_signal(signals, strategy):
        return "荒"
    if _distance_upset_signal(signals, strategy):
        return "荒"
    return "堅"


def detect_exotic_profile(
    signals: RaceSignals,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> str:
    """三連系向け堅/荒。荒=BOX・三連単見送り（流し↔BOXの切替）。"""
    if signals.fav_odds >= strategy.fav_odds_upset:
        return "荒"
    if signals.upset_score >= 4:
        return "荒"
    if (
        signals.upset_score >= strategy.upset_score_min
        and signals.fav_odds >= strategy.win_fav_soft
        and signals.prob_gap <= 0.70
    ):
        return "荒"
    if _class_upset_signal(signals, strategy):
        return "荒"
    if _distance_upset_signal(signals, strategy):
        return "荒"
    return "堅"


def is_volatile_race(
    signals: RaceSignals,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> bool:
    """三連系のワイド拡張・穴馬選定用（BOX切替とは別）。"""
    if signals.head_count >= strategy.exotic_head_min:
        return True
    if signals.odds_std >= strategy.exotic_odds_std_min:
        return True
    cls = signals.race_class.upper()
    if (
        cls
        and any(cls.startswith(c) for c in strategy.exotic_upset_classes)
        and signals.upset_score >= strategy.exotic_class_score_min
    ):
        return True
    return False


def detect_race_profile(
    scored_race: pd.DataFrame,
    win_prob_top: float,
    prob_gap: float,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> Tuple[str, float, int]:
    """後方互換: exotic_profile と同義。"""
    sig = collect_race_signals(scored_race, win_prob_top, prob_gap)
    return detect_exotic_profile(sig, strategy), sig.fav_odds, sig.upset_score


def _pick_exotic_longshots(
    scored_race: pd.DataFrame,
    core_umaban: set[str],
    count: int,
) -> pd.DataFrame:
    """三連複BOX用の穴馬。オッズ穴とモデル中位を混在させる。"""
    if count <= 0:
        return scored_race.iloc[0:0]

    rest = scored_race[
        ~scored_race["umaban"].astype(str).isin(core_umaban)
    ].copy()
    if rest.empty:
        return rest.iloc[0:0]

    rest["odds_n"] = pd.to_numeric(rest.get("odds", pd.Series(dtype=float)), errors="coerce")
    rest["rank_n"] = pd.to_numeric(rest.get("rank_pred", pd.Series(dtype=float)), errors="coerce")

    by_odds = rest.nlargest(max(1, (count + 1) // 2), "odds_n")
    remaining = rest[~rest.index.isin(by_odds.index)]
    model_pool = remaining.nsmallest(count, "rank_n") if not remaining.empty else remaining
    picked = pd.concat([by_odds, model_pool], ignore_index=False).drop_duplicates(
        subset=["umaban"]
    )
    return picked.head(count)


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
    core_count: int = 5,
    extra_longshots: int = 0,
) -> Optional[SanrenpukuBox]:
    """予想上位 core_count 頭＋任意で穴馬を足した三連複BOX。"""
    if len(top5) < 3:
        return None

    core_n = max(3, min(core_count, len(top5)))
    horses = top5.iloc[:core_n].copy()
    selected_u = {str(u) for u in horses["umaban"]}
    if extra_longshots > 0:
        longs = _pick_exotic_longshots(scored_race, selected_u, extra_longshots)
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
    exotic_race: Optional[pd.DataFrame] = None,
) -> RaceBetPlan:
    """1レース分の印・馬券案を生成（exotic_race で三連系スコアを分離可能）。"""
    st = strategy or DEFAULT_STRATEGY
    win_th = thresholds or st.win
    ex_race = exotic_race if exotic_race is not None else scored_race

    race_id = str(scored_race["race_id"].iloc[0])
    race_no = int(scored_race["race_no"].iloc[0])
    race_name = str(scored_race.get("race_name", pd.Series([""])).iloc[0])

    top5 = assign_marks(ex_race)
    marks = [
        (str(row["mark"]), str(row["umaban"]), str(row["horse_name"]))
        for _, row in top5.iterrows()
    ]

    win_high, p1, gap = is_high_confidence(scored_race, win_th)
    _, ex_p1, ex_gap = is_high_confidence(ex_race, win_th)
    signals_win = collect_race_signals(scored_race, p1, gap)
    signals_ex = collect_race_signals(ex_race, ex_p1, ex_gap)
    win_profile = detect_win_profile(signals_win, st)
    exotic_profile = detect_exotic_profile(signals_ex, st)
    exotic_th = st.exotic_upset if exotic_profile == "荒" else st.exotic_firm
    exotic_high = matches_threshold(ex_p1, ex_gap, exotic_th)

    plan = RaceBetPlan(
        race_id=race_id,
        race_no=race_no,
        race_name=race_name,
        confidence="高" if win_high else "通常",
        exotic_confidence="高" if exotic_high else "通常",
        win_profile=win_profile,
        exotic_profile=exotic_profile,
        race_profile=exotic_profile,
        fav_odds=signals_win.fav_odds,
        win_prob_top=p1,
        prob_gap=gap,
        marks=marks,
    )

    if win_profile == "荒" and st.skip_win_on_upset and win_high:
        plan.confidence = "通常（荒れ・単勝見送り）"

    if not exotic_high:
        return _finalize_plan(plan)

    if exotic_profile == "堅":
        plan.sanrenpuku = build_sanrenpuku_nagashi(top5)
        plan.sanrentan = build_sanrentan_formation(top5)
        plan.wide = (
            build_wide_formation_upset(top5)
            if is_volatile_race(signals_ex, st)
            else build_wide_formation(top5)
        )
    else:
        plan.sanrenpuku_box = build_sanrenpuku_box(
            top5,
            ex_race,
            core_count=st.upset_box_core,
            extra_longshots=st.upset_longshot_count,
        )
        plan.wide = build_wide_formation_upset(top5)

    return _finalize_plan(plan)


def _finalize_plan(plan: RaceBetPlan) -> RaceBetPlan:
    from src.predictor.expectation import apply_expectation_to_plan

    return apply_expectation_to_plan(plan)


def build_day_bet_plans(
    scored: pd.DataFrame,
    thresholds: Optional[ConfidenceThresholds] = None,
    strategy: Optional[BetStrategyConfig] = None,
    exotic_scored: Optional[pd.DataFrame] = None,
) -> List[RaceBetPlan]:
    """日付全体のレースごと馬券案。"""
    if scored.empty:
        return []
    st = strategy or DEFAULT_STRATEGY
    ex_by_race: dict = {}
    if st.split_scoring and exotic_scored is not None:
        ex_by_race = {
            str(rid): grp
            for rid, grp in exotic_scored.groupby("race_id", sort=False)
        }
    plans: List[RaceBetPlan] = []
    for _, group in scored.groupby("race_id", sort=False):
        rid = str(group["race_id"].iloc[0])
        ex_group = ex_by_race.get(rid) if ex_by_race else None
        plans.append(build_race_bet_plan(group, thresholds, st, exotic_race=ex_group))
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
