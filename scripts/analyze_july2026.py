"""2026年7月の馬券ロジック振り返り（split scoring・期間比較）。

使い方（リポジトリ直下で）:
  .\\.venv\\Scripts\\python.exe scripts\\analyze_july2026.py
  .\\.venv\\Scripts\\python.exe scripts\\analyze_july2026.py --quick
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _configure_stdio() -> None:
    """Windows コンソールでの日本語文字化け・UnicodeEncodeError を緩和。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


_configure_stdio()

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

KEN = "堅"
ARE = "荒"
SNAPSHOTS = ROOT / "data" / "processed" / "snapshots"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _period_stats(records, label: str) -> dict:
    st = DEFAULT_STRATEGY
    n = len(records)
    if not n:
        return {"label": label, "races": 0}
    win_prof = Counter(r.win_profile for r in records)
    ex_prof = Counter(r.exotic_profile for r in records)
    exotic_bets = [r for r in records if _exotic_high_for_record(r, st)]
    sp_hits: list[int] = []
    for r in exotic_bets:
        if r.exotic_profile == KEN:
            hit, pts = r.sanrenpuku_hit, r.sanrenpuku_points
        else:
            hit, pts = r.sanrenpuku_formation_hit, r.sanrenpuku_formation_points
            if not pts:
                hit, pts = r.sanrenpuku_box_hit, r.sanrenpuku_box_points
        if pts and hit and r.fuku3_yen > 0:
            sp_hits.append(r.fuku3_yen)
    report = _aggregate_records(records, "00000000", "99999999", strategy=st)
    return {
        "label": label,
        "races": n,
        "win_ken": win_prof.get(KEN, 0),
        "win_are": win_prof.get(ARE, 0),
        "ex_ken": ex_prof.get(KEN, 0),
        "ex_are": ex_prof.get(ARE, 0),
        "exotic_bets": len(exotic_bets),
        "sp_hit_n": len(sp_hits),
        "sp_hit_med": float(pd.Series(sp_hits).median()) if sp_hits else 0.0,
        "sanren_roi": report.sanrenpuku.roi,
        "sanrentan_roi": report.sanrentan.roi,
        "win_roi": report.win_pick.roi,
        "place_roi": report.place_pick.roi,
        "wide_roi": report.wide.roi,
        "win_races": report.win_pick.races,
        "win_hits": report.win_pick.hits,
        "sp_races": report.sanrenpuku.races,
        "sp_hits": report.sanrenpuku.hits,
        "st_races": report.sanrentan.races,
        "st_hits": report.sanrentan.hits,
    }


def _print_row(s: dict) -> None:
    if not s["races"]:
        _log(f"  {s['label']}: (no races)")
        return
    hr = s["sp_hits"] / s["sp_races"] if s["sp_races"] else 0.0
    wh = s["win_hits"] / s["win_races"] if s["win_races"] else 0.0
    _log(
        f"  {s['label']}: {s['races']}R "
        f"堅単{s['win_ken']/s['races']:.1%} 堅三{s['ex_ken']/s['races']:.1%} "
        f"単的中{wh:.1%} 三的中{hr:.1%} 的中配当中央{s['sp_hit_med']:,.0f}円 "
        f"ROI 単{s['win_roi']:.1%} 複{s['place_roi']:.1%} "
        f"三連{s['sanren_roi']:.1%} 三単{s['sanrentan_roi']:.1%} ワ{s['wide_roi']:.1%}"
    )


def _load_period(master, win_cfg, ex_cfg, start: str, end: str):
    hist = master[
        (master["date"].astype(str) >= start) & (master["date"].astype(str) <= end)
    ]
    if hist.empty:
        return [], 0, 0
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    _log(f"    scoring {len(race_ids)} races ({start}..{end}) ...")
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    recs = _collect_race_records(
        start, end, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
    )
    return recs, len(race_ids), len(paybacks)


