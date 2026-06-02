"""馬柱（直近5走・横並び）。"""

from __future__ import annotations

import html
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from src.predictor.bets import RaceBetPlan
from src.predictor.marks_display import normalize_umaban, sort_marks
from src.predictor.rationale import PACE_LABEL

MarkLine = Tuple[str, str, str]

FORM_RUN_COLUMNS = ["前走", "2走", "3走", "4走", "5走"]
VENUE_LABEL = "園田"


def _fmt_date_long(d: str) -> str:
    s = str(d).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}.{s[4:6]}.{s[6:8]}"
    return s or "—"


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
        return "—"
    n = int(fin)
    if n == 1:
        return "1着"
    return f"{n}着"


def _distance_line(row: pd.Series) -> str:
    dist = _cell(row.get("distance"))
    surf = _cell(row.get("surface"))
    if surf and dist:
        return f"{surf}{dist}"
    return dist or surf or "—"


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
    return " ".join(parts) if parts else "—"


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

    cls = _cell(row.get("race_class"), "—")
    lines.append(f"{cls}　【{_finish_label(row)}】")

    dist_part = _distance_line(row)
    time_s = _cell(row.get("race_time"))
    track_s = _cell(row.get("track"))
    line3 = dist_part
    if time_s:
        line3 += f" {time_s}"
    if track_s:
        line3 += f" {track_s}"
    lines.append(line3.strip() or "—")

    lines.append(_entry_line(row))

    jockey = _cell(row.get("jockey"))
    weight = _cell(row.get("carried_weight"))
    if jockey or weight:
        lines.append(f"{jockey} {weight}".strip())
    else:
        lines.append("—")

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
    lines.append(" ".join(detail_parts) if detail_parts else "—")

    margin = _cell(row.get("margin"))
    if margin:
        lines.append(f"着差 {margin}")

    return "\n".join(lines)


def recent_run_series(
    master: pd.DataFrame,
    horse_id: str,
    before_date: str,
    *,
    n: int = 5,
) -> List[pd.Series]:
    """直近 n 走（新しい順）。"""
    hid = str(horse_id).strip()
    if not hid or master.empty or not before_date:
        return []
    hist = master[
        (master["horse_id"].astype(str) == hid)
        & (master["date"].astype(str) < str(before_date))
    ].copy()
    if hist.empty:
        return []
    hist["_date_sort"] = hist["date"].astype(str)
    hist = hist.sort_values(["_date_sort", "race_no"], ascending=False).head(n)
    return [row for _, row in hist.iterrows()]


def recent_runs_rows(
    master: pd.DataFrame,
    horse_id: str,
    before_date: str,
    *,
    n: int = 5,
) -> List[dict]:
    """後方互換: 縦持ち dict リスト。"""
    return [
        {"走": f"{i}走前", "内容": format_run_cell(r)}
        for i, r in enumerate(recent_run_series(master, horse_id, before_date, n=n), start=1)
    ]


def build_form_matrix_for_plan(
    plan: RaceBetPlan,
    master: pd.DataFrame,
    before_date: str,
    *,
    horse_by_umaban: Optional[dict[str, str]] = None,
    n: int = 5,
) -> pd.DataFrame:
    """
    印5頭×（馬名 + 前走〜5走）の1枚表。
    各走セルは改行区切りテキスト。
    """
    if not plan.marks or master.empty or not before_date:
        return pd.DataFrame()

    rows: List[dict] = []
    for mark, umaban, horse_name in sort_marks(plan.marks):
        u = normalize_umaban(umaban)
        hid = (horse_by_umaban or {}).get(u, "")
        name = horse_name or "—"
        horse_col = f"{mark} {u}番\n{name}"
        cells = {col: "—" for col in FORM_RUN_COLUMNS}
        if hid:
            runs = recent_run_series(master, hid, before_date, n=n)
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
            raw = str(row[c]) if pd.notna(row.get(c)) else "—"
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
    n: int = 5,
) -> List[tuple[str, pd.DataFrame]]:
    """後方互換: 単一表を返す。"""
    df = build_form_matrix_for_plan(
        plan, master, before_date, horse_by_umaban=horse_by_umaban, n=n,
    )
    if df.empty:
        return []
    return [("馬柱", df)]


def resolve_horse_ids(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame],
) -> dict[str, str]:
    """馬番 -> horse_id（三連行優先）。"""
    from src.predictor.marks_display import filter_race_df

    ex = filter_race_df(exotic_df, plan.race_no) if exotic_df is not None else pd.DataFrame()
    win = filter_race_df(win_df, plan.race_no)
    out: dict[str, str] = {}
    for df in (ex, win):
        if df.empty or "umaban" not in df.columns:
            continue
        for _, row in df.iterrows():
            u = normalize_umaban(row["umaban"])
            if u not in out and pd.notna(row.get("horse_id")):
                out[u] = str(row["horse_id"]).strip()
    return out
