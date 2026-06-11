"""Generate formation_247.py and compare script (UTF-8)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORMATION_247 = r'''"""三連複 2-4-7型（2x2x2列）の馬選び・レース選定。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import comb
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.features.utils import parse_distance_m
from src.predictor.bets import RaceSignals, SanrenpukuBox, _parse_odds_value

_PLACE_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class Formation247Config:
    place_odds_max: float = 2.0
    col2_pop_max: int = 5
    col3_pop_min: int = 10
    min_head_count: int = 10
    min_odds_std: float = 70.0
    short_distance_max_m: float = 1400.0
    upset_classes: Tuple[str, ...] = ("C1", "C2", "C3", "B2", "B1")
    require_upset_profile: bool = True
    min_upset_score: int = 3
    horses_per_column: int = 2


DEFAULT_FORMATION_247 = Formation247Config()


def parse_place_odds_low(place_odds: str) -> float:
    s = str(place_odds or "").strip().replace(",", "")
    if not s:
        return float("nan")
    m = _PLACE_RANGE_RE.match(s)
    if m:
        return float(m.group(1))
    return _parse_odds_value(s)


def top3_rate_for_horse(master: pd.DataFrame, horse_id: str, before_date: str) -> float:
    hid = str(horse_id).strip()
    if not hid or master.empty:
        return 0.0
    hist = master[
        (master["horse_id"].astype(str) == hid)
        & (master["date"].astype(str) < str(before_date))
    ]
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    valid = finish.notna()
    runs = int(valid.sum())
    if runs == 0:
        return 0.0
    return int((finish[valid] <= 3).sum()) / runs


def _race_df_enriched(race_df: pd.DataFrame, master: pd.DataFrame, before_date: str) -> pd.DataFrame:
    out = race_df.copy()
    out["pop_n"] = pd.to_numeric(out.get("popularity"), errors="coerce")
    out["win_odds_n"] = pd.to_numeric(out.get("odds"), errors="coerce")
    if "place_odds" in out.columns:
        out["place_low"] = out["place_odds"].map(parse_place_odds_low)
    else:
        out["place_low"] = np.nan
    out["top3_rate"] = [
        top3_rate_for_horse(master, str(row.get("horse_id", "")), before_date)
        for _, row in out.iterrows()
    ]
    return out


def is_247_target_race(
    race_df: pd.DataFrame,
    signals: RaceSignals,
    *,
    exotic_profile: str = "\u5805",
    cfg: Formation247Config = DEFAULT_FORMATION_247,
) -> bool:
    if cfg.require_upset_profile and exotic_profile != "\u8352":
        return False
    if signals.upset_score < cfg.min_upset_score:
        return False
    if signals.head_count < cfg.min_head_count:
        return False
    if signals.odds_std < cfg.min_odds_std:
        return False
    race_class = str(race_df.get("race_class", pd.Series([""])).iloc[0]).upper()
    distance_m = parse_distance_m(race_df.get("distance", pd.Series([""])).iloc[0])
    class_hit = any(race_class.startswith(c) for c in cfg.upset_classes)
    short_hit = not np.isnan(distance_m) and distance_m > 0 and distance_m <= cfg.short_distance_max_m
    return class_hit or short_hit or signals.head_count >= 12


def _pick_column(
    pool: pd.DataFrame,
    n: int,
    *,
    exclude: set[str],
    sort_cols: Sequence[str],
    ascending: Sequence[bool],
) -> pd.DataFrame:
    cand = pool[~pool["umaban"].astype(str).isin(exclude)].copy()
    if cand.empty:
        return cand.iloc[0:0]
    return cand.sort_values(list(sort_cols), ascending=list(ascending)).head(n)