def _parse_compare_summaries() -> pd.DataFrame:
    rows = []
    if not SNAPSHOTS.exists():
        return pd.DataFrame()
    # 「◎」が他エンコーディングだと壊れるので、英語ラベル/フォールバックも許容
    summary_re = re.compile(
        r"=== (t_minus_\d+) vs Final \((\d+) races\) ===.*?--- Summary ---\n"
        r"win profile match:\s+(\d+)% \((\d+)/(\d+)\)\n"
        r"exotic profile match:\s+(\d+)% \((\d+)/(\d+)\)\n"
        r".*? umaban match:\s+(\d+)% \((\d+)/(\d+)\)\n"
        r"win confidence match:\s+(\d+)% .*?\n"
        r"exotic conf match:\s+(\d+)% .*?\n"
        r"winner in top3 \(live\):\s+(\d+)/(\d+)\n"
        r"winner in top3 \(final\):\s+(\d+)/(\d+)",
        re.DOTALL,
    )
    for day_dir in sorted(SNAPSHOTS.glob("202607*")):
        path = day_dir / "compare_report.txt"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in summary_re.finditer(text):
            rows.append(
                {
                    "date": day_dir.name,
                    "snapshot": m.group(1),
                    "n_races": int(m.group(2)),
                    "win_prof_match_pct": int(m.group(3)),
                    "ex_prof_match_pct": int(m.group(6)),
                    "mark_match_pct": int(m.group(9)),
                    "win_conf_match_pct": int(m.group(12)),
                    "ex_conf_match_pct": int(m.group(13)),
                    "top3_live": int(m.group(14)),
                    "top3_live_n": int(m.group(15)),
                    "top3_final": int(m.group(16)),
                    "top3_final_n": int(m.group(17)),
                }
            )
    return pd.DataFrame(rows)


def _print_compare(df: pd.DataFrame) -> None:
    if df.empty:
        _log("  (compare_report.txt なし)")
        return
    t30 = df[df["snapshot"] == "t_minus_30"]
    t10 = df[df["snapshot"] == "t_minus_10"]
    for label, sub in (("T-30", t30), ("T-10", t10)):
        if sub.empty:
            continue
        top3 = sub["top3_final"].sum() / sub["top3_final_n"].sum()
        mark = (sub["mark_match_pct"] * sub["n_races"]).sum() / sub["n_races"].sum()
        wp = (sub["win_prof_match_pct"] * sub["n_races"]).sum() / sub["n_races"].sum()
        ep = (sub["ex_prof_match_pct"] * sub["n_races"]).sum() / sub["n_races"].sum()
        _log(
            f"  {label}: days={len(sub)}  final_top3={top3:.1%}  "
            f"mark_match~{mark:.0f}%  win_prof~{wp:.0f}%  ex_prof~{ep:.0f}%"
        )
        weak = sub.sort_values("top3_final")
        _log("    弱い日 top3 final:")
        for _, r in weak.head(5).iterrows():
            _log(
                f"      {r['date']}: {r['top3_final']}/{r['top3_final_n']} "
                f"mark{r['mark_match_pct']}% "
                f"profW{r['win_prof_match_pct']}%/E{r['ex_prof_match_pct']}%"
            )


