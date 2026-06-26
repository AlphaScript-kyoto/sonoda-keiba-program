"""日付・期間単位のレース取得オーケストレーション。"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

import requests

from src.scraper.client import NetkeibaBlockedError, fetch_race_result_html
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
    failed: bool = False
    error: str | None = None


@dataclass
class RangeFetchResult:
    days: List[DayFetchResult] = field(default_factory=list)
    stopped: bool = False
    stop_reason: str | None = None

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


def _race_ids_from_schedule(date_yyyymmdd: str) -> List[str]:
    from src.scraper.race_snapshots import load_schedule

    schedule = load_schedule(date_yyyymmdd)
    if not schedule:
        return []
    ids: List[str] = []
    for race in schedule.get("races", []):
        rid = str(race.get("race_id", "")).strip()
        if rid:
            ids.append(rid)
    return sorted(set(ids))


def resolve_race_ids_for_fetch(date_yyyymmdd: str) -> List[str]:
    """
    取得対象 race_id 一覧。

    当日 schedule.json があれば開催全Rを必ず含める（1Rページのリンクが
    途中経過で欠けていても全件取得できるようにする）。
    """
    schedule_ids = _race_ids_from_schedule(date_yyyymmdd)
    listed_ids = list_race_ids_for_date(date_yyyymmdd)
    merged = sorted(set(schedule_ids) | set(listed_ids))
    return merged if merged else listed_ids


def _fetch_race_result_rows(race_id: str) -> List[Dict[str, Any]]:
    html = fetch_race_result_html(race_id)
    return parse_race_result(html, race_id)


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

    race_ids = resolve_race_ids_for_fetch(date_yyyymmdd)

    if not race_ids:
        result.skipped = True
        return result

    result.race_ids = race_ids
    all_rows: List[Dict[str, Any]] = []
    fetched_ids: Set[str] = set()

    def _pull(ids: List[str]) -> None:
        for race_id in ids:
            try:
                rows = _fetch_race_result_rows(race_id)
            except NetkeibaBlockedError:
                raise
            except requests.RequestException as exc:
                print(f"  WARN: {race_id} 取得失敗 ({exc})", flush=True)
                continue
            if rows:
                all_rows.extend(rows)
                fetched_ids.add(str(race_id))

    _pull(race_ids)
    missing = [rid for rid in race_ids if rid not in fetched_ids]
    if missing:
        print(
            f"  WARN: {len(missing)}R 未取得のため再試行: {missing}",
            flush=True,
        )
        time.sleep(3)
        _pull(missing)

    missing_after = [rid for rid in race_ids if rid not in fetched_ids]
    if missing_after:
        print(
            f"  WARN: 再試行後も未取得 {len(missing_after)}R: {missing_after}",
            flush=True,
        )

    result.horse_rows = all_rows

    if save_csv and all_rows:
        path = append_horses_csv(all_rows, date_yyyymmdd)
        result.csv_path = str(path)

    return result


def fetch_races_to_master(race_ids: List[str]) -> List[str]:
    """指定レースの結果を取得し、日次CSVと horses_master.csv を更新する。"""
    import pandas as pd

    from config.settings import HORSES_MASTER_PATH

    fetched: List[str] = []
    by_date: Dict[str, List[Dict[str, Any]]] = {}

    for race_id in race_ids:
        rid = str(race_id)
        try:
            html = fetch_race_result_html(rid)
        except NetkeibaBlockedError:
            raise
        except requests.RequestException:
            continue
        rows = parse_race_result(html, rid)
        if not rows:
            continue
        fetched.append(rid)
        day = str(rows[0].get("date", "") or rid[6:14])
        by_date.setdefault(day, []).extend(rows)

    if not fetched:
        return []

    for day, rows in by_date.items():
        append_horses_csv(rows, day)

    if HORSES_MASTER_PATH.exists():
        master = pd.read_csv(HORSES_MASTER_PATH, dtype=str)
        master = master[~master["race_id"].astype(str).isin(fetched)]
        master = pd.concat([master, pd.DataFrame(sum(by_date.values(), []))], ignore_index=True)
        master.to_csv(HORSES_MASTER_PATH, index=False, encoding="utf-8-sig")

    return fetched


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
        try:
            day_result = fetch_day(day, save_csv=save_csv, skip_existing=skip_existing)
        except NetkeibaBlockedError as exc:
            day_result = DayFetchResult(date=day, failed=True, error=str(exc))
            out.days.append(day_result)
            out.stopped = True
            out.stop_reason = str(exc)
            if log_progress:
                print(f"  STOP: HTTP 400 を検知 — 自動停止 ({exc})", flush=True)
                print("  24時間程度空けてから再開してください。", flush=True)
            break
        except requests.RequestException as exc:
            day_result = DayFetchResult(date=day, failed=True, error=str(exc))
        out.days.append(day_result)

        if log_progress:
            if day_result.failed:
                print(f"  ERROR: 取得失敗 ({day_result.error})", flush=True)
            elif day_result.resumed:
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
        if out.stopped:
            print(f"\n中断: 通信制限の可能性 ({out.stop_reason})", flush=True)
        else:
            print(
                f"\n完了: 開催 {out.active_days}日, "
                f"スキップ {out.skipped_days}日, "
                f"計 {out.total_races}R / {out.total_horses}頭",
                flush=True,
            )

    return out