def select_247_horses(
    race_df: pd.DataFrame,
    master: pd.DataFrame,
    before_date: str,
    cfg: Formation247Config = DEFAULT_FORMATION_247,
) -> Optional[pd.DataFrame]:
    if len(race_df) < 6:
        return None
    df = _race_df_enriched(race_df, master, before_date)
    n = cfg.horses_per_column
    picked: List[pd.Series] = []
    exclude: set[str] = set()

    col1_pool = df[df["place_low"].notna() & (df["place_low"] <= cfg.place_odds_max)]
    if len(col1_pool) < n:
        col1_pool = df[df["place_low"].notna()].sort_values("place_low")
    if col1_pool.empty:
        col1_pool = df.sort_values("win_odds_n")
    for _, row in _pick_column(
        col1_pool, n, exclude=exclude, sort_cols=["top3_rate", "place_low"], ascending=[False, True]
    ).iterrows():
        picked.append(row)
        exclude.add(str(row["umaban"]))

    for _, row in _pick_column(
        df[df["pop_n"].between(1, cfg.col2_pop_max)],
        n,
        exclude=exclude,
        sort_cols=["top3_rate", "pop_n"],
        ascending=[False, True],
    ).iterrows():
        picked.append(row)
        exclude.add(str(row["umaban"]))

    for _, row in _pick_column(
        df[df["pop_n"] >= cfg.col3_pop_min],
        n,
        exclude=exclude,
        sort_cols=["top3_rate", "win_odds_n"],
        ascending=[False, False],
    ).iterrows():
        picked.append(row)
        exclude.add(str(row["umaban"]))

    if len(picked) < 6:
        remain = df[~df["umaban"].astype(str).isin(exclude)].sort_values("top3_rate", ascending=False)
        for _, row in remain.iterrows():
            if len(picked) >= 6:
                break
            picked.append(row)
    if len(picked) < 6:
        return None
    return pd.DataFrame(picked[:6])


def build_sanrenpuku_247_box(
    race_df: pd.DataFrame,
    master: pd.DataFrame,
    before_date: str,
    cfg: Formation247Config = DEFAULT_FORMATION_247,
) -> Optional[SanrenpukuBox]:
    horses = select_247_horses(race_df, master, before_date, cfg)
    if horses is None or len(horses) < 6:
        return None
    umaban = [str(u) for u in horses["umaban"]]
    names = [str(n) for n in horses["horse_name"]]
    return SanrenpukuBox(umaban=umaban, names=names, points=comb(len(umaban), 3))
'''

COMPARE_SCRIPT = r'''"""A/B backtest: model upset BOX vs 2-4-7 formation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY, check_sanrenpuku_box_hit
from src.predictor.formation_247 import (
    DEFAULT_FORMATION_247,
    build_sanrenpuku_247_box,
    is_247_target_race,
)
import pandas as pd

from src.predictor.score import load_master
from src.predictor.scoring_config import load_split_scoring_configs


def _roi(hits: int, races: int, invest: int, return_yen: int) -> dict:
    return {
        "races": races,
        "hits": hits,
        "hit_rate": hits / races if races else 0.0,
        "invest": invest,
        "return_yen": return_yen,
        "roi": return_yen / invest if invest else 0.0,
    }


def compare_period(from_d: str, to_d: str) -> None:
    master = load_master()
    hist = master[
        (master["date"].astype(str) >= from_d) & (master["date"].astype(str) <= to_d)
    ]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    win_cfg, ex_cfg = load_split_scoring_configs()
    records = _collect_race_records(
        from_d, to_d, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
    )

    model = {"races": 0, "hits": 0, "invest": 0, "return_yen": 0}
    f247 = {"races": 0, "hits": 0, "invest": 0, "return_yen": 0}
    f247_skip = 0

    ex_by_date_race: dict[tuple[str, int], object] = {}
    for date in sorted(hist["date"].astype(str).unique()):
        day = hist[hist["date"].astype(str) == date]
        for rid, grp in day.groupby("race_id"):
            ex_by_date_race[(date, int(grp["race_no"].iloc[0]))] = grp

    for rec in records:
        if not _exotic_high_for_record(rec, DEFAULT_STRATEGY):
            continue
        if rec.exotic_profile != "\u8352":
            continue

        if rec.sanrenpuku_box_points:
            model["races"] += 1
            model["invest"] += rec.sanrenpuku_box_points * BET_UNIT
            if rec.sanrenpuku_box_hit:
                model["hits"] += 1
                model["return_yen"] += rec.fuku3_yen

        race_df = ex_by_date_race.get((rec.date, rec.race_no))
        if race_df is None:
            f247_skip += 1
            continue
        from src.predictor.bets import collect_race_signals

        sig = collect_race_signals(race_df, rec.exotic_prob_top, rec.exotic_prob_gap)
        if not is_247_target_race(race_df, sig, exotic_profile=rec.exotic_profile):
            f247_skip += 1
            continue
        box = build_sanrenpuku_247_box(race_df, master, rec.date, DEFAULT_FORMATION_247)
        if box is None:
            f247_skip += 1
            continue
        f247["races"] += 1
        f247["invest"] += box.points * BET_UNIT
        finish = (
            race_df.assign(finish_num=pd.to_numeric(race_df["finish"], errors="coerce"))
            .dropna(subset=["finish_num"])
            .sort_values("finish_num")["umaban"]
            .astype(str)
            .tolist()
        )
        if len(finish) >= 3 and check_sanrenpuku_box_hit(box, finish):
            f247["hits"] += 1
            f247["return_yen"] += rec.fuku3_yen

    print(f"=== 2-4-7 A/B {from_d} .. {to_d} ===")
    print(f"records: {len(records)}  247 skipped: {f247_skip}")
    m = _roi(**model)
    f = _roi(**f247)
    print(
        f"Model BOX(荒+高): {m['races']}R hit {m['hits']} ({m['hit_rate']:.1%}) "
        f"ROI {m['roi']:.1%} invest {m['invest']:,} return {m['return_yen']:,}"
    )
    print(
        f"2-4-7 BOX:       {f['races']}R hit {f['hits']} ({f['hit_rate']:.1%}) "
        f"ROI {f['roi']:.1%} invest {f['invest']:,} return {f['return_yen']:,}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    args = parser.parse_args()
    compare_period(args.from_date, args.to_date)


if __name__ == "__main__":
    main()
'''

TEST_FORMATION = r'''"""formation_247 tests."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceSignals, check_sanrenpuku_box_hit
from src.predictor.formation_247 import (
    build_sanrenpuku_247_box,
    is_247_target_race,
    parse_place_odds_low,
    select_247_horses,
)