def _july_failure_slice(recs) -> None:
    st = DEFAULT_STRATEGY
    exotic = [r for r in recs if _exotic_high_for_record(r, st)]
    if not exotic:
        _log("  三連系購入レースなし")
        return
    report = _aggregate_records(recs, "20260701", "20260731", strategy=st)
    _log(
        f"  三連系購入 {report.sanrenpuku.races}R / "
        f"的中{report.sanrenpuku.hits} / ROI {report.sanrenpuku.roi:.1%}"
    )
    by_ex = Counter()
    hit_by_ex = Counter()
    for r in exotic:
        by_ex[r.exotic_profile] += 1
        if r.exotic_profile == KEN:
            hit = r.sanrenpuku_hit
        else:
            hit = r.sanrenpuku_formation_hit or r.sanrenpuku_box_hit
        if hit:
            hit_by_ex[r.exotic_profile] += 1
    for prof in (KEN, ARE):
        n = by_ex[prof]
        h = hit_by_ex[prof]
        if n:
            _log(f"    exotic={prof}: {n}R 的中{h} ({h/n:.1%})")
        else:
            _log(f"    exotic={prof}: 0R")

    high_miss = [r for r in recs if r.win_high and not r.win_hit][:12]
    if high_miss:
        _log("  単勝自信度高×外れ 例（最大12）:")
        for r in high_miss:
            _log(
                f"    {r.date} {r.race_no}R pred{r.pred_umaban}->{r.actual_1st} "
                f"{r.pred_horse} win{r.win_prob_top:.0%} gap{r.prob_gap:.0%} "
                f"W{r.win_profile}/E{r.exotic_profile}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="July 2026 logic review",
        epilog=(
            "例: .\\.venv\\Scripts\\python.exe scripts\\analyze_july2026.py --quick"
        ),
    )
    parser.add_argument(
        "--out-compare-csv",
        default=str(ROOT / "r_analysis" / "input" / "july2026_compare_summary.csv"),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="7月のみ集計（数十秒〜数分。まずこちら）",
    )
    parser.add_argument(
        "--include-2025",
        action="store_true",
        help="2025通年も比較する（時間がかかる）",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="予想スコアせず compare_report だけ集計（即時）",
    )
    args = parser.parse_args()

    _log(f"ROOT={ROOT}")
    _log(f"script={Path(__file__).resolve()}")
    _log("=== 2026/7 振り返り（split: style + sanrenpuku）===\n")

    july_recs: list = []
    if not args.skip_scoring:
        _log("master 読み込み中...")
        master = load_master()
        win_cfg, ex_cfg = load_split_scoring_configs()
        _log(f"master rows={len(master)}")

        if args.quick:
            periods = [("2026/7", "20260701", "20260731")]
            months = ("202607",)
        else:
            periods = [
                ("2026/1-3", "20260101", "20260331"),
                ("2026/4-5", "20260401", "20260531"),
                ("2026/6", "20260601", "20260630"),
                ("2026/7", "20260701", "20260731"),
                ("2026/1-7", "20260101", "20260731"),
            ]
            if args.include_2025:
                periods.append(("2025 通年", "20250101", "20251231"))
            months = (
                "202601",
                "202602",
                "202603",
                "202604",
                "202605",
                "202606",
                "202607",
            )

        _log("--- 期間別 ROI ---")
        period_cache: dict[tuple[str, str], tuple] = {}
        for label, start, end in periods:
            key = (start, end)
            if key not in period_cache:
                period_cache[key] = _load_period(master, win_cfg, ex_cfg, start, end)
            recs, n_race, n_pb = period_cache[key]
            s = _period_stats(recs, label)
            _print_row(s)
            if s["races"]:
                _log(f"    payback coverage {n_pb}/{n_race}")
            if label == "2026/7":
                july_recs = recs

        if not args.quick:
            _log("\n--- 2026 月別 三連ROI ---")
            for month in months:
                start, end = month + "01", month + "31"
                key = (start, end)
                if key not in period_cache:
                    period_cache[key] = _load_period(
                        master, win_cfg, ex_cfg, start, end
                    )
                recs, n_race, n_pb = period_cache[key]
                if not recs:
                    _log(f"  {month}: master なし")
                    continue
                s = _period_stats(recs, month)
                _log(
                    f"  {month}: {s['races']}R 三連ROI {s['sanren_roi']:.1%} "
                    f"単{s['win_roi']:.1%} ワ{s['wide_roi']:.1%} "
                    f"payback {n_pb}/{n_race}"
                )

        _log("\n--- 7月 詳細 ---")
        if july_recs:
            _july_failure_slice(july_recs)
        else:
            _log("  7月レコードなし（master / payback を確認）")
    else:
        _log("--skip-scoring: バックテスト集計をスキップ")

    _log("\n--- 当日スナップ比較（compare_report） ---")
    cmp_df = _parse_compare_summaries()
    _print_compare(cmp_df)
    if not cmp_df.empty:
        out = Path(args.out_compare_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmp_df.to_csv(out, index=False, encoding="utf-8")
        _log(f"\n  wrote {out}")

    _log(
        "\nヒント:\n"
        "  速い確認: .\\.venv\\Scripts\\python.exe scripts\\analyze_july2026.py --quick\n"
        "  比較のみ: .\\.venv\\Scripts\\python.exe scripts\\analyze_july2026.py --skip-scoring\n"
        "  R: source('r_analysis/scripts/10_july2026_review.R')"
    )


if __name__ == "__main__":
    main()
