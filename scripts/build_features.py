"""特徴量 CSV を生成する。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import HORSES_MASTER_PATH
from src.features.build_features import build_and_save_all, load_raw_horses


def main() -> None:
    print("生データ読み込み...")
    raw = load_raw_horses()
    print(f"  {len(raw):,} 行")

    print("特徴量計算 & マスタ保存...")
    features_path, master_path = build_and_save_all()
    print(f"保存: {features_path}")
    print(f"マスタ: {master_path}")
    import pandas as pd
    df = pd.read_csv(master_path, dtype=str)
    print(f"  {len(df):,} 行 × {len(df.columns)} 列")

    sample = df[
        ["date", "horse_name", "finish", "days_since_last", "last3_avg_finish", "horse_win_rate"]
    ].dropna(subset=["horse_win_rate"]).tail(3)
    print("\nサンプル（直近・勝率あり）:")
    print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
