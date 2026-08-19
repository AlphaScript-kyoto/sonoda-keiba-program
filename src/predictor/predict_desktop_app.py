"""Sonoda race-day predict desktop UI (Flet). Keep UTF-8."""

from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

import flet as ft
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.display_labels import format_race_table_for_display
from src.predictor.expectation import TIER_ORDER, sort_plans_by_race_no
from src.predictor.horse_form import (
    build_form_matrix_for_plan,
    normalize_race_date,
    resolve_horse_ids,
)
from src.predictor.marks_display import build_marks_display_frame, filter_race_df
from src.predictor.post_format import copy_channel_label, day_post_summary, format_race_copy
from src.predictor.predict_day import PredictDayResult, run_predict_day_safe
from src.predictor.score import load_master, race_display_model_probs
from tools.clipboard_util import copy_to_clipboard

SONODA_MAX_RACE_NO = 12
NOTE_TIERS = frozenset({"SS", "S"})

SHOW_COLS = [
    "mark",
    "umaban",
    "horse_name",
    "win_prob",
    "horse_win_rate",
    "horse_place_rate",
    "odds",
    "popularity",
]

# Ink + warm gold (evening track). Avoid purple / cream-serif cliches.
C_BG = "#070A0E"
C_PANEL = "#10161F"
C_PANEL2 = "#161E2A"
C_LINE = "#2A3545"
C_GOLD = "#D4AF37"
C_GOLD_DIM = "#8A7340"
C_TEXT = "#EDE6D8"
C_MUTED = "#8B93A0"
C_FIRM = "#3D9B6E"
C_UPSET = "#C44B4B"
C_WARN = "#C9893A"

TIER_COLORS = {
    "SS": "#D4AF37",
    "S": "#3D9B6E",
    "A": "#4A7FB5",
    "B": "#9A7B55",
    "C": "#6B7380",
}


def _normalize_date(raw: str) -> str:
    s = raw.strip().replace("/", "").replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError("日付は YYYYMMDD 形式で入力してください。")
    return s


def _passes_filters(plan, *, exotic_only, hide_win_skip, tier_filter):
    if exotic_only and plan.exotic_confidence != "高":
        return False
    if hide_win_skip and "見送り" in plan.confidence:
        return False
    if tier_filter and plan.expectation_tier not in tier_filter:
        return False
    return True


def _race_before_date(win_df, plan, exotic_df=None) -> str:
    for df in (exotic_df, win_df):
        race = filter_race_df(df, plan.race_no) if df is not None else pd.DataFrame()
        if not race.empty and "date" in race.columns:
            return str(race["date"].iloc[0]).strip()
    return ""


def _badge(text: str, bg: str, *, fg: str = "#0B0F14") -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color=fg),
        bgcolor=bg,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=4,
    )


def _muted(text: str, size: int = 12) -> ft.Text:
    return ft.Text(text, size=size, color=C_MUTED)

def _h_check(cb: ft.Checkbox, *, width: int | None = None) -> ft.Container:
    """Keep checkbox from expanding full width (Row wrap would go vertical)."""
    cb.expand = False
    if cb.label_style is None:
        cb.label_style = ft.TextStyle(size=12, color=C_TEXT)
    return ft.Container(
        content=cb,
        width=width,
        padding=ft.Padding.only(right=2),
    )


def _race_pick_panel(race_checks: dict) -> ft.Column:
    """1R-12R as two compact horizontal rows (6 + 6)."""
    cbs = list(race_checks.values())
    row1 = ft.Row(
        spacing=2,
        tight=True,
        controls=[_h_check(cb, width=54) for cb in cbs[:6]],
    )
    row2 = ft.Row(
        spacing=2,
        tight=True,
        controls=[_h_check(cb, width=54) for cb in cbs[6:]],
    )
    return ft.Column(spacing=0, tight=True, controls=[row1, row2])




class PredictDesktopApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.last_result: Optional[PredictDayResult] = None
        self.last_win_df: Optional[pd.DataFrame] = None
        self.fetching = False

        self.date_field = ft.TextField(
            label="予想日 (YYYYMMDD)",
            value=date.today().strftime("%Y%m%d"),
            width=140,
            text_size=13,
            dense=True,
            height=44,
            border_color=C_LINE,
            focused_border_color=C_GOLD,
            label_style=ft.TextStyle(color=C_MUTED),
            color=C_TEXT,
            cursor_color=C_GOLD,
        )
        self.offline_cb = ft.Checkbox(label="オフライン", value=False, fill_color=C_GOLD)
        self.force_cb = ft.Checkbox(label="発走済も再取得", value=False, fill_color=C_GOLD)
        self.limit_race_cb = ft.Checkbox(
            label="指定レースのみ",
            value=False,
            fill_color=C_GOLD,
            on_change=self._on_limit_toggle,
        )
        self.exotic_cb = ft.Checkbox(
            label="三連・自信度高のみ", value=False, fill_color=C_GOLD,
            on_change=self._on_filter_change,
        )
        self.hide_skip_cb = ft.Checkbox(
            label="単勝見送りを除く", value=False, fill_color=C_GOLD,
            on_change=self._on_filter_change,
        )
        self.tier_checks = {
            t: ft.Checkbox(label=t, value=False, fill_color=C_GOLD) for t in TIER_ORDER
        }
        self.race_checks = {
            n: ft.Checkbox(label=f"{n}R", value=False, fill_color=C_GOLD)
            for n in range(1, SONODA_MAX_RACE_NO + 1)
        }
        self.race_row = _race_pick_panel(self.race_checks)
        self.race_row.visible = False
        self.progress = ft.ProgressBar(
            value=0, color=C_GOLD, bgcolor=C_LINE, visible=False, bar_height=3
        )
        self.status = ft.Text("", size=12, color=C_MUTED)
        self.summary = ft.Text("", size=13, color=C_TEXT, weight=ft.FontWeight.BOLD)
        self.results_host = ft.Column(spacing=14, tight=True)
        self.fetch_btn = ft.ElevatedButton(
            "予想を取得",
            icon=ft.Icons.BOLT,
            bgcolor=C_GOLD,
            color="#0B0F14",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            ),
            on_click=self._on_fetch,
        )

    def _on_limit_toggle(self, _e=None):
        self.race_row.visible = bool(self.limit_race_cb.value)
        self.page.update()

    def _on_filter_change(self, _e=None):
        if self.last_result is not None:
            self._render_results()
            self.page.update()

    def _selected_race_nos(self) -> list[int]:
        if not self.limit_race_cb.value:
            return []
        return [n for n, cb in self.race_checks.items() if cb.value]

    def _selected_tiers(self) -> list[str]:
        return [t for t, cb in self.tier_checks.items() if cb.value]

    def _snack(self, message: str, *, error: bool = False):
        self.page.open(
            ft.SnackBar(
                content=ft.Text(message, color=C_TEXT),
                bgcolor=C_UPSET if error else C_PANEL2,
                duration=3500,
            )
        )

    def build(self) -> None:
        page = self.page
        page.title = "園田予想"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = C_BG
        page.padding = 0
        page.window.width = 1280
        page.window.height = 860
        page.window.min_width = 960
        page.window.min_height = 680
        page.fonts = {
            "Brand": (
                "https://github.com/google/fonts/raw/main/ofl/"
                "zenkakugothicnew/ZenKakuGothicNew-Bold.ttf"
            ),
            "Body": (
                "https://github.com/google/fonts/raw/main/ofl/"
                "zenkakugothicnew/ZenKakuGothicNew-Regular.ttf"
            ),
        }
        page.theme = ft.Theme(font_family="Body")

        page.scroll = ft.ScrollMode.AUTO

        hero = ft.Container(
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                "SONODA",
                                size=26,
                                weight=ft.FontWeight.BOLD,
                                color=C_GOLD,
                                font_family="Brand",
                            ),
                            ft.Text(
                                "当日予想デスク",
                                size=14,
                                color=C_TEXT,
                                font_family="Brand",
                            ),
                        ],
                    ),
                    _muted("SS/S＝詳細 · A〜C＝印 · コピーでXへ"),
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=28, vertical=12),
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, -1),
                end=ft.Alignment(1, 1),
                colors=[C_BG, "#0E1520", "#121A14"],
            ),
            border=ft.Border.only(bottom=ft.BorderSide(1, C_LINE)),
        )

        control_card = ft.Container(
            bgcolor=C_PANEL,
            border=ft.Border.all(1, C_LINE),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.date_field,
                            _h_check(self.offline_cb),
                            _h_check(self.force_cb),
                            _h_check(self.limit_race_cb),
                            ft.Container(expand=True),
                            self.fetch_btn,
                        ],
                    ),
                    self.race_row,
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            _h_check(self.exotic_cb),
                            _h_check(self.hide_skip_cb),
                            ft.Text("ティア", size=12, color=C_MUTED),
                            *[_h_check(cb) for cb in self.tier_checks.values()],
                        ],
                    ),
                    self.progress,
                    self.status,
                    self.summary,
                ],
            ),
        )

        body = ft.Container(
            padding=ft.Padding.symmetric(horizontal=28, vertical=12),
            content=ft.Column(
                spacing=12,
                tight=True,
                controls=[control_card, self.results_host],
            ),
        )

        page.add(
            ft.Column(
                spacing=0,
                tight=True,
                controls=[hero, body],
            )
        )

    def _on_fetch(self, _e=None):
        if self.fetching:
            return
        try:
            target = _normalize_date(self.date_field.value or "")
        except ValueError as exc:
            self._snack(str(exc), error=True)
            return
        only = self._selected_race_nos()
        if self.limit_race_cb.value and not only:
            self._snack("指定レースのみのときは 1R 以上チェックしてください。", error=True)
            return

        self.fetching = True
        self.fetch_btn.disabled = True
        self.progress.visible = True
        self.progress.value = None
        self.status.value = "準備中…"
        self.page.update()

        def work():
            try:

                def on_progress(current, total, race_id):
                    try:
                        if total > 0:
                            self.progress.value = current / total
                        self.status.value = f"{current}/{total}R 取得中… ({race_id})"
                        self.page.update()
                    except Exception:
                        pass

                cache = (
                    self.last_result
                    if (
                        self.last_result is not None
                        and self.last_result.date == target
                        and not self.offline_cb.value
                    )
                    else None
                )
                result = run_predict_day_safe(
                    target,
                    offline=bool(self.offline_cb.value),
                    on_progress=on_progress,
                    cache=cache,
                    force_refresh=bool(self.force_cb.value or self.offline_cb.value),
                    only_race_nos=set(only) if only else None,
                )
                self._apply_result(target, result, only)
            except Exception as exc:
                print(traceback.format_exc())
                self._fetch_failed(str(exc))

        self.page.run_thread(work)

    def _fetch_failed(self, message: str):
        self.fetching = False
        self.fetch_btn.disabled = False
        self.progress.visible = False
        self.status.value = ""
        self._snack(f"取得失敗: {message}", error=True)
        self.page.update()

    def _apply_result(self, target: str, result: PredictDayResult, only: list[int]):
        self.fetching = False
        self.fetch_btn.disabled = False
        self.progress.visible = False
        self.progress.value = 0
        self.status.value = ""

        if result.message and result.win_df.empty:
            self._snack(result.message, error=True)
            self.page.update()
            return

        self.last_result = result
        self.last_win_df = result.win_df
        summary = f"{target} · {result.race_count}レース · {day_post_summary(result.plans)}"
        if only:
            summary = f"{summary} · 取得: {','.join(f'{n}R' for n in sorted(only))}"
        if result.message:
            summary = f"{summary} · {result.message}"
        self.summary.value = summary
        self._render_results()
        self.page.update()

    def _render_results(self):
        self.results_host.controls.clear()
        result = self.last_result
        win_df = self.last_win_df
        if result is None or win_df is None:
            return

        plans = sort_plans_by_race_no(result.plans)
        shown = [
            p
            for p in plans
            if _passes_filters(
                p,
                exotic_only=bool(self.exotic_cb.value),
                hide_win_skip=bool(self.hide_skip_cb.value),
                tier_filter=self._selected_tiers(),
            )
        ]
        if not shown:
            self.results_host.controls.append(
                ft.Text("フィルタ条件に合うレースがありません。", color=C_WARN)
            )
            return

        self.results_host.controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(
                        f"レース一覧  {len(shown)} / {len(plans)}R",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=C_TEXT,
                        font_family="Brand",
                    ),
                    _muted(day_post_summary(plans)),
                ],
            )
        )

        try:
            master = load_master()
        except FileNotFoundError:
            master = None

        dist_map: dict[int, str] = {}
        if not win_df.empty and "distance" in win_df.columns:
            for race_no, grp in win_df.groupby("race_no"):
                dist_map[int(race_no)] = str(grp["distance"].iloc[0])

        for plan in shown:
            self.results_host.controls.append(
                self._race_card(
                    plan,
                    win_df,
                    result.exotic_df,
                    master=master,
                    distance=dist_map.get(plan.race_no, ""),
                )
            )

    def _race_card(
        self,
        plan: RaceBetPlan,
        win_df: pd.DataFrame,
        exotic_df,
        *,
        master,
        distance: str,
    ) -> ft.Container:
        tier = plan.expectation_tier
        tier_bg = TIER_COLORS.get(tier, C_MUTED)
        win_bg = (
            C_FIRM
            if plan.win_profile == "堅"
            else C_UPSET
            if plan.win_profile == "荒"
            else C_MUTED
        )
        ex_bg = (
            C_FIRM
            if plan.exotic_profile == "堅"
            else C_UPSET
            if plan.exotic_profile == "荒"
            else C_MUTED
        )

        badges = ft.Row(
            spacing=6,
            wrap=True,
            controls=[
                _badge(f"期待値 {tier}", tier_bg, fg="#0B0F14"),
                _badge(f"単勝:{plan.win_profile}", win_bg, fg="#fff"),
                _badge(f"三連:{plan.exotic_profile}", ex_bg, fg="#fff"),
                _badge(f"単勝:{plan.confidence}", C_PANEL2, fg=C_TEXT),
                _badge(f"三連:{plan.exotic_confidence}", C_PANEL2, fg=C_TEXT),
            ],
        )

        disp_top, disp_gap = 0.0, 0.0
        if exotic_df is not None and not exotic_df.empty:
            race = filter_race_df(exotic_df, plan.race_no)
            disp_top, disp_gap = race_display_model_probs(race)

        meta = _muted(
            f"スコア {plan.expectation_score} · 1番人気 {plan.fav_odds:.1f}倍 · "
            f"モデル {disp_top:.1%} · 差 {disp_gap:.1%}"
            + (" · 発走済" if plan.is_started else "")
        )

        table = format_race_table_for_display(
            build_marks_display_frame(plan, win_df, exotic_df, master=master),
            SHOW_COLS,
        )
        if table.empty:
            table_ctrl: ft.Control = _muted("出走表なし")
        else:
            cols = list(table.columns)
            table_ctrl = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text(str(c), size=11, color=C_MUTED)) for c in cols
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(row[c]), size=12, color=C_TEXT))
                            for c in cols
                        ]
                    )
                    for _, row in table.iterrows()
                ],
                heading_row_color=C_PANEL2,
                data_row_min_height=32,
                column_spacing=18,
                border=ft.Border.all(1, C_LINE),
                border_radius=6,
            )

        copy_text = format_race_copy(plan, win_df, exotic_df)
        channel = copy_channel_label(plan.expectation_tier)
        copy_field = ft.TextField(
            value=copy_text,
            multiline=True,
            min_lines=6 if tier in NOTE_TIERS else 3,
            max_lines=18 if tier in NOTE_TIERS else 6,
            read_only=True,
            border_color=C_LINE,
            focused_border_color=C_GOLD,
            color=C_TEXT,
            text_size=12,
            expand=True,
        )

        def do_copy(_e, text=copy_text, rno=plan.race_no):
            if copy_to_clipboard(text):
                self._snack(f"{rno}R をクリップボードにコピーしました")
            else:
                self._snack("クリップボードコピーに失敗しました", error=True)

        form_block: list[ft.Control] = []
        if tier in NOTE_TIERS and master is not None and not master.empty:
            before = normalize_race_date(_race_before_date(win_df, plan, exotic_df))
            if before:
                hid_map = resolve_horse_ids(plan, win_df, exotic_df)
                form_df = build_form_matrix_for_plan(
                    plan,
                    master,
                    before,
                    horse_by_umaban=hid_map,
                    win_df=win_df,
                    exotic_df=exotic_df,
                )
                if not form_df.empty:
                    form_cols = list(form_df.columns)
                    form_block.extend(
                        [
                            _muted("馬柱（直近5走）", 12),
                            ft.DataTable(
                                columns=[
                                    ft.DataColumn(
                                        ft.Text(str(c), size=10, color=C_MUTED)
                                    )
                                    for c in form_cols
                                ],
                                rows=[
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(
                                                ft.Text(
                                                    str(row[c]), size=10, color=C_TEXT
                                                )
                                            )
                                            for c in form_cols
                                        ]
                                    )
                                    for _, row in form_df.iterrows()
                                ],
                                heading_row_color=C_PANEL2,
                                data_row_min_height=28,
                                column_spacing=10,
                                border=ft.Border.all(1, C_LINE),
                                border_radius=6,
                            ),
                        ]
                    )

        post = f"  {plan.post_time}" if plan.post_time else ""
        started = "  · 発走済" if plan.is_started else ""
        title = f"{plan.race_no}R{post}  {plan.race_name}  {distance}{started}"

        return ft.Container(
            bgcolor=C_PANEL,
            border=ft.Border.all(1, C_LINE),
            border_radius=12,
            padding=18,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                title,
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=C_TEXT,
                                font_family="Brand",
                            ),
                            ft.OutlinedButton(
                                "コピー",
                                icon=ft.Icons.CONTENT_COPY,
                                style=ft.ButtonStyle(
                                    color=C_GOLD,
                                    side=ft.BorderSide(1, C_GOLD_DIM),
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                                on_click=do_copy,
                            ),
                        ],
                    ),
                    badges,
                    meta,
                    ft.Container(content=table_ctrl, padding=ft.Padding.only(top=4)),
                    *form_block,
                    _muted(f"コピー用（{channel}）"),
                    copy_field,
                ],
            ),
        )


def _main_page(page: ft.Page):
    app = PredictDesktopApp(page)
    app.build()


def main():
    ft.app(target=_main_page)


if __name__ == "__main__":
    main()
