"""raw / master データの概要を精査して表示する。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from config.settings import DATA_RAW_DIR, HORSES_MASTER_PATH
from src.storage.csv_store import HORSE_COLUMN_LABELS, read_horses_csv


def main() -> None:
    paths = sorted(DATA_RAW_DIR.glob("horses_*.csv"))
    print("=== raw CSV ===")
    print(f"ファイル数: {len(paths):,}")
    if paths:
        print(f"期間: {paths[0].stem[7:]} ～ {paths[-1].stem[7:]}")

    frames = [read_horses_csv(p) for p in paths]
    raw = pd.concat(frames, ignore_index=True)
    raw["finish_num"] = pd.to_numeric(raw["finish"], errors="coerce")

    print(f"総行数: {len(raw):,}")
    print(f"ユニークレース: {raw['race_id'].nunique():,}")
    print(f"ユニーク馬: {raw['horse_id'].replace('', pd.NA).dropna().nunique():,}")
    print(f"重複 (race_id+horse_id): {raw.duplicated(subset=['race_id', 'horse_id']).sum():,}")

    header = pd.read_csv(paths[0], dtype=str, nrows=0)
    ja_ok = header.columns[0] == HORSE_COLUMN_LABELS["race_id"]
    print(f"日本語ヘッダー: {'OK' if ja_ok else 'NG'}")

    for col in ("horse_id", "margin", "weather", "race_class"):
        empty = raw[col].fillna("").astype(str).str.strip().eq("").sum()
        print(f"  空列 {col}: {empty:,}")

    dup_races = raw.groupby("race_id").size()
    print(f"1レースあたり頭数: min={dup_races.min()}, max={dup_races.max()}, median={dup_races.median():.0f}")

    print("\n=== master CSV ===")
    if not HORSES_MASTER_PATH.exists():
        print("未生成 — python scripts/build_features.py を実行してください")
        return

    master = pd.read_csv(HORSES_MASTER_PATH, dtype=str)
    print(f"パス: {HORSES_MASTER_PATH}")
    print(f"行数: {len(master):,} / 列数: {len(master.columns)}")
    feature_cols = [
        "days_since_last",
        "last3_avg_finish",
        "last5_avg_finish",
        "horse_win_rate",
        "horse_win_rate_distance",
        "horse_win_rate_track",
        "jockey_win_rate",
    ]
    for col in feature_cols:
        if col in master.columns:
            filled = master[col].fillna("").astype(str).str.strip().ne("").sum()
            print(f"  {col} あり: {filled:,} ({filled / len(master) * 100:.1f}%)")

    print("\n=== 年別開催行数 ===")
    raw["year"] = raw["date"].astype(str).str[:4]
    yearly = raw.groupby("year").size()
    for year, count in yearly.items():
        print(f"  {year}: {count:,}")


if __name__ == "__main__":
    main()
