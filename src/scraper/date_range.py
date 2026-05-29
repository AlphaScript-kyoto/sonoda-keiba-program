"""取得期間の日付列挙。"""

from datetime import date, timedelta
from typing import Iterator, List


def parse_yyyymmdd(s: str) -> date:
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"日付は YYYYMMDD 形式で指定してください: {s}")
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def format_yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def iter_dates(date_from: str, date_to: str) -> Iterator[str]:
    """開始日～終了日（両端含む）を1日ずつ yield。"""
    start = parse_yyyymmdd(date_from)
    end = parse_yyyymmdd(date_to)
    if start > end:
        raise ValueError(f"DATE_FROM ({date_from}) が DATE_TO ({date_to}) より後です")

    current = start
    while current <= end:
        yield format_yyyymmdd(current)
        current += timedelta(days=1)


def list_dates(date_from: str, date_to: str) -> List[str]:
    return list(iter_dates(date_from, date_to))
