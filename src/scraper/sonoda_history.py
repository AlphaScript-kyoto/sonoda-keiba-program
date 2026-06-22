"""園田競馬の開催日探索。"""

from datetime import date, timedelta
from typing import Optional

from src.scraper.client import fetch_race_result_html
from src.scraper.parser import has_result_table
from src.scraper.race_id import build_race_id
from src.scraper.race_list import list_race_ids_for_shutuba

SEARCH_START = date(1995, 1, 1)


def _yyyymmdd_to_date(ymd: str) -> date:
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))


def next_sonoda_date_in_master(
    from_yyyymmdd: str,
    master=None,
) -> Optional[str]:
    """master の開催日一覧から、指定日より後の最初の園田開催日。"""
    if master is None:
        from src.predictor.score import load_master

        master = load_master()
    dates = sorted(master["date"].astype(str).unique())
    for d in dates:
        if d > from_yyyymmdd:
            return d
    return None


def find_next_sonoda_race_date_after(
    from_yyyymmdd: str,
    *,
    max_days: int = 60,
    master=None,
) -> Optional[str]:
    """指定日より後の次回園田開催日（master → 出馬表の順で探索）。"""
    nxt = next_sonoda_date_in_master(from_yyyymmdd, master)
    if nxt:
        return nxt

    start = _yyyymmdd_to_date(from_yyyymmdd)
    for offset in range(1, max_days + 1):
        ymd = (start + timedelta(days=offset)).strftime("%Y%m%d")
        try:
            if list_race_ids_for_shutuba(ymd):
                return ymd
        except Exception:
            continue
    return None


def date_has_sonoda_races(date_yyyymmdd: str) -> bool:
    """指定日に園田1Rの結果があるか。"""
    rid = build_race_id(date_yyyymmdd, 1)
    try:
        html = fetch_race_result_html(rid)
        return has_result_table(html)
    except Exception:
        return False


def find_earliest_sonoda_date(
    end_yyyymmdd: str,
    start: Optional[date] = None,
) -> Optional[str]:
    """
    終了日以前で最も古い園田開催日を返す。

    開催が連続しないため、年→日の順で線形探索する。
    """
    end_d = date(
        int(end_yyyymmdd[:4]),
        int(end_yyyymmdd[4:6]),
        int(end_yyyymmdd[6:8]),
    )
    lo = start or SEARCH_START

    if not date_has_sonoda_races(end_yyyymmdd):
        return None

    # 最初に開催があった年を特定（各年の代表日を数点チェック）
    first_year: Optional[int] = None
    for year in range(lo.year, end_d.year + 1):
        samples = [f"{year}{m:02d}15" for m in (1, 4, 7, 10)]
        if any(date_has_sonoda_races(d) for d in samples):
            first_year = year
            break

    if first_year is None:
        return None

    # その年の1月1日から日単位で最古日を探す
    scan_start = date(first_year, 1, 1)
    current = scan_start
    earliest: Optional[str] = None

    while current <= end_d:
        ymd = current.strftime("%Y%m%d")
        if date_has_sonoda_races(ymd):
            earliest = ymd
            break
        current += timedelta(days=1)

    return earliest
