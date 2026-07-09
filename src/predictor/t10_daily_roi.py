"""T-10 snapshot ROI report for expectation tier S+ races (nightly team broadcast)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from src.predictor.backtest import (
    BET_UNIT,
    _finish_order,
    _load_paybacks_for_races,
)
from src.predictor.bets import (
    DEFAULT_STRATEGY,
    _race_class,
    assign_marks,
    build_race_bet_plan,
    build_sanrenpuku_formation_firm,
    check_sanrenpuku_formation_firm_hit,
    format_sanrenpuku_formation_umaban_line,
)
from src.predictor.expectation import TIER_RANK
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.scraper.payback import RacePayback, finish_top3_from_payback
from src.scraper.race_snapshots import LABEL_T_MINUS_10, snapshot_path

S_PLUS_BUY_LABEL = "\u4e09\u9023\u8907\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f35\u70b9"


def is_tier_s_plus(tier: str) -> bool:
    return TIER_RANK.get(tier, 99) <= TIER_RANK["S"]


def format_s_plus_buy_line_message(
    plan,
    top5: pd.DataFrame,
    *,
    header_line: Optional[str] = None,
) -> Optional[str]:
    """Team LINE buy text for S+ races (sanren formation only)."""
    if plan is None or not is_tier_s_plus(plan.expectation_tier):
        return None
    formation = build_sanrenpuku_formation_firm(top5)
    if formation is None or formation.points <= 0:
        return None

    buy_line = format_sanrenpuku_formation_umaban_line(formation)
    header = header_line or f"{int(plan.race_no)}R"
    return "\n".join(
        [
            header,
            "",
            f"\u3010\u8cb7\u3044\u76ee\u3011\u671f\u5f85\u5024{plan.expectation_tier}",
            S_PLUS_BUY_LABEL,
            buy_line,
            f"\uff08\u8a08{formation.points}\u70b9\u30fb{formation.points * BET_UNIT}\u5186\uff09",
        ]
    )


@dataclass(frozen=True)
class SPlusPaybackEvaluation:
    hit: bool
    return_yen: int
    finish: tuple[str, str, str]
    buy_line: str


def evaluate_s_plus_payback_for_race(
    date_yyyymmdd: str,
    race_id: str,
    payback: Optional[RacePayback],
    master: Optional[pd.DataFrame] = None,
) -> Optional[SPlusPaybackEvaluation]:
    """T-10買い目（三連複5点フォーメーション）が的中したかを判定する。"""
    master_df = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    scored = _score_t10_race(
        date_yyyymmdd,
        race_id,
        master_df,
        win_cfg=win_cfg,
        ex_cfg=ex_cfg,
        require_result=False,
    )
    if scored is None:
        return None

    _plan, top5, final_race, _snap = scored
    if top5.empty:
        return None

    finish = _finish_order(final_race) if not final_race.empty else []
    if len(finish) < 3:
        pb_finish = finish_top3_from_payback(payback)
        if pb_finish is None:
            return None
        finish = list(pb_finish)

    formation = build_sanrenpuku_formation_firm(top5)
    if formation is None or formation.points <= 0:
        return None

    hit = check_sanrenpuku_formation_firm_hit(formation, finish)
    return_yen = payback.fuku3_yen if hit and payback else 0
    return SPlusPaybackEvaluation(
        hit=hit,
        return_yen=return_yen,
        finish=(finish[0], finish[1], finish[2]),
        buy_line=format_sanrenpuku_formation_umaban_line(formation),
    )


@dataclass
class T10RaceRoi:
    race_id: str
    race_no: int
    race_name: str
    race_class: str
    expectation_tier: str
    expectation_score: int
    sanren_points: int = 0
    investment: int = 0
    return_yen: int = 0
    sanren_hit: bool = False
    sanren_display: str = ""

    @property
    def roi_pct(self) -> float:
        return (self.return_yen / self.investment * 100.0) if self.investment else 0.0


@dataclass
class T10DailyRoiReport:
    date: str
    races: List[T10RaceRoi] = field(default_factory=list)
    skipped_no_result: int = 0
    skipped_not_s_plus: int = 0

    @property
    def total_investment(self) -> int:
        return sum(r.investment for r in self.races)

    @property
    def total_return(self) -> int:
        return sum(r.return_yen for r in self.races)

    @property
    def total_roi_pct(self) -> float:
        inv = self.total_investment
        return (self.total_return / inv * 100.0) if inv else 0.0

    @property
    def total_points(self) -> int:
        return sum(r.sanren_points for r in self.races)

    @property
    def sanren_hit_count(self) -> int:
        return sum(1 for r in self.races if r.sanren_hit)

    @property
    def race_hit_count(self) -> int:
        return self.sanren_hit_count


def _load_snapshot_entries(date_yyyymmdd: str, race_id: str) -> Optional[dict]:
    path = snapshot_path(date_yyyymmdd, race_id, LABEL_T_MINUS_10)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _score_t10_race(
    date_yyyymmdd: str,
    race_id: str,
    master: pd.DataFrame,
    *,
    win_cfg,
    ex_cfg,
    require_result: bool = True,
):
    snap = _load_snapshot_entries(date_yyyymmdd, race_id)
    if snap is None:
        return None

    final_race = master[master["race_id"].astype(str) == race_id].copy()
    if require_result and final_race.empty:
        # 開催中は結果が master 未反映。着順は呼び出し側で払戻から取得する。
        return None

    live_entries = pd.DataFrame(snap.get("entries", []))
    if live_entries.empty:
        return None

    hist_master = master[master["date"].astype(str) < date_yyyymmdd]
    scored_live_win = score_entries(live_entries, hist_master, config=win_cfg)
    scored_live_ex = score_entries(live_entries, hist_master, config=ex_cfg)
    plan = build_race_bet_plan(
        scored_live_win,
        exotic_race=scored_live_ex,
        strategy=DEFAULT_STRATEGY,
        master=hist_master,
        before_date=date_yyyymmdd,
    )
    top5 = assign_marks(scored_live_ex)
    return plan, top5, final_race, snap


def compute_t10_race_roi(
    date_yyyymmdd: str,
    race_id: str,
    master: pd.DataFrame,
    payback: Optional[RacePayback],
    *,
    win_cfg=None,
    ex_cfg=None,
) -> Optional[T10RaceRoi]:
    scored = _score_t10_race(date_yyyymmdd, race_id, master, win_cfg=win_cfg, ex_cfg=ex_cfg)
    if scored is None:
        return None

    plan, top5, final_race, _snap = scored
    if not is_tier_s_plus(plan.expectation_tier):
        return None

    finish = _finish_order(final_race)
    if len(finish) < 3 or top5.empty:
        return None

    formation = build_sanrenpuku_formation_firm(top5)
    if formation is None or formation.points <= 0:
        return None

    row = T10RaceRoi(
        race_id=race_id,
        race_no=int(final_race["race_no"].iloc[0]),
        race_name=str(final_race.get("race_name", pd.Series([""])).iloc[0]),
        race_class=_race_class(final_race),
        expectation_tier=plan.expectation_tier,
        expectation_score=int(plan.expectation_score or 0),
        sanren_points=formation.points,
        sanren_display=(
            f"{format_sanrenpuku_formation_umaban_line(formation)}"
            f"(\u8a08{formation.points}\u70b9)"
        ),
        investment=formation.points * BET_UNIT,
    )
    if check_sanrenpuku_formation_firm_hit(formation, finish):
        row.sanren_hit = True
        if payback:
            row.return_yen = payback.fuku3_yen
    return row


def build_t10_daily_roi_report(
    date_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    fetch_payback: bool = True,
) -> T10DailyRoiReport:
    master_df = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    race_ids = list_snapshot_race_ids(date_yyyymmdd, label=LABEL_T_MINUS_10)
    report = T10DailyRoiReport(date=date_yyyymmdd)

    if not race_ids:
        return report

    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)

    for rid in race_ids:
        scored = _score_t10_race(date_yyyymmdd, rid, master_df, win_cfg=win_cfg, ex_cfg=ex_cfg)
        if scored is None:
            continue
        plan, _top5, final_race, _ = scored
        if not is_tier_s_plus(plan.expectation_tier):
            report.skipped_not_s_plus += 1
            continue
        if len(_finish_order(final_race)) < 3:
            report.skipped_no_result += 1
            continue
        row = compute_t10_race_roi(
            date_yyyymmdd,
            rid,
            master_df,
            paybacks.get(rid),
            win_cfg=win_cfg,
            ex_cfg=ex_cfg,
        )
        if row is not None:
            report.races.append(row)

    report.races.sort(key=lambda r: r.race_no)
    return report


def _format_t10_race_block(r: T10RaceRoi) -> List[str]:
    cls = f" {r.race_class}" if r.race_class else ""
    name = r.race_name[:16] if r.race_name else ""
    lines = [f"{r.race_no}R {name}{cls} \u671f\u5f85\u5024{r.expectation_tier}"]
    if r.sanren_display:
        lines.append(f"\u4e09\u9023\u8907\u3000{r.sanren_display}")
    else:
        lines.append("\u4e09\u9023\u8907\u3000\u2015")
    lines.append(
        f"\u6295{r.investment}\u5186\u3000\u6255{r.return_yen}\u5186\u3000"
        f"\u56de\u53ce{r.roi_pct:.0f}%"
    )
    return lines


def _format_t10_daily_summary(report: T10DailyRoiReport) -> List[str]:
    """文末の当日合計ブロック。"""
    if not report.races:
        return []

    profit = report.total_return - report.total_investment
    profit_sign = "+" if profit > 0 else ""
    return [
        "",
        "【当日合計】",
        f"対象 {len(report.races)}R / {report.total_points}点",
        f"投資 {report.total_investment:,}円",
        f"払戻 {report.total_return:,}円",
        f"収支 {profit_sign}{profit:,}円",
        f"回収率 {report.total_roi_pct:.0f}%",
        (
            f"的中 {report.race_hit_count}/{len(report.races)}R"
            f"（三連複{report.sanren_hit_count}）"
        ),
    ]


def _format_report_date_label(date_yyyymmdd: str) -> str:
    return f"{int(date_yyyymmdd[4:6])}\u6708{int(date_yyyymmdd[6:8])}\u65e5"


def format_t10_daily_roi_message(report: T10DailyRoiReport) -> str:
    date_label = _format_report_date_label(report.date)
    lines: List[str] = [
        f"\u3010\u5712\u7530 {date_label} \u8cb7\u3044\u76ee\u306e\u6210\u7e3e\u3011",
        "\u203b\u30ec\u30fc\u30b910\u5206\u524d\u306b\u914d\u4fe1\u3057\u305f\u4e88\u60f3\u3069\u304a\u308a\u306b\u8cb7\u3063\u305f\u60f3\u5b9a",
        "\u5bfe\u8c61: \u671f\u5f85\u5024S\u4ee5\u4e0a\u306e\u30ec\u30fc\u30b9",
        f"\u8cb7\u3044\u65b9: {S_PLUS_BUY_LABEL}",
        "",
    ]

    if not report.races:
        lines.append("\u5bfe\u8c61\u30ec\u30fc\u30b9\u306a\u3057")
        if report.skipped_not_s_plus:
            lines.append(
                f"\uff08\u671f\u5f85\u5024S\u672a\u6e80\u306e\u305f\u3081\u5bfe\u8c61\u5916: "
                f"{report.skipped_not_s_plus}\u30ec\u30fc\u30b9\uff09"
            )
        if report.skipped_no_result:
            lines.append(
                f"\uff08\u7d50\u679c\u672a\u53d6\u5f97: {report.skipped_no_result}\u30ec\u30fc\u30b9\uff09"
            )
        return "\n".join(lines)

    for r in report.races:
        lines.extend(_format_t10_race_block(r))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    lines.extend(_format_t10_daily_summary(report))
    return "\n".join(lines)
