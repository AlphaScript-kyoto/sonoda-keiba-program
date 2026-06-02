"""印（◎〜☆）の固定順表示用。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pandas as pd

from src.predictor.bets import MARKS, RaceBetPlan
from src.predictor.score import DISPLAY_SOFTMAX_TEMPERATURE, load_master, tempered_probabilities

MarkLine = Tuple[str, str, str]
MARK_RANK = {m: i for i, m in enumerate(MARKS)}


def normalize_umaban(value) -> str:
    s = str(value).strip()
    if s.isdigit():
        return str(int(s))
    return s


def filter_race_df(df: pd.DataFrame, race_no: int | str) -> pd.DataFrame:
    """race_no の int/str 差を吸収してレース行を抽出。"""
    if df.empty or "race_no" not in df.columns:
        return pd.DataFrame()
    key = str(race_no).strip()
    return df[df["race_no"].astype(str).str.strip() == key].copy()


def sort_marks(marks: Sequence[MarkLine]) -> List[MarkLine]:
    """◎→○→▲→△→☆ の順に並べ替え。"""
    return sorted(marks, key=lambda x: MARK_RANK.get(x[0], 99))


def career_win_stats(
    master: pd.DataFrame,
    horse_id: str,
    before_date: str,
) -> tuple[int, int, Optional[float]]:
    """後方互換: (1着数, 走数, 勝率)。"""
    wins, places, runs, win_r, _ = _career_rates_raw(master, horse_id, before_date)
    if runs == 0 or win_r is None:
        return 0, 0, None
    return wins, runs, win_r


def _career_rates_raw(
    master: pd.DataFrame,
    horse_id: str,
    before_date: str,
) -> tuple[int, int, int, Optional[float], Optional[float]]:
    hid = str(horse_id).strip()
    if not hid or master.empty or not before_date:
        return 0, 0, 0, None, None
    hist = master[
        (master["horse_id"].astype(str) == hid)
        & (master["date"].astype(str) < str(before_date))
    ]
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    valid = finish.notna()
    runs = int(valid.sum())
    if runs == 0:
        return 0, 0, 0, None, None
    f = finish[valid]
    wins = int((f == 1).sum())
    places = int((f <= 2).sum())
    return wins, places, runs, wins / runs, places / runs


def build_marks_display_frame(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame] = None,
    *,
    master: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """三連印5頭を ◎ 順で1行ずつ（オッズ等は三連スコア行を優先）。"""
    if not plan.marks:
        return pd.DataFrame()

    win_race = filter_race_df(win_df, plan.race_no)
    ex_race = filter_race_df(exotic_df, plan.race_no) if exotic_df is not None else pd.DataFrame()

    def _index_by_umaban(df: pd.DataFrame) -> dict[str, pd.Series]:
        if df.empty or "umaban" not in df.columns:
            return {}
        out: dict[str, pd.Series] = {}
        for _, row in df.iterrows():
            out[normalize_umaban(row["umaban"])] = row
        return out

    ex_by_u = _index_by_umaban(ex_race)
    win_by_u = _index_by_umaban(win_race)

    prob_source = ex_race if not ex_race.empty else win_race
    prob_by_u: dict[str, float] = {}
    win_rate_by_u: dict[str, float] = {}
    place_rate_by_u: dict[str, float] = {}
    before_date = ""
    if not prob_source.empty and "date" in prob_source.columns:
        before_date = str(prob_source["date"].iloc[0]).strip()

    if not prob_source.empty and "score" in prob_source.columns:
        tempered = tempered_probabilities(prob_source["score"], DISPLAY_SOFTMAX_TEMPERATURE)
        for idx, row in prob_source.iterrows():
            prob_by_u[normalize_umaban(row["umaban"])] = float(tempered.loc[idx])

    mst = master
    if mst is None and before_date:
        try:
            mst = load_master()
        except FileNotFoundError:
            mst = None

    rows: List[dict] = []
    for mark, umaban, horse_name in sort_marks(plan.marks):
        u = normalize_umaban(umaban)
        src = ex_by_u.get(u)
        if src is None:
            src = win_by_u.get(u)
        hid = str(src.get("horse_id", "")).strip() if src is not None else ""
        win_r: Optional[float] = None
        place_r: Optional[float] = None
        if mst is not None and before_date and hid:
            _, _, runs, win_r, place_r = _career_rates_raw(mst, hid, before_date)
            if runs == 0:
                win_r, place_r = None, None
        if win_r is None and src is not None:
            feat = pd.to_numeric(src.get("horse_win_rate"), errors="coerce")
            if pd.notna(feat):
                win_r = float(feat)
        if win_r is not None:
            win_rate_by_u[u] = win_r
        if place_r is not None:
            place_rate_by_u[u] = place_r
        row = {
            "mark": mark,
            "umaban": umaban,
            "horse_name": horse_name if horse_name else (src.get("horse_name", "") if src is not None else ""),
            "win_prob": prob_by_u.get(u),
            "horse_win_rate": win_rate_by_u.get(u),
            "horse_place_rate": place_rate_by_u.get(u),
            "odds": src.get("odds", "") if src is not None else "",
            "popularity": src.get("popularity", "") if src is not None else "",
        }
        rows.append(row)

    return pd.DataFrame(rows)
