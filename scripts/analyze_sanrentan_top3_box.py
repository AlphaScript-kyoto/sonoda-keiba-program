"""◎・○・▲ 三連単BOX（6点）の回収率と1-3着決着率を集計。"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (  # noqa: E402
    BET_UNIT,
    _collect_race_records,
    _finish_order,
    _load_paybacks_for_races,
)
from src.predictor.bets import MARKS, assign_marks  # noqa: E402
from src.predictor.score import load_master, score_entries  # noqa: E402
from src.predictor.scoring_config import load_split_scoring_configs  # noqa: E402

TOP3_MARKS = MARKS[:3]  # ◎, ○, ▲
BOX_POINTS = 6  # 3頭三連単BOX


@dataclass
class YearStats:
    year: str
    races: int = 0
    top3_set_hits: int = 0
    box_hits: int = 0
    investment: int = 0
    return_yen: int = 0

    @property
    def top3_set_rate(self) -> float:
        return self.top3_set_hits / self.races if self.races else 0.0

    @property
    def box_hit_rate(self) -> float:
        return self.box_hits / self.races if self.races else 0.0

    @property
    def roi(self) -> float:
        return self.return_yen / self.investment if self.investment else 0.0


def _marked_top3(top5) -> list[str]:
    return [str(u) for u in top5.head(3)["umaban"].tolist()]


def _top3_set_hit(marked: list[str], finish: list[str]) -> bool:
    if len(marked) < 3 or len(finish) < 3:
        return False
    return set(marked) == set(finish[:3])


def _box_hit(marked: list[str], finish: list[str]) -> bool:
    if len(marked) < 3 or len(finish) < 3:
        return False
    key = tuple(finish[:3])
    return key in set(permutations(marked, 3))


def analyze(from_date: str, to_date: str, *, fetch_missing: bool = False) -> dict:
    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()

    hist = master[
        (master["date"].astype(str) >= from_date)
        & (master["date"].astype(str) <= to_date)
    ]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_missing)

    by_year: dict[str, YearStats] = {}
    total = YearStats(year="total")

    for date in sorted(hist["date"].astype(str).unique()):
        year = date[:4]
        if year not in by_year:
            by_year[year] = YearStats(year=year)

        entries = hist[hist["date"].astype(str) == date]
        scored = score_entries(entries, master, config=ex_cfg)
        if scored.empty:
            continue

        actual_by_race = {
            str(rid): grp for rid, grp in entries.groupby("race_id")
        }

        for race_id, pred_group in scored.groupby("race_id", sort=False):
            race_id = str(race_id)
            actual = actual_by_race.get(race_id)
            if actual is None or actual.empty:
                continue

            finish = _finish_order(actual)
            if len(finish) < 3:
                continue

            top5 = assign_marks(pred_group)
            marked = _marked_top3(top5)
            if len(marked) < 3:
                continue

            pb = paybacks.get(race_id)
            tan3_yen = pb.tan3_yen if pb else 0

            top3_hit = _top3_set_hit(marked, finish)
            box_hit = _box_hit(marked, finish)
            invest = BOX_POINTS * BET_UNIT
            ret = tan3_yen if box_hit else 0

            for stats in (by_year[year], total):
                stats.races += 1
                stats.investment += invest
                stats.return_yen += ret
                if top3_hit:
                    stats.top3_set_hits += 1
                if box_hit:
                    stats.box_hits += 1

    return {"by_year": by_year, "total": total}


def _print_stats(label: str, s: YearStats) -> None:
    print(f"\n=== {label} ===")
    print(f"  対象レース数: {s.races:,}R")
    print(
        f"  ◎○▲が1-3着を占有（順不同）: "
        f"{s.top3_set_hits:,}R / {s.top3_set_rate:.2%}"
    )
    print(
        f"  三連単BOX(6点)的中: "
        f"{s.box_hits:,}R / {s.box_hit_rate:.2%}"
    )
    print(
        f"  投資: {s.investment:,}円 → 払戻: {s.return_yen:,}円 "
        f"/ 回収率(ROI): {s.roi:.2%}"
    )
    if s.races:
        avg_pay = s.return_yen / s.box_hits if s.box_hits else 0
        print(f"  的中時平均払戻: {avg_pay:,.0f}円")


def main() -> None:
    parser = argparse.ArgumentParser(description="◎○▲三連単BOX分析")
    parser.add_argument("--from", dest="from_date", default="20240101")
    parser.add_argument("--to", dest="to_date", default="20261231")
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="払戻キャッシュに無いレースをnetkeibaから取得",
    )
    args = parser.parse_args()

    print(
        f"期間: {args.from_date} 〜 {args.to_date}\n"
        f"買い方: ◎・○・▲の3頭 三連単BOX（6点 × {BET_UNIT}円 = "
        f"{BOX_POINTS * BET_UNIT}円/R）"
    )

    result = analyze(args.from_date, args.to_date, fetch_missing=args.fetch_missing)

    for year in sorted(result["by_year"]):
        _print_stats(year, result["by_year"][year])

    _print_stats(f"合計 ({args.from_date}〜{args.to_date})", result["total"])


if __name__ == "__main__":
    main()
