"""開催日・レース一覧の取得。"""

import re
from typing import List

from config.settings import JYO_CD
from src.scraper.client import fetch_race_result_html
from src.scraper.parser import has_result_table
from src.scraper.race_id import MAX_RACE_NO, build_race_id, race_id_prefix_for_date
from src.scraper.shutuba import fetch_shutuba_html, has_shutuba_table

_RACE_LINK_RE = re.compile(rf"\?race_id=(\d{{12}})")


def list_race_ids_from_html(html: str, date_yyyymmdd: str) -> List[str]:
    """結果ページ HTML 内の園田レースリンクから race_id 一覧を抽出。"""
    prefix = race_id_prefix_for_date(date_yyyymmdd)
    ids = []
    for rid in _RACE_LINK_RE.findall(html):
        if rid.startswith(prefix):
            ids.append(rid)
    return sorted(set(ids))


def list_race_ids_for_date(date_yyyymmdd: str) -> List[str]:
    """
    指定日の園田全レース race_id 一覧を返す。

    1R の結果ページを取得し、ページ内リンクから列挙する。
    リンクが取れない場合は 1R～MAX_RACE_NO を順に試す。
    """
    first_id = build_race_id(date_yyyymmdd, 1)
    html = fetch_race_result_html(first_id)

    if not has_result_table(html):
        return []

    ids = list_race_ids_from_html(html, date_yyyymmdd)
    if ids:
        return ids

    # フォールバック: 連番で存在するレースを探す
    found: List[str] = []
    for race_no in range(1, MAX_RACE_NO + 1):
        rid = build_race_id(date_yyyymmdd, race_no)
        if race_no > 1:
            html = fetch_race_result_html(rid)
        if has_result_table(html):
            found.append(rid)
        elif race_no > 1:
            break
    return found


def list_race_ids_for_shutuba(date_yyyymmdd: str) -> List[str]:
    """
    指定日の園田全レース race_id 一覧（出馬表ベース・レース前予想用）。
    """
    first_id = build_race_id(date_yyyymmdd, 1)
    html = fetch_shutuba_html(first_id)

    if not has_shutuba_table(html):
        return []

    ids = list_race_ids_from_html(html, date_yyyymmdd)
    if ids:
        return ids

    found: List[str] = []
    for race_no in range(1, MAX_RACE_NO + 1):
        rid = build_race_id(date_yyyymmdd, race_no)
        if race_no > 1:
            html = fetch_shutuba_html(rid)
        if has_shutuba_table(html):
            found.append(rid)
        elif race_no > 1:
            break
    return found
