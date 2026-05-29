"""
raw 再取得 → 特徴量 → マスタ CSV まで一括実行。

ログ: data/processed/refresh_log.txt
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import scrape_range
from config.settings import HORSES_MASTER_PATH, REQUEST_INTERVAL_SEC
from src.features.build_features import build_and_save_all
from src.scraper.fetcher import fetch_range

LOG_PATH = ROOT / "data" / "processed" / "refresh_log.txt"


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except PermissionError:
        # PowerShell の Tee-Object で同じログを書いている場合にロックされることがある。
        pass


def main() -> None:
    try:
        LOG_PATH.write_text("", encoding="utf-8")
    except PermissionError:
        pass
    log("=== refresh_all 開始 ===")
    log(f"期間: {scrape_range.DATE_FROM} ～ {scrape_range.DATE_TO}")
    log(f"リクエスト間隔: {REQUEST_INTERVAL_SEC} 秒")

    log("STEP 1/2: netkeiba から raw CSV 更新（新列が無い日のみ再取得）")
    fetch_range(
        scrape_range.DATE_FROM,
        scrape_range.DATE_TO,
        save_csv=True,
        skip_existing=True,
        log_progress=True,
    )

    log("STEP 2/2: 特徴量計算 & マスタ CSV 作成")
    features_path, master_path = build_and_save_all()
    log(f"  features: {features_path}")
    log(f"  master:   {master_path}")

    import pandas as pd

    df = pd.read_csv(master_path, dtype=str, nrows=0)
    row_count = sum(1 for _ in open(master_path, encoding="utf-8-sig")) - 1
    log(f"  マスタ行数: {row_count:,} / 列数: {len(df.columns)}")
    log("=== refresh_all 完了 ===")


if __name__ == "__main__":
    main()
