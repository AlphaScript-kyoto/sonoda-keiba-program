"""予想用の学習期間: 2年前・1年前・当年（基準日以前）。"""

from __future__ import annotations

from typing import List, Tuple

import pandas as pd


def get_training_ranges(reference_date: str) -> List[Tuple[str, str]]:
    """基準日（通常は予想日）に対する重み学習用の3期間を返す。

    - 当年: YYYY0101 〜 基準日の前日（結果確定済みデータのみ）
    - 1年前: 前年の通年
    - 2年前: 一昨年の通年
    """
    ref = pd.to_datetime(reference_date, format="%Y%m%d")
    year = ref.year
    prev_day = (ref - pd.Timedelta(days=1)).strftime("%Y%m%d")

    ranges: List[Tuple[str, str]] = []

    year_start = f"{year}0101"
    if prev_day >= year_start:
        ranges.append((year_start, prev_day))

    ranges.append((f"{year - 1}0101", f"{year - 1}1231"))
    ranges.append((f"{year - 2}0101", f"{year - 2}1231"))
    return ranges


def describe_training_ranges(reference_date: str) -> str:
    """学習期間を人間向けに整形。"""
    return " / ".join(f"{a}〜{b}" for a, b in get_training_ranges(reference_date))


def filter_master_by_training_window(
    master: pd.DataFrame,
    reference_date: str,
) -> pd.DataFrame:
    """学習ウィンドウに含まれるマスタ行のみ返す。"""
    ranges = get_training_ranges(reference_date)
    dates = master["date"].astype(str)
    mask = pd.Series(False, index=master.index)
    for from_date, to_date in ranges:
        mask |= (dates >= from_date) & (dates <= to_date)
    return master[mask].copy()
