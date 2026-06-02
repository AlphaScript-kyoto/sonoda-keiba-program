"""馬柱（直近5走・横並び）のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.horse_form import (
    FORM_RUN_COLUMNS,
    build_form_matrix_for_plan,
    build_form_tables_for_plan,
    format_run_cell,
    form_matrix_html,
    recent_run_series,
)
from src.predictor.marks_display import _career_rates_raw


def test_career_place_rate():
    master = pd.DataFrame(
        [
            {"horse_id": "h1", "date": "20260101", "finish": "3"},
            {"horse_id": "h1", "date": "20260201", "finish": "1"},
            {"horse_id": "h1", "date": "20260301", "finish": "2"},
            {"horse_id": "h1", "date": "20260529", "finish": "1"},
        ]
    )
    wins, places, runs, win_r, place_r = _career_rates_raw(master, "h1", "20260529")
    assert wins == 1
    assert places == 2
    assert runs == 3
    assert abs(win_r - 1 / 3) < 1e-6
    assert abs(place_r - 2 / 3) < 1e-6


def test_format_run_cell_contains_key_lines():
    row = pd.Series(
        {
            "date": "20260201",
            "race_class": "C2",
            "finish": "1",
            "distance": "1400",
            "surface": "ダ",
            "race_time": "1:29.0",
            "track": "稍",
            "head_count": "12",
            "umaban": "3",
            "popularity": "5",
            "jockey": "騎手B",
            "carried_weight": "55.0",
            "last_3f": "37.0",
            "body_weight": "478(-1)",
            "race_pace": "S",
            "margin": "アタマ",
        }
    )
    text = format_run_cell(row)
    assert "2026.02.01" in text
    assert "園田" in text
    assert "C2" in text and "1着" in text
    assert "ダ1400" in text
    assert "12頭" in text and "3番" in text
    assert "騎手B" in text
    assert "スロー" in text
    assert "着差" in text


def test_build_form_matrix_columns_and_order():
    master = pd.DataFrame(
        [
            {
                "horse_id": "hid1",
                "date": "20260101",
                "race_no": 1,
                "race_class": "C3",
                "distance": "1400",
                "track": "良",
                "finish": "3",
            },
            {
                "horse_id": "hid1",
                "date": "20260201",
                "race_no": 1,
                "race_class": "C2",
                "distance": "1500",
                "track": "稍",
                "finish": "1",
            },
        ]
    )
    runs = recent_run_series(master, "hid1", "20260301", n=5)
    assert len(runs) == 2
    assert runs[0]["race_class"] == "C2"

    plan = RaceBetPlan(
        race_id="r1",
        race_no=1,
        race_name="テスト",
        confidence="高",
        win_prob_top=0.9,
        prob_gap=0.7,
        marks=[("◎", "1", "A馬"), ("○", "2", "B馬")],
    )
    df = build_form_matrix_for_plan(
        plan, master, "20260301", horse_by_umaban={"1": "hid1"},
    )
    assert list(df.columns) == ["馬名", *FORM_RUN_COLUMNS]
    assert len(df) == 2
    assert "◎ 1番" in df.iloc[0]["馬名"]
    assert "C2" in df.iloc[0]["前走"]
    assert df.iloc[0]["2走"] != "—" or "C3" in df.iloc[0]["2走"]
    assert df.iloc[1]["前走"] == "—"


def test_form_matrix_html_multiline_visible():
    df = pd.DataFrame([{"馬名": "◎ 1番\nテスト", "前走": "2026.01.01 園田\nC3　【1着】"}])
    h = form_matrix_html(df)
    assert "<br>" in h
    assert "form-table" in h
    assert "テスト" in h


def test_build_form_tables_wrapper():
    plan = RaceBetPlan(
        race_id="r1",
        race_no=1,
        race_name="テスト",
        confidence="高",
        win_prob_top=0.9,
        prob_gap=0.7,
        marks=[("◎", "1", "A馬")],
    )
    master = pd.DataFrame(
        [
            {
                "horse_id": "hid1",
                "date": "20260101",
                "race_no": 1,
                "race_class": "C3",
                "finish": "2",
            },
        ]
    )
    blocks = build_form_tables_for_plan(
        plan, master, "20260201", horse_by_umaban={"1": "hid1"},
    )
    assert len(blocks) == 1
    _, table = blocks[0]
    assert "馬名" in table.columns
    assert "前走" in table.columns
