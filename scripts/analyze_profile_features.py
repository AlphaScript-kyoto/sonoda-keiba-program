"""堅/荒レースの事前特徴量比較（オッズ以外の共通点を洗い出す）。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import assign_marks, detect_race_profile, is_high_confidence
from src.predictor.score import load_master, predict_date
from src.scraper.payback import load_payback_cache


def _int_val(series, default=0):
    v = pd.to_numeric(series.iloc[0], errors="coerce")
    return int(v) if pd.notna(v) else default


def build_features(master: pd.DataFrame, race_ids: list[str]) -> pd.DataFrame:
    cache = load_payback_cache()
    rows = []
    scored_cache: dict[str, pd.DataFrame] = {}

    for rid in race_ids:
        if rid not in cache:
            continue
        grp = master[master["race_id"].astype(str) == rid]
        if grp.empty:
            continue
        finish = grp.copy()
        finish["fn"] = pd.to_numeric(finish["finish"], errors="coerce")
        finish = finish.dropna(subset=["fn"]).sort_values("fn")
        if len(finish) < 3:
            continue

        date = str(grp["date"].iloc[0])
        if date not in scored_cache:
            scored_cache[date] = predict_date(date, master=master, fetch_entries=False)
        scored = scored_cache[date]
        pred = scored[scored["race_id"].astype(str) == rid]
        if pred.empty:
            continue

        _, p1, gap = is_high_confidence(pred)
        profile, fav, upset_score = detect_race_profile(pred, p1, gap)
        top5 = assign_marks(pred)
        top5_set = {str(u) for u in top5["umaban"]}
        winner = str(finish.iloc[0]["umaban"])
        w_pop = int(pd.to_numeric(finish.iloc[0]["popularity"], errors="coerce") or 99)

        odds = pd.to_numeric(grp["odds"], errors="coerce").dropna()
        probs = pred.sort_values("rank_pred")["win_prob"].astype(float)
        pb = cache[rid]

        rows.append(
            {
                "race_id": rid,
                "profile": profile,
                "fav_odds": fav,
                "upset_score": upset_score,
                "prob_gap": gap,
                "win_prob_top": p1,
                "top3_prob_sum": float(probs.head(3).sum()),
                "head_count": _int_val(grp["head_count"], len(grp)),
                "distance": _int_val(grp["distance"]),
                "race_class": str(grp["race_class"].iloc[0]),
                "odds_spread": float(odds.max() / odds.min()) if len(odds) >= 2 and odds.min() > 0 else 0,
                "odds_std": float(odds.std()) if len(odds) >= 2 else 0,
                "fuku3_yen": int(pb.get("fuku3_yen", 0)),
                "winner_in_top5": winner in top5_set,
                "long_winner": w_pop >= 6,
            }
        )

    return pd.DataFrame(rows)


def _compare(df: pd.DataFrame, col: str) -> None:
    firm = df[df["profile"] == "堅"]
    upset = df[df["profile"] == "荒"]
    if firm.empty or upset.empty:
        return
    print(
        f"  {col:18} 堅={firm[col].mean():8.2f}  荒={upset[col].mean():8.2f}  "
        f"差={upset[col].mean() - firm[col].mean():+.2f}"
    )


def main() -> None:
    master = load_master()
    cache = load_payback_cache()
    df = build_features(master, sorted(cache.keys()))
    if df.empty:
        print("分析対象なし")
        return

    print(f"分析: {len(df)}R  堅={len(df[df.profile=='堅'])}  荒={len(df[df.profile=='荒'])}")

    print("\n=== 堅 vs 荒（事前指標） ===")
    for col in [
        "fav_odds", "prob_gap", "win_prob_top", "top3_prob_sum",
        "head_count", "distance", "odds_spread", "odds_std", "upset_score",
    ]:
        _compare(df, col)

    print("\n=== クラス別 ===")
    for cls, sub in df.groupby("race_class"):
        if len(sub) < 20:
            continue
        print(
            f"  {cls:12} n={len(sub):4}  荒率={(sub.profile=='荒').mean()*100:4.1f}%  "
            f"top5外={(~sub.winner_in_top5).mean()*100:.1f}%  三複med={sub.fuku3_yen.median():.0f}"
        )

    print("\n=== 距離帯 ===")
    bins = [0, 1400, 1700, 2000, 9999]
    labels = ["~1400", "1401-1700", "1701-2000", "2001~"]
    df["dist_band"] = pd.cut(df["distance"], bins=bins, labels=labels)
    for band, sub in df.groupby("dist_band", observed=True):
        if len(sub) < 15:
            continue
        print(
            f"  {band:12} n={len(sub):4}  荒率={(sub.profile=='荒').mean()*100:4.1f}%  "
            f"top5外={(~sub.winner_in_top5).mean()*100:.1f}%"
        )

    upset = df[df["profile"] == "荒"]
    firm = df[df["profile"] == "堅"]
    print("\n=== 結果 ===")
    print(f"  top5外勝ち: 荒={(~upset.winner_in_top5).mean()*100:.1f}%  堅={(~firm.winner_in_top5).mean()*100:.1f}%")
    print(f"  6番人気以下勝ち: 荒={upset.long_winner.mean()*100:.1f}%  堅={firm.long_winner.mean()*100:.1f}%")

    print("\n=== シグナル別 ===")
    for label, sub in [
        ("fav>=3.0", df[df.fav_odds >= 3.0]),
        ("fav<2.0", df[df.fav_odds < 2.0]),
        ("gap<=0.65", df[df.prob_gap <= 0.65]),
        ("top3prob<1.05", df[df.top3_prob_sum < 1.05]),
        ("spread>=15", df[df.odds_spread >= 15]),
        ("head>=12", df[df.head_count >= 12]),
    ]:
        if len(sub) < 10:
            continue
        print(
            f"  {label:16} n={len(sub):4}  荒率={(sub.profile=='荒').mean()*100:4.1f}%  "
            f"top5外={(~sub.winner_in_top5).mean()*100:.1f}%  三複med={sub.fuku3_yen.median():.0f}"
        )


if __name__ == "__main__":
    main()
