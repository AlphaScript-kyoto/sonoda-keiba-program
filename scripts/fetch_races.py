"""レースデータ取得スクリプト。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import scrape_range
from src.scraper.client import build_result_url, fetch_race_result_html
from src.scraper.fetcher import fetch_day, fetch_range
from src.scraper.parser import parse_race_result
from src.storage.csv_store import append_horses_csv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="園田競馬レース結果を netkeiba から取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 1日分（2026/05/22 園田開催）
  python scripts/fetch_races.py --date 20260522 --save

  # config/scrape_range.py の期間を使う
  python scripts/fetch_races.py --save

  # 期間をCLIで指定
  python scripts/fetch_races.py --from 20260520 --to 20260522 --save
        """,
    )
    parser.add_argument("--date", help="取得する1日 YYYYMMDD")
    parser.add_argument("--from", dest="date_from", help="取得開始日 YYYYMMDD")
    parser.add_argument("--to", dest="date_to", help="取得終了日 YYYYMMDD")
    parser.add_argument("--race-id", help="単一レースのみ取得")
    parser.add_argument(
        "--save",
        action="store_true",
        help="CSV に保存する",
    )
    args = parser.parse_args()

    if args.race_id:
        _fetch_single_race(args.race_id, args.date, args.save)
        return

    if args.date:
        date_from = date_to = args.date
    else:
        date_from = args.date_from or scrape_range.DATE_FROM
        date_to = args.date_to or scrape_range.DATE_TO

    if date_from == date_to:
        _fetch_one_day(date_from, args.save)
    else:
        _fetch_period(date_from, date_to, args.save)


def _fetch_single_race(race_id: str, date: str | None, save: bool) -> None:
    csv_date = date or race_id[:4] + race_id[6:10]
    url = build_result_url(race_id)
    print(f"取得: {url}")
    html = fetch_race_result_html(race_id)
    rows = parse_race_result(html, race_id)
    print(f"パース結果: {len(rows)} 頭")
    if save and rows:
        path = append_horses_csv(rows, csv_date)
        print(f"保存: {path}")
    elif rows:
        for row in rows[:3]:
            print(row)
        if len(rows) > 3:
            print("...")


def _fetch_one_day(date_yyyymmdd: str, save: bool) -> None:
    print(f"=== {date_yyyymmdd} 園田 ===")
    result = fetch_day(date_yyyymmdd, save_csv=save)
    if result.skipped:
        print("開催なし（結果テーブルなし）")
        return
    print(f"レース数: {len(result.race_ids)}")
    print(f"出走馬データ: {len(result.horse_rows)} 行")
    if result.csv_path:
        print(f"保存: {result.csv_path}")


def _fetch_period(date_from: str, date_to: str, save: bool) -> None:
    from config.settings import (
        REQUEST_INTERVAL_MAX_SEC,
        REQUEST_INTERVAL_MIN_SEC,
        REQUEST_MAX_PER_HOUR,
    )

    print(f"=== 期間 {date_from} ～ {date_to} ===")
    print(
        f"待機: {REQUEST_INTERVAL_MIN_SEC}～{REQUEST_INTERVAL_MAX_SEC} 秒/リクエスト, "
        f"上限 {REQUEST_MAX_PER_HOUR}/時間（config/settings.py）"
    )
    fetch_range(date_from, date_to, save_csv=save, skip_existing=True, log_progress=True)


if __name__ == "__main__":
    main()
