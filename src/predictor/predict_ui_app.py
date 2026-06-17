"""園田競馬 当日予想 UI（Streamlit 本体）。UTF-8 で編集すること。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.display_labels import format_race_table_for_display
from src.predictor.expectation import TIER_ORDER, sort_plans_by_race_no
from src.predictor.horse_form import (
    build_form_matrix_for_plan,
    form_matrix_html,
    normalize_race_date,
    resolve_horse_ids,
)
from src.predictor.marks_display import build_marks_display_frame, filter_race_df
from src.predictor.post_format import copy_channel_label, day_post_summary, format_race_copy
from src.predictor.predict_day import PredictDayResult, run_predict_day_safe
from src.predictor.score import load_master, race_display_model_probs

SONODA_MAX_RACE_NO = 12
NOTE_TIERS = frozenset({"SS", "S"})

SHOW_COLS = [
    "mark", "umaban", "horse_name", "win_prob", "horse_win_rate",
    "horse_place_rate", "odds", "popularity",
]

TIER_COLORS = {"SS": "#b8860b", "S": "#2e7d32", "A": "#1565c0", "B": "#6d4c41", "C": "#757575"}


def _normalize_date(raw: str) -> str:
    s = raw.strip().replace("/", "").replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError("日付は YYYYMMDD 形式で入力してください。")
    return s


def _tier_badge(tier: str) -> str:
    color = TIER_COLORS.get(tier, "#555")
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:4px;font-weight:bold;margin-right:8px">'
        f"期待値 {tier}</span>"
    )


def _race_rows(win_df, plan, exotic_df=None, master=None):
    view = build_marks_display_frame(plan, win_df, exotic_df, master=master)
    return format_race_table_for_display(view, SHOW_COLS)


def _profile_badge(label, value):
    color = "#2e7d32" if value == "堅" else "#c62828" if value == "荒" else "#555"
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;margin-right:6px;font-size:0.85em">{label}:{value}</span>'
    )


def _race_before_date(win_df, plan, exotic_df=None) -> str:
    for df in (exotic_df, win_df):
        race = filter_race_df(df, plan.race_no) if df is not None else pd.DataFrame()
        if not race.empty and "date" in race.columns:
            return str(race["date"].iloc[0]).strip()
    return ""


def _render_horse_form(plan, win_df, exotic_df=None, *, master=None):
    if master is None or master.empty:
        st.caption("馬柱: master 未読込のため省略")
        return
    before = normalize_race_date(_race_before_date(win_df, plan, exotic_df))
    if not before:
        return
    hid_map = resolve_horse_ids(plan, win_df, exotic_df)
    form_df = build_form_matrix_for_plan(
        plan,
        master,
        before,
        horse_by_umaban=hid_map,
        win_df=win_df,
        exotic_df=exotic_df,
    )
    if form_df.empty:
        return
    st.markdown("**馬柱（直近5走）**")
    st.markdown(form_matrix_html(form_df), unsafe_allow_html=True)


def _render_plan_header(plan, distance, *, exotic_df=None):
    conf_color = "#1565c0" if plan.confidence == "高" else "#757575"
    ex_color = "#6a1b9a" if plan.exotic_confidence == "高" else "#757575"
    badges = "".join([
        _tier_badge(plan.expectation_tier),
        _profile_badge("単勝", plan.win_profile),
        _profile_badge("三連", plan.exotic_profile),
        f'<span style="background:{conf_color};color:#fff;padding:2px 8px;border-radius:4px;margin-right:6px">'
        f"単勝:{plan.confidence}</span>",
        f'<span style="background:{ex_color};color:#fff;padding:2px 8px;border-radius:4px">'
        f"三連:{plan.exotic_confidence}</span>",
    ])
    st.markdown(f"**{plan.race_no}R** {plan.race_name} {distance}  \n{badges}", unsafe_allow_html=True)
    disp_top, disp_gap = 0.0, 0.0
    if exotic_df is not None and not exotic_df.empty:
        race = filter_race_df(exotic_df, plan.race_no)
        disp_top, disp_gap = race_display_model_probs(race)
    st.caption(
        f"期待値スコア {plan.expectation_score} · "
        f"1番人気 {plan.fav_odds:.1f}倍 · "
        f"モデル確率（レース内） {disp_top:.1%} · 1-2位差 {disp_gap:.1%}"
    )
    st.caption(
        "※ モデル確率＝レース内の相対評価。"
        "勝率・連対率＝予想日より前の園田成績（1着率・2着以内率）。"
    )
    if plan.fav_odds <= 0:
        st.warning("オッズ未取得（再取得するか、オッズ確定後に試してください）")


def _copy_text_widget_key(plan: RaceBetPlan) -> str:
    """text_area の key。再取得ごとに epoch を変え、古い投稿文が残らないようにする。"""
    epoch = st.session_state.get("copy_text_epoch", 0)
    return f"race_copy_{plan.race_id}_{epoch}"


def _selected_fetch_race_nos() -> list[int]:
    if not st.session_state.get("limit_race_fetch"):
        return []
    selected: list[int] = []
    for race_no in range(1, SONODA_MAX_RACE_NO + 1):
        if st.session_state.get(f"fetch_race_{race_no}"):
            selected.append(race_no)
    return selected


def _render_race_fetch_selector():
    st.checkbox("指定レースのみ取得", key="limit_race_fetch")
    if not st.session_state.get("limit_race_fetch"):
        return
    st.caption("取得するレースにチェック（1つ以上必須）")
    per_row = 5
    for row_start in range(1, SONODA_MAX_RACE_NO + 1, per_row):
        cols = st.columns(per_row)
        for col_idx, col in enumerate(cols):
            race_no = row_start + col_idx
            if race_no > SONODA_MAX_RACE_NO:
                break
            with col:
                st.checkbox(f"{race_no}R", key=f"fetch_race_{race_no}")


def _passes_filters(plan, *, exotic_only, hide_win_skip, tier_filter):
    if exotic_only and plan.exotic_confidence != "高":
        return False
    if hide_win_skip and "見送り" in plan.confidence:
        return False
    if tier_filter and plan.expectation_tier not in tier_filter:
        return False
    return True


def _render_results(result, win_df, exotic_df=None):
    plans = sort_plans_by_race_no(result.plans)
    exotic_only = st.session_state.get("filter_exotic_high", False)
    hide_win_skip = st.session_state.get("filter_hide_win_skip", False)
    tier_filter = st.session_state.get("filter_tiers", [])
    shown = [
        p for p in plans
        if _passes_filters(
            p, exotic_only=exotic_only, hide_win_skip=hide_win_skip, tier_filter=tier_filter,
        )
    ]
    if not shown:
        st.warning("フィルタ条件に合うレースがありません。")
        return
    st.subheader(f"レース一覧（{len(shown)} / {len(plans)}R）")
    st.caption(day_post_summary(plans))
    try:
        master = load_master()
    except FileNotFoundError:
        master = None
    dist_map = {}
    if not win_df.empty and "distance" in win_df.columns:
        for race_no, grp in win_df.groupby("race_no"):
            dist_map[int(race_no)] = str(grp["distance"].iloc[0])
    for plan in shown:
        distance = dist_map.get(plan.race_no, "")
        started_tag = "　発走済" if plan.is_started else ""
        post_tag = f" {plan.post_time}" if plan.post_time else ""
        label = (
            f"{plan.race_no}R{post_tag} {plan.race_name}{started_tag}"
            f"　期待値{plan.expectation_tier}"
        )
        expanded = (
            not plan.is_started and plan.expectation_tier in NOTE_TIERS
        )
        with st.expander(label, expanded=expanded):
            if plan.is_started:
                st.caption("発走済み — 前回取得の内容（オッズは当時のもの）")
            _render_plan_header(plan, distance, exotic_df=exotic_df)
            table = _race_rows(win_df, plan, exotic_df, master=master)
            if not table.empty:
                st.dataframe(table, width="stretch", hide_index=True)
            if plan.expectation_tier in NOTE_TIERS:
                _render_horse_form(plan, win_df, exotic_df, master=master)
            channel = copy_channel_label(plan.expectation_tier)
            height = 480 if plan.expectation_tier in NOTE_TIERS else 160
            st.text_area(
                f"コピー用（{channel}）",
                format_race_copy(plan, win_df, exotic_df),
                height=height,
                key=_copy_text_widget_key(plan),
            )


def main():
    st.set_page_config(page_title="園田予想", page_icon="🏇", layout="wide")
    st.title("園田競馬 当日予想")
    st.caption(
        "期待値 SS/S＝展開・印と根拠の詳細文 · A〜C＝印のみ · split scoring · "
        "発走済みレースは前回データを再利用（未発走のみ netkeiba 取得）"
    )
    col_date, col_off, col_force = st.columns([2, 1, 1])
    with col_date:
        date_input = st.text_input("予想日（YYYYMMDD）", value=date.today().strftime("%Y%m%d"))
    with col_off:
        offline = st.checkbox("オフライン（master のみ）", value=False)
    with col_force:
        force_refresh = st.checkbox("発走済みも再取得", value=False)
    _render_race_fetch_selector()
    st.checkbox("三連系 自信度「高」のみ", key="filter_exotic_high")
    st.checkbox("単勝見送りを除く", key="filter_hide_win_skip")
    st.multiselect(
        "期待値ティア", options=list(TIER_ORDER), default=[],
        key="filter_tiers", placeholder="全ティア表示",
    )
    if st.button("予想取得", type="primary"):
        try:
            target = _normalize_date(date_input)
        except ValueError as exc:
            st.error(str(exc))
            return
        only_race_nos = _selected_fetch_race_nos()
        if st.session_state.get("limit_race_fetch") and not only_race_nos:
            st.error("指定レースのみ取得のときは、1つ以上レースにチェックしてください。")
            return
        progress = st.progress(0.0, text="準備中…")
        status = st.empty()

        def on_progress(current, total, race_id):
            if total <= 0:
                return
            progress.progress(current / total, text=f"{current}/{total}R 取得中… ({race_id})")
            status.caption(f"取得: {race_id}")

        prev = st.session_state.get("last_result")
        cache = (
            prev
            if isinstance(prev, PredictDayResult) and prev.date == target and not offline
            else None
        )
        with st.spinner(f"{target} 園田を取得中…"):
            result = run_predict_day_safe(
                target,
                offline=offline,
                on_progress=on_progress,
                cache=cache,
                force_refresh=force_refresh or offline,
                only_race_nos=set(only_race_nos) if only_race_nos else None,
            )
        progress.empty()
        status.empty()
        if result.message and result.win_df.empty:
            st.error(result.message)
            return
        st.session_state["last_result"] = result
        st.session_state["last_win_df"] = result.win_df
        st.session_state["copy_text_epoch"] = st.session_state.get("copy_text_epoch", 0) + 1
        summary = f"{target} · {result.race_count}レース · {day_post_summary(result.plans)}"
        if only_race_nos:
            race_label = ",".join(f"{n}R" for n in sorted(only_race_nos))
            summary = f"{summary} · 取得: {race_label}"
        if result.message:
            summary = f"{summary} · {result.message}"
        st.success(summary)
    result = st.session_state.get("last_result")
    win_df = st.session_state.get("last_win_df")
    if result is not None and isinstance(result, PredictDayResult) and win_df is not None:
        _render_results(result, win_df, result.exotic_df)
