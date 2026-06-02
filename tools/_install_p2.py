from pathlib import Path
import ast
import textwrap

ROOT = Path(__file__).resolve().parent.parent
KEN = "\u5805"
ARE = "\u8352"

def write(relpath, content):
    p = ROOT / relpath
    p.write_text(content, encoding="utf-8")
    ast.parse(content, filename=str(p))
    print("OK", relpath)

analyze = f'''"""2026 Q1 collapse analysis (split scoring)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.predictor.backtest import (
    _aggregate_records,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY
from src.predictor.score import load_master
from src.predictor.scoring_config import load_split_scoring_configs

KEN = "{KEN}"
ARE = "{ARE}"


def _period_stats(records, label: str) -> dict:
    st = DEFAULT_STRATEGY
    n = len(records)
    if not n:
        return {{"label": label, "races": 0}}
    win_prof = Counter(r.win_profile for r in records)
    ex_prof = Counter(r.exotic_profile for r in records)
    exotic_bets = [r for r in records if _exotic_high_for_record(r, st)]
    sp_hits: list[int] = []
    for r in exotic_bets:
        if r.exotic_profile == KEN:
            hit, pts = r.sanrenpuku_hit, r.sanrenpuku_points
        else:
            hit, pts = r.sanrenpuku_box_hit, r.sanrenpuku_box_points
        if pts and hit and r.fuku3_yen > 0:
            sp_hits.append(r.fuku3_yen)
    report = _aggregate_records(records, "00000000", "99999999", strategy=st)
    return {{
        "label": label,
        "races": n,
        "win_ken": win_prof.get(KEN, 0),
        "ex_ken": ex_prof.get(KEN, 0),
        "exotic_bets": len(exotic_bets),
        "sp_hit_n": len(sp_hits),
        "sp_hit_med": float(pd.Series(sp_hits).median()) if sp_hits else 0.0,
        "sanren_roi": report.sanrenpuku.roi,
        "win_roi": report.win_pick.roi,
        "wide_roi": report.wide.roi,
    }}


def _print_row(s: dict) -> None:
    if not s["races"]:
        print(f"  {{s['label']}}: (no races)")
        return
    hr = s["sp_hit_n"] / s["exotic_bets"] if s["exotic_bets"] else 0.0
    print(
        f"  {{s['label']}}: {{s['races']}}R "
        f"\\u5805\\u5358{{s['win_ken']/s['races']:.1%}} \\u5805\\u4e09{{s['ex_ken']/s['races']:.1%}} "
        f"\\u4e09\\u9023\\u7684\\u4e2d{{hr:.1%}} \\u7684\\u4e2d\\u914d\\u5f53\\u4e2d\\u592e{{s['sp_hit_med']:,.0f}}\\u5186 "
        f"ROI \\u5358{{s['win_roi']:.1%}} \\u4e09\\u9023{{s['sanren_roi']:.1%}} \\u30ef{{s['wide_roi']:.1%}}"
    )


def main() -> None:
    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    print("=== 2026 Q1 \\u5206\\u6790\\uff08split: style + sanrenpuku\\uff09===\\n")
    for label, start, end in [
        ("2026/1-3", "20260101", "20260331"),
        ("2026/4-5", "20260401", "20260531"),
        ("2026/1-5", "20260101", "20260531"),
    ]:
        hist = master[
            (master["date"].astype(str) >= start) & (master["date"].astype(str) <= end)
        ]
        race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
        paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
        recs = _collect_race_records(
            start, end, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
        )
        _print_row(_period_stats(recs, label))

    print("\\n--- \\u6708\\u5225\\u4e09\\u9023ROI / payback coverage ---")
    for month in ("202601", "202602", "202603", "202604", "202605"):
        start, end = month + "01", month + "31"
        hist = master[
            (master["date"].astype(str) >= start) & (master["date"].astype(str) <= end)
        ]
        if hist.empty:
            print(f"  {{month}}: master \\u306a\\u3057")
            continue
        race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
        paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
        recs = _collect_race_records(
            start, end, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
        )
        s = _period_stats(recs, month)
        if s["races"]:
            print(
                f"  {{month}}: \\u4e09\\u9023ROI {{s['sanren_roi']:.1%}} "
                f"({{s['races']}}R, payback {{len(paybacks)}}/{{len(race_ids)}})"
            )


if __name__ == "__main__":
    main()
'''

write("scripts/analyze_q1_collapse.py", analyze)
