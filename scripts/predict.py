"""簡易予想スクリプト（馬名別勝率）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.win_rate import calc_horse_win_rates


def main() -> None:
    rates = calc_horse_win_rates()
    print("=== 馬名別 1着率（上位20） ===")
    print(rates.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
