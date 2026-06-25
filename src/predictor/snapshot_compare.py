"""Compare T-10 snapshots vs final (result-page) odds impact on predictions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from src.predictor.bets import (
    DEFAULT_STRATEGY,
    RaceBetPlan,
    assign_marks,
    build_race_bet_plan,
    collect_race_signals,
    is_high_confidence,
)
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.scraper.race_snapshots import (
    DEFAULT_CAPTURE_OFFSETS,
    label_for_offset,
    snapshot_path,
    snapshots_dir,
)


@dataclass
class RaceTimingCompare:
    race_id: str
    race_no: int
    race_name: str
    snapshot_label: str
    captured_at: str
    fav_odds_live: float
    fav_odds_final: float
    odds_std_live: float
    odds_std_final: float
    upset_live: int
    upset_final: int
    win_profile_live: str
    win_profile_final: str
    exotic_profile_live: str
    exotic_profile_final: str
    confidence_live: str
    confidence_final: str
    exotic_confidence_live: str
    exotic_confidence_final: str
    mark_live: str
    mark_final: str
    umaban_live: str
    umaban_final: str
    win_prob_live: float
    win_prob_final: float
    winner_umaban: str
    winner_in_live_top3: bool
    winner_in_final_top3: bool
    profile_match: bool
    exotic_profile_match: bool
    mark_match: bool
    confidence_match: bool
    exotic_confidence_match: bool


def _odds_std(scored: pd.DataFrame) -> float:
    odds = pd.to_numeric(scored.get("odds", pd.Series(dtype=float)), errors="coerce").dropna()
    return float(odds.std()) if len(odds) >= 2 else 0.0


def _fav_odds(scored: pd.DataFrame) -> float:
    odds = pd.to_numeric(scored.get("odds", pd.Series(dtype=float)), errors="coerce")
    if odds.notna().any():
        return float(odds.min())
    return 99.0


def _load_snapshot_entries(
    date_yyyymmdd: str,
    race_id: str,
    label: str,
) -> Optional[dict]:
    path = snapshot_path(date_yyyymmdd, race_id, label)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_snapshot_race_ids(
    date_yyyymmdd: str,
    *,
    label: str = "t_minus_10",
) -> List[str]:
    day_dir = snapshots_dir(date_yyyymmdd)
    if not day_dir.exists():
        return []
    suffix = f"_{label}.json"
    return sorted(p.name[: -len(suffix)] for p in day_dir.glob(f"*{suffix}"))


def _winner_umaban(final_race: pd.DataFrame) -> str:
    if "finish" not in final_race.columns:
        return ""
    fn = pd.to_numeric(final_race["finish"], errors="coerce")
    winners = final_race.loc[fn == 1, "umaban"]
    if winners.empty:
        return ""
    return str(winners.iloc[0])


def _top_mark(scored: pd.DataFrame) -> tuple[str, str]:
    top = assign_marks(scored)
    if top.empty:
        return "", ""
    row = top.iloc[0]
    return str(row.get("mark", "")), str(row.get("umaban", ""))


def _winner_in_top3(scored: pd.DataFrame, winner: str) -> bool:
    if not winner:
        return False
    top3 = scored.sort_values("rank_pred").head(3)["umaban"].astype(str).tolist()
    return winner in top3


def compare_race(
    date_yyyymmdd: str,
    race_id: str,
    master: pd.DataFrame,
    *,
    label: str = "t_minus_10",
    win_cfg=None,
    ex_cfg=None,
) -> Optional[RaceTimingCompare]:
    snap = _load_snapshot_entries(date_yyyymmdd, race_id, label)
    if snap is None:
        return None

    final_race = master[master["race_id"].astype(str) == race_id].copy()
    if final_race.empty:
        return None

    live_entries = pd.DataFrame(snap.get("entries", []))
    if live_entries.empty:
        return None

    win_cfg = win_cfg if win_cfg is not None else load_split_scoring_configs()[0]
    ex_cfg = ex_cfg if ex_cfg is not None else load_split_scoring_configs()[1]

    hist_master = master[master["date"].astype(str) < date_yyyymmdd]
    scored_live_win = score_entries(live_entries, hist_master, config=win_cfg)
    scored_live_ex = score_entries(live_entries, hist_master, config=ex_cfg)
    scored_final_win = score_entries(final_race, hist_master, config=win_cfg)
    scored_final_ex = score_entries(final_race, hist_master, config=ex_cfg)

    plan_live = build_race_bet_plan(
        scored_live_win,
        exotic_race=scored_live_ex,
        strategy=DEFAULT_STRATEGY,
        master=hist_master,
        before_date=date_yyyymmdd,
    )
    plan_final = build_race_bet_plan(
        scored_final_win,
        exotic_race=scored_final_ex,
        strategy=DEFAULT_STRATEGY,
        master=hist_master,
        before_date=date_yyyymmdd,
    )

    sig_live = collect_race_signals(
        scored_live_ex,
        *is_high_confidence(scored_live_ex, DEFAULT_STRATEGY.win)[1:],
    )
    sig_final = collect_race_signals(
        scored_final_ex,
        *is_high_confidence(scored_final_ex, DEFAULT_STRATEGY.win)[1:],
    )

    mark_live, uma_live = _top_mark(scored_live_ex)
    mark_final, uma_final = _top_mark(scored_final_ex)
    winner = _winner_umaban(final_race)

    return RaceTimingCompare(
        race_id=race_id,
        race_no=int(final_race["race_no"].iloc[0]),
        race_name=str(final_race.get("race_name", pd.Series([""])).iloc[0]),
        snapshot_label=label,
        captured_at=str(snap.get("captured_at", "")),
        fav_odds_live=_fav_odds(scored_live_ex),
        fav_odds_final=_fav_odds(scored_final_ex),
        odds_std_live=_odds_std(scored_live_ex),
        odds_std_final=_odds_std(scored_final_ex),
        upset_live=sig_live.upset_score,
        upset_final=sig_final.upset_score,
        win_profile_live=plan_live.win_profile,
        win_profile_final=plan_final.win_profile,
        exotic_profile_live=plan_live.exotic_profile,
        exotic_profile_final=plan_final.exotic_profile,
        confidence_live=plan_live.confidence,
        confidence_final=plan_final.confidence,
        exotic_confidence_live=plan_live.exotic_confidence,
        exotic_confidence_final=plan_final.exotic_confidence,
        mark_live=mark_live,
        mark_final=mark_final,
        umaban_live=uma_live,
        umaban_final=uma_final,
        win_prob_live=float(scored_live_win.sort_values("rank_pred").iloc[0]["win_prob"]),
        win_prob_final=float(scored_final_win.sort_values("rank_pred").iloc[0]["win_prob"]),
        winner_umaban=winner,
        winner_in_live_top3=_winner_in_top3(scored_live_ex, winner),
        winner_in_final_top3=_winner_in_top3(scored_final_ex, winner),
        profile_match=plan_live.win_profile == plan_final.win_profile,
        exotic_profile_match=plan_live.exotic_profile == plan_final.exotic_profile,
        mark_match=uma_live == uma_final,
        confidence_match=plan_live.confidence == plan_final.confidence,
        exotic_confidence_match=plan_live.exotic_confidence == plan_final.exotic_confidence,
    )


def compare_day(
    date_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    label: str = "t_minus_10",
) -> List[RaceTimingCompare]:
    master = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    rows: List[RaceTimingCompare] = []
    for rid in list_snapshot_race_ids(date_yyyymmdd, label=label):
        row = compare_race(
            date_yyyymmdd,
            rid,
            master,
            label=label,
            win_cfg=win_cfg,
            ex_cfg=ex_cfg,
        )
        if row is not None:
            rows.append(row)
    return sorted(rows, key=lambda r: r.race_no)


def compare_day_all_labels(
    date_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    labels: Optional[Sequence[str]] = None,
) -> Dict[str, List[RaceTimingCompare]]:
    if labels is None:
        labels = [label_for_offset(m) for m in DEFAULT_CAPTURE_OFFSETS]
    return {
        label: compare_day(date_yyyymmdd, master, label=label)
        for label in labels
    }


def format_compare_report(
    rows: List[RaceTimingCompare],
    *,
    label: str = "t_minus_10",
) -> str:
    if not rows:
        return f"No comparable races for {label}."

    lines: List[str] = []
    n = len(rows)
    lines.append(f"=== {label} vs Final ({n} races) ===")
    lines.append("")

    for r in rows:
        lines.append(
            f"R{r.race_no:>2} {r.race_name}  captured={r.captured_at[-8:] if r.captured_at else '?'}"
        )
        lines.append(
            f"  odds: fav {r.fav_odds_live:.1f}->{r.fav_odds_final:.1f}  "
            f"std {r.odds_std_live:.0f}->{r.odds_std_final:.0f}  "
            f"upset {r.upset_live}->{r.upset_final}"
        )
        lines.append(
            f"  profile: win {r.win_profile_live}->{r.win_profile_final}  "
            f"exotic {r.exotic_profile_live}->{r.exotic_profile_final}"
        )
        lines.append(
            f"  conf: win [{r.confidence_live}] -> [{r.confidence_final}]  "
            f"exotic [{r.exotic_confidence_live}] -> [{r.exotic_confidence_final}]"
        )
        lines.append(
            f"  mark: {r.mark_live}{r.umaban_live} -> {r.mark_final}{r.umaban_final}  "
            f"win_prob {r.win_prob_live:.1%}->{r.win_prob_final:.1%}"
        )
        if r.winner_umaban:
            lines.append(
                f"  result: winner={r.winner_umaban}  "
                f"top3 live={r.winner_in_live_top3} final={r.winner_in_final_top3}"
            )
        flags = []
        if not r.profile_match:
            flags.append("win_prof")
        if not r.exotic_profile_match:
            flags.append("ex_prof")
        if not r.mark_match:
            flags.append("mark")
        if not r.confidence_match:
            flags.append("conf")
        if not r.exotic_confidence_match:
            flags.append("ex_conf")
        if flags:
            lines.append(f"  CHANGED: {', '.join(flags)}")
        lines.append("")

    def _rate(attr: str) -> float:
        return sum(1 for r in rows if getattr(r, attr)) / n

    lines.append("--- Summary ---")
    lines.append(f"win profile match:     {_rate('profile_match'):.0%} ({sum(r.profile_match for r in rows)}/{n})")
    lines.append(f"exotic profile match:  {_rate('exotic_profile_match'):.0%} ({sum(r.exotic_profile_match for r in rows)}/{n})")
    lines.append(f"◎ umaban match:        {_rate('mark_match'):.0%} ({sum(r.mark_match for r in rows)}/{n})")
    lines.append(f"win confidence match:  {_rate('confidence_match'):.0%} ({sum(r.confidence_match for r in rows)}/{n})")
    lines.append(f"exotic conf match:     {_rate('exotic_confidence_match'):.0%} ({sum(r.exotic_confidence_match for r in rows)}/{n})")
    winners = [r for r in rows if r.winner_umaban]
    if winners:
        lines.append(
            f"winner in top3 (live):  {sum(r.winner_in_live_top3 for r in winners)}/{len(winners)}"
        )
        lines.append(
            f"winner in top3 (final): {sum(r.winner_in_final_top3 for r in winners)}/{len(winners)}"
        )
    avg_fav_delta = sum(abs(r.fav_odds_live - r.fav_odds_final) for r in rows) / n
    avg_std_delta = sum(abs(r.odds_std_live - r.odds_std_final) for r in rows) / n
    lines.append(f"avg |fav_odds delta|: {avg_fav_delta:.2f}")
    lines.append(f"avg |odds_std delta|: {avg_std_delta:.1f}")
    return "\n".join(lines)


def _label_display(label: str) -> str:
    if label == "t_minus_10":
        return "T-10"
    if label.startswith("t_minus_"):
        return "T-" + label.replace("t_minus_", "")
    return label


def format_compare_summary_ja(
    rows: List[RaceTimingCompare],
    *,
    date_yyyymmdd: str,
    label: str = "t_minus_10",
) -> str:
    """LINE\u7528\u306e\u65e5\u672c\u8a9e\u30b5\u30de\u30ea\u30fc\uff08\u958b\u50ac\u65e5\u306e\u7ba1\u7406\u8005\u5411\u3051\uff09\u3002"""
    if not rows:
        return ""

    n = len(rows)
    timing = _label_display(label)

    def _count(attr: str) -> int:
        return sum(1 for r in rows if getattr(r, attr))

    winners = [r for r in rows if r.winner_umaban]
    avg_fav_delta = sum(abs(r.fav_odds_live - r.fav_odds_final) for r in rows) / n

    lines = [
        f"\u3010\u30aa\u30c3\u30ba\u5909\u52d5\u30c1\u30a7\u30c3\u30af {date_yyyymmdd}\u3011",
        f"{timing}\u6642\u70b9\u306e\u30aa\u30c3\u30ba vs \u78ba\u5b9a\u30aa\u30c3\u30ba\uff08{n}R\uff09",
        "\u203b\u4e88\u60f3\u306e\u5f71\u97ff\u30c1\u30a7\u30c3\u30af\uff08\u6210\u7e3e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\uff09",
        "",
        f"\u5358\u52dd\u30d7\u30ed\u30d5\u30a3\u30fc\u30eb\u4e00\u81f4: {_count('profile_match')}/{n}",
        f"\u4e09\u9023\u30d7\u30ed\u30d5\u30a3\u30fc\u30eb\u4e00\u81f4: {_count('exotic_profile_match')}/{n}",
        f"\u25ce\u99ac\u756a\u4e00\u81f4: {_count('mark_match')}/{n}",
        f"\u5358\u52dd\u81ea\u4fe1\u5ea6\u4e00\u81f4: {_count('confidence_match')}/{n}",
        f"\u4e09\u9023\u81ea\u4fe1\u5ea6\u4e00\u81f4: {_count('exotic_confidence_match')}/{n}",
    ]
    if winners:
        lines.extend(
            [
                "",
                f"1\u7740\u304c\u4e0a\u4f4d3\u982d\u5185\uff08{timing}\uff09: "
                f"{sum(r.winner_in_live_top3 for r in winners)}/{len(winners)}",
                f"1\u7740\u304c\u4e0a\u4f4d3\u982d\u5185\uff08\u78ba\u5b9a\u5f8c\uff09: "
                f"{sum(r.winner_in_final_top3 for r in winners)}/{len(winners)}",
            ]
        )
    lines.extend(
        [
            "",
            f"1\u756a\u4eba\u6c17\u30aa\u30c3\u30ba\u306e\u5e73\u5747\u5909\u52d5: {avg_fav_delta:.2f}",
        ]
    )
    return "\n".join(lines)
