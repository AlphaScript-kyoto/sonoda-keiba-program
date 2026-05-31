"""デイリー取得: 指定日（既定=今日）の園田レース結果を CSV 保存し、マスタを更新する。"""
import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.features.build_features import build_and_save_all
from src.scraper.client import NetkeibaBlockedError
from src.scraper.fetcher import fetch_day


def main() -> None:
    parser = argparse.ArgumentParser(
        description="園田競馬のレース結果を1日分取得（デイリー運用向け）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 今日の結果を取得 → マスタ更新（デイリー定番）
  python scripts/fetch_daily.py

  # 日付指定
  python scripts/fetch_daily.py --date 20260529

  # マスタ更新をスキップ
  python scripts/fetch_daily.py --no-update-master
        """,
    )
    parser.add_argument(
        "--date",
        help="取得日 YYYYMMDD（省略時は今日）",
    )
    parser.add_argument(
        "--no-update-master",
        action="store_true",
        help="取得後の horses_master.csv 再生成をスキップ",
    )
    args = parser.parse_args()

    target = args.date or date.today().strftime("%Y%m%d")
    print(f"=== デイリー取得: {target} 園田 ===")

    try:
        result = fetch_day(target, save_csv=True, skip_existing=False)
    except NetkeibaBlockedError as exc:
        print(f"STOP: HTTP 400 — 通信制限の可能性 ({exc})")
        print("24時間程度空けてから再試行してください。")
        sys.exit(1)

    if result.skipped:
        print("開催なし（園田のレース結果なし）")
        sys.exit(0)

    print(f"レース数: {len(result.race_ids)}")
    print(f"出走馬: {len(result.horse_rows)} 行")
    if result.csv_path:
        print(f"保存: {result.csv_path}")

    if not args.no_update_master:
        print("\nマスタ CSV 更新中...")
        features_path, master_path = build_and_save_all()
        print(f"  features: {features_path}")
        print(f"  master:   {master_path}")


if __name__ == "__main__":
    main()
