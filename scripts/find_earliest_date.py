"""園田の最古開催日を調べて表示する。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.sonoda_history import find_earliest_sonoda_date

if __name__ == "__main__":
    end = "20260522"
    earliest = find_earliest_sonoda_date(end)
    print(f"earliest={earliest} latest={end}")
