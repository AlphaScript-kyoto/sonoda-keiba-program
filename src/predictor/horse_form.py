"""馬柱（直近5走・横並び）。"""

from __future__ import annotations

import html
import re
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from src.predictor.bets import RaceBetPlan
from src.predictor.marks_display import (
    filter_race_df,
    is_valid_horse_id,
    normalize_umaban,
    sort_marks,
)
from src.predictor.rationale import PACE_LABEL

MarkLine = Tuple[str, str, str]

FORM_RUN_COLUMNS = ["前走", "2走", "3走", "4走", "5走"]
VENUE_LABEL = "園田"
_EMPTY_CELL = "—"
_DATE_DIGITS_RE = re.compile(r"(\d{8})")


def normalize_race_date(value) -> str:
    """比較用に YYYYMMDD へ揃える。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if len(s) == 8 and s.isdigit():
        return s
    m = _DATE_DIGITS_RE.search(s)
    return m.group(1) if m else s


def _normalize_horse_name(name: str) -> str:
    return str(name).strip().replace(" ", "").replace("　", "")


def _fmt_date_long(d: str) -> str:
    s = normalize_race_date(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}.{s[4:6]}.{s[6:8]}"
    return s or _EMPTY_CELL


def _fmt_pace(val) -> str:
    p = str(val).strip().upper()
    if not p or p == "NAN":
        return ""
    return PACE_LABEL.get(p, p)


def _cell(val, default: str = "") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    s = str(val).strip()
    return s if s and s.lower() != "nan" else default


def _finish_label(row: pd.Series) -> str:
    fin = pd.to_numeric(row.get("finish"), errors="coerce")
    if pd.isna(fin):
        return _EMPTY_CELL
    n = int(fin)
    if n == 1:
        return "1着"
    return f"{n}着"


def _distance_line(row: pd.Series) -> str:
    dist = _cell(row.get("distance"))
    surf = _cell(row.get("surface"))
    if surf and dist:
        return f"{surf}{dist}"
    return dist or surf or _EMPTY_CELL


def _entry_line(row: pd.Series) -> str:
    hc = _cell(row.get("head_count"))
    u = _cell(row.get("umaban"))
    pop = _cell(row.get("popularity"))
    parts = []
    if hc:
        parts.append(f"{hc}頭")
    if u:
        parts.append(f"{u}番")
    if pop:
        parts.append(f"{pop}人")
    return " ".join(parts) if parts else _EMPTY_CELL


def _corner_line(row: pd.Series) -> str:
    avg = pd.to_numeric(row.get("corner_pos_avg"), errors="coerce")
    if pd.notna(avg):
        return f"通過均{avg:.1f}"
    return ""


def format_run_cell(row: pd.Series, *, venue: str = VENUE_LABEL) -> str:
    """1走分を netkeiba 馬柱風の複数行テキストにする。"""
    lines: List[str] = []
    date_s = _fmt_date_long(row.get("date", ""))
    lines.append(f"{date_s} {venue}")

    cls = _cell(row.get("race_class"), _EMPTY_CELL)
    lines.append(f"{cls}　【{_finish_label(row)}】")

    dist_part = _distance_line(row)
    time_s = _cell(row.get("race_time"))
    track_s = _cell(row.get("track"))
    line3 = dist_part
    if time_s:
        line3 += f" {time_s}"
    if track_s:
        line3 += f" {track_s}"
    lines.append(line3.strip() or _EMPTY_CELL)

    lines.append(_entry_line(row))

    jockey = _cell(row.get("jockey"))
    weight = _cell(row.get("carried_weight"))
    if jockey or weight:
        lines.append(f"{jockey} {weight}".strip())
    else:
        lines.append(_EMPTY_CELL)

    detail_parts: List[str] = []
    corner = _corner_line(row)
    if corner:
        detail_parts.append(corner)
    l3f = _cell(row.get("last_3f"))
    if l3f:
        detail_parts.append(f"({l3f})")
    bw = _cell(row.get("body_weight"))
    if bw:
        detail_parts.append(bw)
    pace = _fmt_pace(row.get("race_pace"))
    if pace:
        detail_parts.append(pace)
    lines.append(" ".join(detail_parts) if detail_parts else _EMPTY_CELL)

    margin = _cell(row.get("margin"))
    if margin:
        lines.append(f"着差 {margin}")

    return "\n".join(lines)


def _history_before_date(master: pd.DataFrame, before_date: str) -> pd.DataFrame:
    cutoff = normalize_race_date(before_date)
    if master.empty or not cutoff:
        return master.iloc[0:0].copy()
    dates = master["date"].astype(str).map(normalize_race_date)
    return master[dates < cutoff].copy()


def horse_id_from_name(
    master: pd.DataFrame,
    horse_name: str,
    before_date: str,
) -> str:
    """馬名から master 上の horse_id を推定（同姓が複数いれば走数最多を採用）。"""
    nm = _normalize_horse_name(horse_name)
    if not nm or master.empty:
        return ""
    hist = _history_before_date(master, before_date)
    if hist.empty or "horse_name" not in hist.columns:
        return ""
    matched = hist[
        hist["horse_name"].astype(str).map(_normalize_horse_name) == nm
    ]
    if matched.empty:
        return ""
    ids = [
        x for x in matched["horse_id"].astype(str).unique()
        if is_valid_horse_id(x)
    ]
    if not ids:
        return ""
    if len(ids) == 1:
        return ids[0]
    return max(
        ids,
        key=lambda hid: len(matched[matched["horse_id"].astype(str) == hid]),
    )


def resolve_horse_id_for_mark(
    umaban: str,
    horse_name: str,
    horse_by_umaban: dict[str, str],
    *,
    master: Optional[pd.DataFrame] = None,
    before_date: str = "",
    win_race: Optional[pd.DataFrame] = None,
    ex_race: Optional[pd.DataFrame] = None,
) -> str:
    """印1頭分の horse_id を解決（馬番 → 行 → 馬名の順）。"""
    u = normalize_umaban(umaban)
    hid = str(horse_by_umaban.get(u, "")).strip()
    if is_valid_horse_id(hid):
        return hid

    for df in (ex_race, win_race):
        if df is None or df.empty or "umaban" not in df.columns:
            continue
        for _, row in df.iterrows():
            if normalize_umaban(row["umaban"]) != u:
                continue
            row_hid = str(row.get("horse_id", "")).strip()
            if is_valid_horse_id(row_hid):
                return row_hid

    if master is not None and horse_name:
        by_name = horse_id_from_name(master, horse_name, before_date)
        if is_valid_horse_id(by_name):
            return by_name
    return ""


def recent_run_series(
    master: pd.DataFrame,
    horse_id: str,
    before_date: str,
    *,
    horse_name: str = "",
    n: int = 5,
) -> List[pd.Series]:
    """直近 n 走（新しい順）。"""
    hid = str(horse_id).strip()
    if not is_valid_horse_id(hid) and horse_name:
        hid = horse_id_from_name(master, horse_name, before_date)
    if not is_valid_horse_id(hid) or master.empty or not before_date:
        return []

    hist = _history_before_date(master, before_date)
    hist = hist[hist["horse_id"].astype(str) == hid].copy()
    if hist.empty and horse_name:
        alt = horse_id_from_name(master, horse_name, before_date)
        if is_valid_horse_id(alt) and alt != hid:
            hid = alt
            hist = _history_before_date(master, before_date)
            hist = hist[hist["horse_id"].astype(str) == hid].copy()
    if hist.empty:
        return []

    hist["_date_sort"] = hist["date"].astype(str).map(normalize_race_date)
    hist = hist.sort_values(["_date_sort", "race_no"], ascending=False).head(n)
    return [row for _, row in hist.iterrows()]


def recent_runs_rows(
    master: pd.DataFrame,
    horse_id: str,
    before_date: str,
    *,
    horse_name: str = "",
    n: int = 5,
) -> List[dict]:
    """後方互換: 縦持ち dict リスト。"""
    return [
        {"走": f"{i}走前", "内容": format_run_cell(r)}
        for i, r in enumerate(
            recent_run_series(
                master, horse_id, before_date, horse_name=horse_name, n=n,
            ),
            start=1,
        )
    ]


def build_form_matrix_for_plan(
    plan: RaceBetPlan,
    master: pd.DataFrame,
    before_date: str,
    *,
    horse_by_umaban: Optional[dict[str, str]] = None,
    win_df: Optional[pd.DataFrame] = None,
    exotic_df: Optional[pd.DataFrame] = None,
    n: int = 5,
) -> pd.DataFrame:
    """
    印5頭×（馬名 + 前走〜5走）の1枚表。
    各走セルは改行区切りテキスト。
    """
    if not plan.marks or master.empty or not before_date:
        return pd.DataFrame()

    cutoff = normalize_race_date(before_date)
    if not cutoff:
        return pd.DataFrame()

    hid_map = horse_by_umaban or {}
    win_race = (
        filter_race_df(win_df, plan.race_no)
        if win_df is not None else pd.DataFrame()
    )
    ex_race = (
        filter_race_df(exotic_df, plan.race_no)
        if exotic_df is not None else pd.DataFrame()
    )

    rows: List[dict] = []
    for mark, umaban, horse_name in sort_marks(plan.marks):
        u = normalize_umaban(umaban)
        hid = resolve_horse_id_for_mark(
            umaban,
            horse_name,
            hid_map,
            master=master,
            before_date=cutoff,
            win_race=win_race,
            ex_race=ex_race,
        )
        name = horse_name or "—"
        horse_col = f"{mark} {u}番\n{name}"
        cells = {col: _EMPTY_CELL for col in FORM_RUN_COLUMNS}
        if hid:
            runs = recent_run_series(
                master, hid, cutoff, horse_name=horse_name, n=n,
            )
            for col, run in zip(FORM_RUN_COLUMNS, runs):
                cells[col] = format_run_cell(run)
        rows.append({"馬名": horse_col, **cells})

    return pd.DataFrame(rows, columns=["馬名", *FORM_RUN_COLUMNS])


def form_matrix_html(df: pd.DataFrame) -> str:
    """展開不要で全文表示する静的 HTML 表（Streamlit markdown 用）。"""
    if df.empty:
        return ""
    cols = list(df.columns)
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body_rows: List[str] = []
    for _, row in df.iterrows():
        tds: List[str] = []
        for c in cols:
            raw = str(row[c]) if pd.notna(row.get(c)) else _EMPTY_CELL
            safe = html.escape(raw).replace("\n", "<br>")
            cls = "form-name" if c == "馬名" else "form-cell"
            tds.append(f'<td class="{cls}">{safe}</td>')
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    return (
        "<style>"
        ".form-table{width:100%;border-collapse:collapse;font-size:0.84rem;"
        "table-layout:fixed;}"
        ".form-table th,.form-table td{border:1px solid rgba(128,128,128,0.4);"
        "padding:8px 10px;vertical-align:top;word-break:break-word;}"
        ".form-table th{background:rgba(128,128,128,0.12);white-space:nowrap;}"
        ".form-table th:first-child,.form-name{width:7%;}"
        ".form-cell{line-height:1.4;}"
        "</style>"
        f'<table class="form-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def build_form_tables_for_plan(
    plan: RaceBetPlan,
    master: pd.DataFrame,
    before_date: str,
    *,
    horse_by_umaban: Optional[dict[str, str]] = None,
    win_df: Optional[pd.DataFrame] = None,
    exotic_df: Optional[pd.DataFrame] = None,
    n: int = 5,
) -> List[tuple[str, pd.DataFrame]]:
    """後方互換: 単一表を返す。"""
    df = build_form_matrix_for_plan(
        plan,
        master,
        before_date,
        horse_by_umaban=horse_by_umaban,
        win_df=win_df,
        exotic_df=exotic_df,
        n=n,
    )
    if df.empty:
        return []
    return [("馬柱", df)]


def resolve_horse_ids(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame],
) -> dict[str, str]:
    """馬番 -> horse_id（三連行優先。空 ID は win 側で補完）。"""
    ex = filter_race_df(exotic_df, plan.race_no) if exotic_df is not None else pd.DataFrame()
    win = filter_race_df(win_df, plan.race_no)
    out: dict[str, str] = {}
    for df in (ex, win):
        if df.empty or "umaban" not in df.columns:
            continue
        for _, row in df.iterrows():
            u = normalize_umaban(row["umaban"])
            if not u:
                continue
            hid = str(row.get("horse_id", "")).strip()
            if not is_valid_horse_id(hid):
                continue
            if u not in out:
                out[u] = hid
    return out
