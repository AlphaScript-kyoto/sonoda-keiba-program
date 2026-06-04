"""raw CSV の着差（Excel 日付化）を修復して再保存する。文字化けは repair_raw_encoding.py を使う。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.csv_store import (
    normalize_margin_value,
    read_horses_csv,
    _prepare_horses_for_csv,
)


def repair_csv_files():
    raw_dir = Path("data/raw")
    for csv_file in raw_dir.glob("horses_*.csv"):
        print(f"修復中: {csv_file.name}")
        df = read_horses_csv(csv_file)
        if "margin" in df.columns:
            df["margin"] = df["margin"].map(normalize_margin_value)
        out = _prepare_horses_for_csv(df)
        out.to_csv(csv_file, index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    repair_csv_files()
    print("1000個のCSVの修復が完了しました！")