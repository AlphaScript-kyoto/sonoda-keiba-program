"""
文字化けした raw CSV を検出し、netkeiba から再取得する。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.fetcher import fetch_day
from src.storage.csv_store import horses_csv_path, read_horses_csv


def _is_corrupt(path: Path) -> bool:
    if not path.exists():
        return False
    df = read_horses_csv(path)
    if df.empty or "horse_name" not in df.columns:
        return False
    names = df["horse_name"].fillna("").astype(str)
    return names.str.contains("\ufffd", regex=False).any()


def find_corrupt_dates(raw_dir: Path | None = None) -> list[str]:
    raw_dir = raw_dir or ROOT / "data" / "raw"
    dates: list[str] = []
    for path in sorted(raw_dir.glob("horses_*.csv")):
        if _is_corrupt(path):
            dates.append(path.stem.replace("horses_", ""))
    return dates


def main() -> None:
    parser = argparse.ArgumentParser(description="文字化け raw の再取得")
    parser.add_argument("--date", help="YYYYMMDD（省略時は自動検出）")
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()

    dates = [args.date] if args.date else find_corrupt_dates()
    if not dates:
        print("文字化けした raw CSV はありません。")
        return

    print(f"対象: {', '.join(dates)}")
    if args.list_only:
        return

    for date in dates:
        print(f"再取得: {date} ...", flush=True)
        result = fetch_day(date, save_csv=True, skip_existing=False)
        path = horses_csv_path(date)
        if _is_corrupt(path):
            print(f"  WARN: まだ文字化け ({path})", flush=True)
        else:
            print(f"  OK: {len(result.horse_rows)} 頭 -> {path}", flush=True)


if __name__ == "__main__":
    main()
