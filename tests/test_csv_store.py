"""CSV 保存のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.csv_store import (
    HORSE_COLUMN_LABELS,
    _format_excel_text,
    _parse_excel_text,
    append_horses_csv,
    read_horses_csv,
)


def test_margin_excel_text_roundtrip():
    assert _format_excel_text("0.1") == '="0.1"'
    assert _format_excel_text("1.3/4") == '="1.3/4"'
    assert _format_excel_text("") == ""
    assert _parse_excel_text('="0.1"') == "0.1"
    assert _parse_excel_text("1.3/4") == "1.3/4"


def test_append_horses_csv_japanese_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.storage.csv_store.DATA_RAW_DIR",
        tmp_path,
    )
    rows = [
        {
            "race_id": "202650052201",
            "date": "20260522",
            "race_no": 1,
            "horse_id": "2018110078",
            "horse_url": "https://example.com/horse/2018110078",
            "horse_name": "テスト馬",
            "sex_age": "牝8",
            "waku": "8",
            "umaban": "9",
            "finish": 1,
            "race_time": "1:34.8",
            "margin": "0.1",
            "popularity": "1",
            "odds": "2.3",
            "last_3f": "41.8",
            "carried_weight": "54.0",
            "body_weight": "456(+2)",
            "distance": "1400m",
            "track": "重",
            "direction": "右",
            "surface": "ダ",
            "weather": "晴",
            "head_count": "10",
            "race_condition": "3歳以上",
            "race_class": "C3",
            "race_name": "テストレース",
            "jockey": "テスト騎手",
            "trainer": "テスト調教師",
        }
    ]

    path = append_horses_csv(rows, "20260522")
    saved = path.read_text(encoding="utf-8-sig")
    assert HORSE_COLUMN_LABELS["horse_id"] in saved.splitlines()[0]
    assert HORSE_COLUMN_LABELS["margin"] in saved.splitlines()[0]
    assert '="0.1"' in saved

    loaded = read_horses_csv(path)
    assert loaded.loc[0, "horse_id"] == "2018110078"
    assert loaded.loc[0, "margin"] == "0.1"


if __name__ == "__main__":
    test_margin_excel_text_roundtrip()
    print("ok")
