"""高配当・穴馬レースの特徴分析。"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import (
    DEFAULT_THRESHOLDS,
    assign_marks,
    build_sanrenpuku_nagashi,
    check_sanrenpuku_hit,
    is_high_confidence,
)
from src.predictor.score import load_master, predict_date
from src.scraper.payback import load_payback_cache, payback_from_dict


def _finish_top3(grp: pd.DataFrame) -> pd.DataFrame:
    out = grp.copy()
    out["finish_num"] = pd.to_numeric(out["finish"], errors="coerce")
    return out.dropna(subset=["finish_num"]).sort_values("finish_num").head(3)


def build_race_table(master: pd.DataFrame, race_ids: list[str]) -> pd.DataFrame:
    cache = load_payback_cache()
    rows = []
    scored_cache: dict[str, pd.DataFrame] = {}
    for rid in race_ids:
        if rid not in cache:
            continue
        pb = payback_from_dict({**cache[rid], "race_id": rid})
        grp = master[master["race_id"].astype(str) == rid]
        if grp.empty:
            continue
        top3 = _finish_top3(grp)
        if len(top3) < 3:
            continue

        w = top3.iloc[0]
        w_odds = float(pd.to_numeric(w["odds"], errors="coerce") or 0)
        w_pop = int(pd.to_numeric(w["popularity"], errors="coerce") or 99)
        odds_all = pd.to_numeric(grp["odds"], errors="coerce")
        date = str(grp["date"].iloc[0])

        if date not in scored_cache:
            scored_cache[date] = predict_date(date, master=master, fetch_entries=False)
        scored = scored_cache[date]
        pred_grp = scored[scored["race_id"].astype(str) == rid] if not scored.empty else pd.DataFrame()
        high, p1, gap = False, 0.0, 0.0
        pred_u, sp_hit, in_top5 = "", None, False
        if not pred_grp.empty:
            top5 = assign_marks(pred_grp)
            pred_u = str(top5.iloc[0]["umaban"])
            in_top5 = str(w["umaban"]) in {str(u) for u in top5["umaban"]}
            high, p1, gap = is_high_confidence(pred_grp, DEFAULT_THRESHOLDS)
            actual = [str(u) for u in top3["umaban"]]
            nag = build_sanrenpuku_nagashi(top5)
            sp_hit = check_sanrenpuku_hit(nag, actual) if nag else False

        top3_pops = [
            int(pd.to_numeric(r["popularity"], errors="coerce") or 99) for _, r in top3.iterrows()
        ]
        top3_odds = [
            float(pd.to_numeric(r["odds"], errors="coerce") or 0) for _, r in top3.iterrows()
        ]

        def _int_val(series, default=0):
            v = pd.to_numeric(series.iloc[0], errors="coerce")
            return int(v) if pd.notna(v) else default

        rows.append(
            {
                "race_id": rid,
                "date": date,
                "race_no": int(grp["race_no"].iloc[0]),
                "race_name": str(grp["race_name"].iloc[0]),
                "fuku3_yen": pb.fuku3_yen,
                "tan3_yen": pb.tan3_yen,
                "win_odds": w_odds,
                "win_pop": w_pop,
                "fav_odds": float(odds_all.min()),
                "max_odds": float(odds_all.max()),
                "head_count": _int_val(grp["head_count"], len(grp)),
                "distance": _int_val(grp["distance"]),
                "track": str(grp["track"].iloc[0]),
                "surface": str(grp["surface"].iloc[0]),
                "race_class": str(grp["race_class"].iloc[0]),
                "win_style": str(w.get("running_style", "")),
                "long_in_top3": sum(1 for p in top3_pops if p >= 6),
                "top3_pop_sum": sum(top3_pops),
                "top3_odds_prod": float(np.prod(top3_odds)) if all(o > 0 for o in top3_odds) else 0.0,
                "high_conf": high,
                "win_prob_top": p1,
                "prob_gap": gap,
                "pred_hit": str(w["umaban"]) == pred_u if pred_u else False,
                "winner_in_top5": in_top5,
                "sanren_hit": sp_hit,
                "pred_umaban": pred_u,
            }
        )
    return pd.DataFrame(rows)


def _compare(hi: pd.DataFrame, lo: pd.DataFrame) -> None:
    cols = [
        "win_odds",
        "win_pop",
        "fav_odds",
        "head_count",
        "long_in_top3",
        "top3_pop_sum",
        "win_prob_top",
        "prob_gap",
    ]
    print("\n=== 三連複高配当(上位20%) vs 低配当(下位50%) ===")
    for c in cols:
        print(f"  {c:16} 高配当={hi[c].mean():.2f}  低配当={lo[c].mean():.2f}")
    print(f"  1番人気勝率         高配当={(hi['win_pop']==1).mean()*100:.1f}%  低配当={(lo['win_pop']==1).mean()*100:.1f}%")
    print(f"  予想◎的中          高配当={hi['pred_hit'].mean()*100:.1f}%  低配当={lo['pred_hit'].mean()*100:.1f}%")
    print(f"  top5に勝ち馬        高配当={hi['winner_in_top5'].mean()*100:.1f}%  低配当={lo['winner_in_top5'].mean()*100:.1f}%")
    print(f"  三連複的中(現戦略)  高配当={hi['sanren_hit'].mean()*100:.1f}%  低配当={lo['sanren_hit'].mean()*100:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="高配当レース分析")
    parser.add_argument("--top", type=int, default=10, help="TOP N 表示件数")
    args = parser.parse_args()

    cache = load_payback_cache()
    race_ids = sorted(cache.keys())
    master = load_master()
    df = build_race_table(master, race_ids)
    if df.empty:
        print("払戻キャッシュに分析対象レースがありません")
        return

    print(f"分析対象: {len(df)}レース (payback cache)")
    for col in ["fuku3_yen", "tan3_yen", "win_odds"]:
        q = df[col].quantile([0.5, 0.75, 0.9, 0.95])
        print(f"  {col}: median={q[0.5]:.0f} p75={q[0.75]:.0f} p90={q[0.9]:.0f} p95={q[0.95]:.0f}")

    thr = df["fuku3_yen"].quantile(0.80)
    hi = df[df["fuku3_yen"] >= thr]
    lo = df[df["fuku3_yen"] < df["fuku3_yen"].quantile(0.50)]
    _compare(hi, lo)

    miss = df[(df["high_conf"]) & (~df["sanren_hit"]) & (df["fuku3_yen"] >= thr)]
    print(f"\n=== 自信度高 × 三連複外し × 高配当: {len(miss)}R ===")
    if not miss.empty:
        cols = ["date", "race_no", "race_name", "fuku3_yen", "win_odds", "win_pop", "long_in_top3"]
        print(miss.nlargest(args.top, "fuku3_yen")[cols].to_string(index=False))

    print("\n=== 予測前シグナル ===")
    for label, sub in [
        ("prob_gap<=0.65 (混戦)", df[df["prob_gap"] <= 0.65]),
        ("prob_gap>=0.75 (本命堅)", df[df["prob_gap"] >= 0.75]),
        ("head>=13", df[df["head_count"] >= 13]),
        ("head<=10", df[df["head_count"] <= 10]),
        ("fav_odds>=3.0 (本命薄", df[df["fav_odds"] >= 3.0]),
    ]:
        if sub.empty:
            continue
        print(
            f"  {label:22} n={len(sub):3}  fuku3_med={sub['fuku3_yen'].median():6.0f}  "
            f"高配当率={(sub['fuku3_yen']>=thr).mean()*100:4.1f}%  "
            f"sanren_hit={sub['sanren_hit'].mean()*100:4.1f}%"
        )

    print(f"\n=== 三連複払戻 TOP{args.top} ===")
    cols = [
        "date", "race_no", "race_name", "fuku3_yen", "tan3_yen",
        "win_odds", "win_pop", "head_count", "high_conf", "sanren_hit", "winner_in_top5",
    ]
    print(df.nlargest(args.top, "fuku3_yen")[cols].to_string(index=False))

    # 穴馬(6番人気以下)が絡む高配当
    upset_hi = df[(df["long_in_top3"] >= 1) & (df["fuku3_yen"] >= thr)]
    print(f"\n=== 6番人気以下が3着内 × 高配当: {len(upset_hi)}R (全体の{len(upset_hi)/len(df)*100:.1f}%) ===")
    if not upset_hi.empty:
        print(f"  平均三連複={upset_hi['fuku3_yen'].mean():.0f}円  現戦略的中率={upset_hi['sanren_hit'].mean()*100:.1f}%")
        print(f"  top5外勝ち馬={ (~upset_hi['winner_in_top5']).mean()*100:.1f}%")


if __name__ == "__main__":
    main()
