"""netkeiba 出馬表への予想印リンク生成（Tampermonkey 連携）。"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from config.settings import URL_SHUTUBA

# netkeiba select value: {umaban}_{code}
MARK_TO_NETKEIBA_CODE: Dict[str, str] = {
    "\u25ce": "1",
    "\u25cb": "2",
    "\u25ef": "2",
    "\u25b2": "3",
    "\u25b3": "4",
    "\u2606": "5",
}

MarkLine = Tuple[str, str, str]


def marks_to_sonoda_param(marks: Sequence[MarkLine]) -> str:
    """2:1,8:2 形式（馬番:印コード）。"""
    parts: List[str] = []
    for mark, umaban, _name in marks:
        code = MARK_TO_NETKEIBA_CODE.get(str(mark).strip())
        if not code:
            continue
        uma = str(umaban).strip()
        if uma.isdigit():
            parts.append(f"{uma}:{code}")
    return ",".join(parts)


def build_shutuba_url_with_marks(race_id: str, marks: Sequence[MarkLine]) -> str:
    """出馬表 URL + sonoda_marks クエリ（LINE でも # より安定）。"""
    base = URL_SHUTUBA.format(race_id=str(race_id))
    param = marks_to_sonoda_param(marks)
    if not param:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}sonoda_marks={param}"


def format_netkeiba_marks_block(plan) -> str:
    """T-10 LINE 本文末尾に足す印自動リンクブロック。"""
    if plan is None:
        return ""
    marks = getattr(plan, "marks", None) or []
    if not marks:
        return ""
    race_id = str(getattr(plan, "race_id", "") or "").strip()
    if not race_id:
        return ""
    url = build_shutuba_url_with_marks(race_id, marks)
    return f"\n\n\u25bc \u51fa\u99ac\u8868\uff08\u5370\u81ea\u52d5\uff09\n{url}"
