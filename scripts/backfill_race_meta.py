"""脚質・ラップ・血統キャッシュのバックフィル。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.scraper.bloodline import fetch_bloodlines, load_bloodline_cache
from src.scraper.client import NetkeibaBlockedError
from src.scraper.race_lap import fetch_race_laps, load_lap_cache
from src.scraper.running_style import fetch_race_styles, load_style_cache


def _race_ids_in_range(master, from_date: str, to_date: str) -> list[str]:
    df = master[
        (master["date"].astype(str) >= from_date)
        & (master["date"].astype(str) <= to_date)
    ]
    return sorted(df["race_id"].astype(str).unique().tolist())


def _missing_style(race_ids: list[str]) -> list[str]:
    cache = load_style_cache()
    return [r for r in race_ids if r not in cache]


def _missing_lap(race_ids: list[str]) -> list[str]:
    cache = load_lap_cache()
    return [r for r in race_ids if r not in cache]


def _missing_bloodline(horse_ids: list[str]) -> list[str]:
    cache = load_bloodline_cache()
    return [h for h in horse_ids if h and h not in cache]


def main() -> None:
    parser = argparse.ArgumentParser(description="脚質・ラップ・血統キャッシュを取得")
    parser.add_argument("--from", dest="from_date", default="20240101")
    parser.add_argument("--to", dest="to_date", default="20260531")
    parser.add_argument("--skip-style", action="store_true")
    parser.add_argument("--skip-lap", action="store_true")
    parser.add_argument("--skip-bloodline", action="store_true")
    parser.add_argument("--bloodline-limit", type=int, default=500)
    args = parser.parse_args()

    master = load_master()
    race_ids = _race_ids_in_range(master, args.from_date, args.to_date)
    print(f"対象レース: {len(race_ids)} ({args.from_date}〜{args.to_date})")

    try:
        if not args.skip_style:
            missing = _missing_style(race_ids)
            print(f"脚質 未取得: {len(missing)}件")
            if missing:
                fetch_race_styles(missing)
                print(f"脚質キャッシュ: {len(load_style_cache())}件")

        if not args.skip_lap:
            missing = _missing_lap(race_ids)
            print(f"ラップ 未取得: {len(missing)}件")
            if missing:
                fetch_race_laps(missing)
                print(f"ラップキャッシュ: {len(load_lap_cache())}件")

        if not args.skip_bloodline:
            horses = master[
                (master["date"].astype(str) >= args.from_date)
                & (master["date"].astype(str) <= args.to_date)
            ]["horse_id"].astype(str).unique().tolist()
            missing_h = _missing_bloodline(horses)[: args.bloodline_limit]
            print(f"血統 未取得: {len(missing_h)}件（上限 {args.bloodline_limit}）")
            if missing_h:
                fetch_bloodlines(missing_h)
                print(f"血統キャッシュ: {len(load_bloodline_cache())}件")
    except NetkeibaBlockedError as exc:
        print(f"STOP: HTTP 400 — 通信制限 ({exc})")
        sys.exit(1)

    print("完了。続けて python scripts/build_features.py を実行してください。")


if __name__ == "__main__":
    main()
