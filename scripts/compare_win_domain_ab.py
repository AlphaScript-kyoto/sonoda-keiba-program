"""A/B: style win model vs style + sanrenpuku domain features (split scoring)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import PROJECT_ROOT
from src.features.constants import DOMAIN_FEATURE_COLUMNS
from src.predictor.backtest import backtest_period
from src.predictor.scoring_config import (
    EXOTIC_WEIGHTS_PATH,
    WIN_WEIGHTS_PATH,
    ScoringConfig,
    load_split_scoring_configs,
)
from src.predictor.score import load_master

STYLE_DOMAIN_PATH = PROJECT_ROOT / "config" / "tuned_weights_style_domain.json"

DEFAULT_PERIODS = [
    ("2026/1-5", "20260101", "20260531"),
    ("2026/4-5", "20260401", "20260531"),
    ("2025通年", "20250101", "20251231"),
]


@dataclass(frozen=True)
class Variant:
    label: str
    win_config: ScoringConfig


def build_style_domain_config() -> ScoringConfig:
    """Style active set + domain columns with sanrenpuku weights."""
    style = ScoringConfig.load_tuned(WIN_WEIGHTS_PATH)
    sanren = ScoringConfig.load_tuned(EXOTIC_WEIGHTS_PATH)
    merged = dict(style.feature_weights)
    for feat in DOMAIN_FEATURE_COLUMNS:
        merged[feat] = sanren.feature_weights.get(feat, merged.get(feat, 0.0))
    active = set(style.active_features or style.feature_weights.keys())
    active |= set(DOMAIN_FEATURE_COLUMNS)
    return ScoringConfig(
        feature_weights=merged,
        market_weight=style.market_weight,
        normalize=style.normalize,
        active_features=active,
    )


def _variants() -> list[Variant]:
    _, exotic = load_split_scoring_configs()
    style = ScoringConfig.load_tuned(WIN_WEIGHTS_PATH)
    domain = (
        ScoringConfig.load_tuned(STYLE_DOMAIN_PATH)
        if STYLE_DOMAIN_PATH.exists()
        else build_style_domain_config()
    )
    return [
        Variant("style (現行単勝)", style),
        Variant("style+domain (三連のドメイン追加)", domain),
    ]


def _row(report) -> dict:
    w, p = report.win_pick, report.place_pick
    sp, st, wd = report.sanrenpuku, report.sanrentan, report.wide
    high = sum(1 for r in report.rows if r.confidence == "高")
    return {
        "races": report.race_count,
        "win_r": w.races,
        "win_roi": w.roi,
        "win_hit": w.hit_rate,
        "place_roi": p.roi,
        "place_hit": p.hit_rate,
        "sanren_roi": sp.roi,
        "sanrentan_roi": st.roi,
        "wide_roi": wd.roi,
        "high_conf": high,
    }


def _fmt_pct(v: float) -> str:
    if v != v:
        return "N/A"
    return f"{v:.1%}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Win model domain A/B backtest")
    parser.add_argument("--from", dest="from_date", default=None)
    parser.add_argument("--to", dest="to_date", default=None)
    parser.add_argument(
        "--save-domain-config",
        action="store_true",
        help="Write config/tuned_weights_style_domain.json from builder",
    )
    args = parser.parse_args()

    if args.save_domain_config:
        cfg = build_style_domain_config()
        cfg.save(STYLE_DOMAIN_PATH)
        print(f"Saved {STYLE_DOMAIN_PATH}")

    master = load_master()
    _, exotic_cfg = load_split_scoring_configs()
    variants = _variants()

    if args.from_date and args.to_date:
        periods = [(f"{args.from_date}-{args.to_date}", args.from_date, args.to_date)]
    else:
        periods = DEFAULT_PERIODS

    print("=== Win model A/B (三連=sanrenpuku 固定 / 単勝側のみ変更) ===")
    added = [f for f in DOMAIN_FEATURE_COLUMNS if f in (variants[1].win_config.active_features or set())]
    print("追加ドメイン:", ", ".join(added))
    print()

    for label, fr, to in periods:
        print(f"--- {label} ({fr}〜{to}) ---")
        print(
            f"{'モデル':<28} {'R':>5} {'単勝ROI':>8} {'複勝ROI':>8} "
            f"{'三連複':>8} {'三連単':>8} {'ワイド':>8} {'高自信':>6}"
        )
        rows = []
        for var in variants:
            report = backtest_period(
                fr,
                to,
                master=master,
                config=var.win_config,
                exotic_config=exotic_cfg,
            )
            r = _row(report)
            rows.append((var.label, r))
            print(
                f"{var.label:<28} {r['races']:>5} "
                f"{_fmt_pct(r['win_roi']):>8} {_fmt_pct(r['place_roi']):>8} "
                f"{_fmt_pct(r['sanren_roi']):>8} {_fmt_pct(r['sanrentan_roi']):>8} "
                f"{_fmt_pct(r['wide_roi']):>8} {r['high_conf']:>6}"
            )

        base, test = rows[0][1], rows[1][1]
        d_win = test["win_roi"] - base["win_roi"]
        d_place = test["place_roi"] - base["place_roi"]
        print(
            f"  delta (domain-style): 単勝 {d_win:+.1%}  複勝 {d_place:+.1%}  "
            f"(三連複 {test['sanren_roi'] - base['sanren_roi']:+.1%} ※印は三連モデル固定)"
        )
        print()


if __name__ == "__main__":
    main()