def test_parse_place_odds_low():
    assert parse_place_odds_low("1.5-2.8") == 1.5
    assert parse_place_odds_low("3.2") == 3.2


def _sample_master():
    rows = []
    for i in range(1, 13):
        for d in ("20260101", "20260201", "20260301"):
            rows.append(
                {
                    "horse_id": f"h{i:02d}",
                    "date": d,
                    "finish": "1" if i <= 3 else "5",
                }
            )
    return pd.DataFrame(rows)


def _sample_race():
    rows = []
    for i in range(1, 13):
        rows.append(
            {
                "race_id": "r1",
                "date": "20260610",
                "race_no": 1,
                "horse_id": f"h{i:02d}",
                "horse_name": f"H{i}",
                "umaban": str(i),
                "popularity": str(i),
                "odds": str(2 + i * 1.5),
                "place_odds": "1.2-1.5" if i <= 2 else "3.0-5.0",
                "race_class": "C3",
                "distance": "1200m",
            }
        )
    return pd.DataFrame(rows)


def test_select_247_horses_six():
    race = _sample_race()
    master = _sample_master()
    horses = select_247_horses(race, master, "20260610")
    assert horses is not None
    assert len(horses) == 6


def test_build_box_points():
    race = _sample_race()
    master = _sample_master()
    box = build_sanrenpuku_247_box(race, master, "20260610")
    assert box is not None
    assert box.points == 20


def test_is_247_target_upset():
    race = _sample_race()
    sig = RaceSignals(
        fav_odds=4.0,
        head_count=12,
        odds_std=90.0,
        win_prob_top=0.5,
        prob_gap=0.1,
        upset_score=4,
        race_class="C3",
        distance_m=1200.0,
    )
    assert is_247_target_race(race, sig, exotic_profile="\u8352")
'''

FILES = {
    "src/predictor/formation_247.py": FORMATION_247,
    "scripts/backtest_247_compare.py": COMPARE_SCRIPT,
    "tests/test_formation_247.py": TEST_FORMATION,
}


def main() -> None:
    for rel, content in FILES.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"wrote {rel} nulls={path.read_bytes().count(b'\\x00')}")


if __name__ == "__main__":
    main()
