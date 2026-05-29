"""日付・期間単位のレース取得オーケストレーション。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.scraper.client import fetch_race_result_html
from src.scraper.date_range import iter_dates, list_dates
from src.scraper.parser import parse_race_result
from src.scraper.race_list import list_race_ids_for_date
from src.storage.csv_store import (
    append_horses_csv,
    csv_has_required_columns,
    horses_csv_path,
)


@dataclass
class DayFetchResult:
    date: str
    race_ids: List[str] = field(default_factory=list)
    horse_rows: List[Dict[str, Any]] = field(default_factory=list)
    csv_path: str | None = None
    skipped: bool = False
    resumed: bool = False


@dataclass
class RangeFetchResult:
    days: List[DayFetchResult] = field(default_factory=list)

    @property
    def total_races(self) -> int:
        return sum(len(d.race_ids) for d in self.days)

    @property
    def total_horses(self) -> int:
        return sum(len(d.horse_rows) for d in self.days)

    @property
    def active_days(self) -> int:
        return sum(1 for d in self.days if d.race_ids)

    @property
    def skipped_days(self) -> int:
        return sum(1 for d in self.days if d.skipped and not d.resumed)


def fetch_day(
    date_yyyymmdd: str,
    *,
    save_csv: bool = True,
    skip_existing: bool = False,
) -> DayFetchResult:
    """指定1日分の園田レース結果を取得する。"""
    result = DayFetchResult(date=date_yyyymmdd)
    csv_path = horses_csv_path(date_yyyymmdd)

    if skip_existing and csv_has_required_columns(csv_path):
        result.resumed = True
        result.csv_path = str(csv_path)
        return result

    race_ids = list_race_ids_for_date(date_yyyymmdd)

    if not race_ids:
        result.skipped = True
        return result

    result.race_ids = race_ids
    all_rows: List[Dict[str, Any]] = []

    for race_id in race_ids:
        html = fetch_race_result_html(race_id)
        rows = parse_race_result(html, race_id)
        all_rows.extend(rows)

    result.horse_rows = all_rows

    if save_csv and all_rows:
        path = append_horses_csv(all_rows, date_yyyymmdd)
        result.csv_path = str(path)

    return result


def fetch_range(
    date_from: str,
    date_to: str,
    *,
    save_csv: bool = True,
    skip_existing: bool = True,
    log_progress: bool = True,
) -> RangeFetchResult:
    """期間内の各日を順に取得する（1日ごとに間隔を空けてアクセス）。"""
    out = RangeFetchResult()
    days = list_dates(date_from, date_to)
    total = len(days)

    for i, day in enumerate(days, start=1):
        if log_progress:
            print(f"[{i}/{total}] {day} ...", flush=True)
        day_result = fetch_day(day, save_csv=save_csv, skip_existing=skip_existing)
        out.days.append(day_result)

        if log_progress:
            if day_result.resumed:
                print(f"  skip (既存 CSV)", flush=True)
            elif day_result.skipped:
                print(f"  skip (園田開催なし)", flush=True)
            else:
                print(
                    f"  OK: {len(day_result.race_ids)}R, "
                    f"{len(day_result.horse_rows)}頭 -> {day_result.csv_path}",
                    flush=True,
                )

    if log_progress:
        print(
            f"\n完了: 開催 {out.active_days}日, "
            f"スキップ {out.skipped_days}日, "
            f"計 {out.total_races}R / {out.total_horses}頭",
            flush=True,
        )

    return out
