"""レースデータの CSV 保存。"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_MARGIN_MONTH_DAY_RE = re.compile(r"^(\d{1,2})月(\d{1,2})日$")
_MARGIN_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")

from config.settings import DATA_RAW_DIR

# 新列追加時は REQUIRED_COLUMNS に追加 → 再取得時に自動で差し替え
REQUIRED_COLUMNS = [
    "horse_id",
    "waku",
    "umaban",
    "margin",
    "weather",
    "race_class",
    "jockey_id",
]

HORSE_COLUMNS = [
    "race_id",
    "date",
    "race_no",
    "horse_id",
    "horse_url",
    "horse_name",
    "sex_age",
    "waku",
    "umaban",
    "finish",
    "race_time",
    "margin",
    "popularity",
    "odds",
    "last_3f",
    "carried_weight",
    "body_weight",
    "distance",
    "track",
    "direction",
    "surface",
    "weather",
    "head_count",
    "race_condition",
    "race_class",
    "race_name",
    "jockey",
    "trainer",
    "jockey_id",
    "trainer_id",
    "post_time",
    "place_odds",
    "race_pace",
    "corner_pos_1",
    "corner_pos_2",
    "corner_pos_3",
    "corner_pos_4",
]

HORSE_COLUMN_LABELS: Dict[str, str] = {
    "race_id": "レースID",
    "date": "日付",
    "race_no": "レース番号",
    "horse_id": "馬ID",
    "horse_url": "馬URL",
    "horse_name": "馬名",
    "sex_age": "性齢",
    "waku": "枠番",
    "umaban": "馬番",
    "finish": "着順",
    "race_time": "走破タイム",
    "margin": "着差",
    "popularity": "人気",
    "odds": "オッズ",
    "last_3f": "上がり3F",
    "carried_weight": "斤量",
    "body_weight": "馬体重",
    "distance": "距離",
    "track": "馬場",
    "direction": "回り",
    "surface": "芝ダ",
    "weather": "天候",
    "head_count": "頭数",
    "race_condition": "競馬条件",
    "race_class": "クラス",
    "race_name": "レース名",
    "jockey": "騎手",
    "trainer": "調教師",
    "jockey_id": "騎手ID",
    "trainer_id": "調教師ID",
    "post_time": "発走時刻",
    "place_odds": "複勝オッズ",
    "race_pace": "ペース",
    "corner_pos_1": "通過1",
    "corner_pos_2": "通過2",
    "corner_pos_3": "通過3",
    "corner_pos_4": "通過4",
}

JAPANESE_TO_ENGLISH = {ja: en for en, ja in HORSE_COLUMN_LABELS.items()}


def horses_csv_path(date_yyyymmdd: str) -> Path:
    """日付別の馬データ CSV パス。例: data/raw/horses_20250525.csv"""
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_RAW_DIR / f"horses_{date_yyyymmdd}.csv"


def _format_excel_text(value: Any) -> str:
    """Excel が数値・日付と誤認しない文字列形式に変換する。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith('="') and text.endswith('"'):
        return text
    return f'="{text}"'


def _parse_excel_text(value: Any) -> str:
    """Excel 用文字列形式を通常の文字列に戻す。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.startswith('="') and text.endswith('"'):
        return text[2:-1]
    return text


def normalize_margin_value(value: Any) -> str:
    """
    着差を netkeiba 表記に揃える。
    Excel が 3/4 を日付化した「3月4日」「2026-03-04」等を 3/4 形式へ戻す。
    """
    text = _parse_excel_text(value)
    if not text:
        return ""

    m = _MARGIN_MONTH_DAY_RE.match(text)
    if m:
        return f"{int(m.group(1))}/{int(m.group(2))}"

    m = _MARGIN_ISO_DATE_RE.match(text)
    if m:
        return f"{int(m.group(2))}/{int(m.group(3))}"

    return text


def normalize_horses_columns(df: pd.DataFrame) -> pd.DataFrame:
    """日本語ヘッダーを内部用の英語列名に揃える（旧形式の英語ヘッダーもそのまま通す）。"""
    rename = {
        col: JAPANESE_TO_ENGLISH[col]
        for col in df.columns
        if col in JAPANESE_TO_ENGLISH
    }
    if rename:
        df = df.rename(columns=rename)
    return df


def read_horses_csv(path: Path, *, nrows: Optional[int] = None) -> pd.DataFrame:
    """raw 馬 CSV を読み込み、内部処理用の英語列名に正規化する。"""
    df = pd.read_csv(path, dtype=str, nrows=nrows)
    df = normalize_horses_columns(df)
    if "margin" in df.columns:
        df["margin"] = df["margin"].map(normalize_margin_value)
    return df


def _prepare_horses_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    """保存用に列順・着差の Excel 文字列形式・日本語ヘッダーを整える。"""
    out = df.copy()
    for col in HORSE_COLUMNS:
        if col not in out.columns:
            out[col] = None
    out = out[HORSE_COLUMNS]
    out["margin"] = out["margin"].map(normalize_margin_value).map(_format_excel_text)
    return out.rename(columns=HORSE_COLUMN_LABELS)


def csv_has_required_columns(path: Path) -> bool:
    """必須列が揃い、少なくとも1行は値があるか。"""
    if not path.exists():
        return False
    try:
        df = read_horses_csv(path, nrows=5)
        if len(df) == 0:
            return False
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                return False
            if col == "horse_id":
                if not df[col].fillna("").astype(str).str.len().gt(0).any():
                    return False
            elif not df[col].fillna("").astype(str).str.len().gt(0).any():
                return False
        return True
    except Exception:
        return False


def append_horses_csv(rows: List[Dict[str, Any]], date_yyyymmdd: str) -> Path:
    """馬データを日付別 CSV に追記（既存ファイルがあれば結合）。"""
    path = horses_csv_path(date_yyyymmdd)
    df_new = pd.DataFrame(rows)

    if path.exists():
        df_old = read_horses_csv(path)
        race_ids = df_new["race_id"].dropna().unique()
        df_old = df_old[~df_old["race_id"].isin(race_ids)]
        df = pd.concat([df_old, df_new], ignore_index=True)
        df = df.drop_duplicates(subset=["race_id", "horse_id"], keep="last")
    else:
        df = df_new

    df = _prepare_horses_for_csv(df)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
