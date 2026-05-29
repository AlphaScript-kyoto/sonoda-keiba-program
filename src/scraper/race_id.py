"""netkeiba 園田 race_id の組み立て・分解。"""

import re
from typing import Optional

from config.settings import JYO_CD

# 例: 202650052201 = 2026年 + 園田(50) + 05月22日 + 1R
RACE_ID_PATTERN = re.compile(
    rf"^(?P<year>\d{{4}}){JYO_CD}(?P<mmdd>\d{{4}})(?P<race_no>\d{{2}})$"
)
MAX_RACE_NO = 15


def date_to_mmdd(date_yyyymmdd: str) -> str:
    """YYYYMMDD → MMDD（race_id 用）。"""
    if len(date_yyyymmdd) != 8 or not date_yyyymmdd.isdigit():
        raise ValueError(f"日付は YYYYMMDD 形式で指定してください: {date_yyyymmdd}")
    return date_yyyymmdd[4:8]


def build_race_id(date_yyyymmdd: str, race_no: int) -> str:
    """園田の race_id を生成する。"""
    year = date_yyyymmdd[:4]
    mmdd = date_to_mmdd(date_yyyymmdd)
    return f"{year}{JYO_CD}{mmdd}{race_no:02d}"


def parse_race_id(race_id: str) -> Optional[dict]:
    """race_id を年・日付・R番に分解。園田以外は None。"""
    m = RACE_ID_PATTERN.match(race_id)
    if not m:
        return None
    mmdd = m.group("mmdd")
    year = m.group("year")
    return {
        "race_id": race_id,
        "date": f"{year}{mmdd}",
        "race_no": int(m.group("race_no")),
    }


def race_id_prefix_for_date(date_yyyymmdd: str) -> str:
    """指定日の園田 race_id プレフィックス（末尾2桁以外）。"""
    return build_race_id(date_yyyymmdd, 0)[:-2]
