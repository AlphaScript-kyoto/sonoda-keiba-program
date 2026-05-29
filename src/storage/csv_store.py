"""レースデータの CSV 保存。"""

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from config.settings import DATA_RAW_DIR

# 新列追加時は REQUIRED_COLUMNS に追加 → 再取得時に自動で差し替え
REQUIRED_COLUMNS = [
    "horse_id",
    "waku",
    "umaban",
    "margin",
    "weather",
    "race_class",
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
]


def horses_csv_path(date_yyyymmdd: str) -> Path:
    """日付別の馬データ CSV パス。例: data/raw/horses_20250525.csv"""
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_RAW_DIR / f"horses_{date_yyyymmdd}.csv"


def csv_has_required_columns(path: Path) -> bool:
    """必須列が揃い、少なくとも1行は値があるか。"""
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path, dtype=str, nrows=5)
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
        df_old = pd.read_csv(path, dtype=str)
        race_ids = df_new["race_id"].dropna().unique()
        df_old = df_old[~df_old["race_id"].isin(race_ids)]
        df = pd.concat([df_old, df_new], ignore_index=True)
        df = df.drop_duplicates(subset=["race_id", "horse_id"], keep="last")
    else:
        df = df_new

    for col in HORSE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[HORSE_COLUMNS]
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
