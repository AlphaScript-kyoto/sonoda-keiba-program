"""スコアリング設定・重み定義。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

from config.settings import PROJECT_ROOT
from src.features.constants import DOMAIN_FEATURE_COLUMNS, STYLE_FEATURE_COLUMNS

WEIGHTS_CONFIG_PATH = PROJECT_ROOT / "config" / "tuned_weights.json"

# Phase A+B 追加前（8特徴量・非正規化）
LEGACY_FEATURE_WEIGHTS: Dict[str, float] = {
    "horse_win_rate": 4.0,
    "horse_win_rate_distance": 2.5,
    "horse_win_rate_track": 2.0,
    "jockey_trainer_win_rate": 2.2,
    "jockey_win_rate": 1.5,
    "last3_avg_finish": -0.6,
    "last5_avg_finish": -0.4,
    "days_since_last": -0.015,
}
LEGACY_MARKET_WEIGHT = 0.35

# 非正規化・全特徴量（Phase A+B 追加直後の手設定）
RAW_FEATURE_WEIGHTS: Dict[str, float] = {
    **LEGACY_FEATURE_WEIGHTS,
    "trainer_win_rate": 1.8,
    "last3_avg_last3f": -0.08,
    "horse_best_last3f": -0.05,
    "last3_avg_popularity": -0.15,
    "last_avg_body_weight": -0.002,
    "last_body_weight_delta": -0.02,
    "entry_carried_weight": -0.04,
    "entry_body_weight_delta": -0.015,
    "body_weight_vs_avg": -0.003,
    "last3_avg_margin": -0.15,
    "last3_avg_time_index": -0.02,
    "horse_best_time_index": -0.02,
    "entry_waku": 0.05,
    "entry_head_count": -0.03,
    "waku_win_rate": 0.8,
}
RAW_MARKET_WEIGHT = 0.35

STYLE_ONLY_WEIGHTS: Dict[str, float] = {
    "horse_style_score": 1.2,
    "last3_avg_style_score": 1.0,
    "style_front_ratio": 0.8,
    "corner_pos_avg_last": 0.6,
}
DOMAIN_ONLY_WEIGHTS: Dict[str, float] = {
    "waku_distance_win_rate": 0.7,
    "style_track_win_rate": 0.8,
    "jockey_trainer_roi": 1.0,
    "sonoda_waku_style_fit": 1.1,
    "season_weight_score": 0.4,
    "pace_style_fit": 0.6,
    "sonoda_front_bonus": 0.9,
    "sire_win_rate": 0.9,
    "dam_sire_win_rate": 0.4,
}

# 正規化後の初期重み（チューニング前の均等寄り）
DEFAULT_NORMALIZED_WEIGHTS: Dict[str, float] = {
    "horse_win_rate": 2.0,
    "horse_win_rate_distance": 1.5,
    "horse_win_rate_track": 1.2,
    "jockey_trainer_win_rate": 1.3,
    "jockey_win_rate": 1.0,
    "trainer_win_rate": 0.8,
    "last3_avg_finish": 1.0,
    "last5_avg_finish": 0.8,
    "days_since_last": 0.3,
    "last3_avg_last3f": 1.2,
    "horse_best_last3f": 0.8,
    "last3_avg_popularity": 0.5,
    "last_avg_body_weight": 0.2,
    "last_body_weight_delta": 0.3,
    "entry_carried_weight": 0.4,
    "entry_body_weight_delta": 0.3,
    "body_weight_vs_avg": 0.2,
    "last3_avg_margin": 0.6,
    "last3_avg_time_index": 0.8,
    "horse_best_time_index": 0.7,
    "entry_waku": 0.3,
    "entry_head_count": 0.2,
    "waku_win_rate": 0.5,
    **STYLE_ONLY_WEIGHTS,
    **DOMAIN_ONLY_WEIGHTS,
}
DEFAULT_NORMALIZED_MARKET_WEIGHT = 1.5

BASE_FEATURE_NAMES = frozenset(
    k
    for k in DEFAULT_NORMALIZED_WEIGHTS
    if k not in STYLE_FEATURE_COLUMNS and k not in DOMAIN_FEATURE_COLUMNS
)


@dataclass
class ScoringConfig:
    feature_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_NORMALIZED_WEIGHTS)
    )
    market_weight: float = DEFAULT_NORMALIZED_MARKET_WEIGHT
    normalize: bool = True
    active_features: Optional[Set[str]] = None

    def weights_for_scoring(self) -> Dict[str, float]:
        if self.active_features is not None:
            return {k: v for k, v in self.feature_weights.items() if k in self.active_features}
        return dict(self.feature_weights)

    def to_dict(self) -> dict:
        return {
            "feature_weights": self.feature_weights,
            "market_weight": self.market_weight,
            "normalize": self.normalize,
            "active_features": sorted(self.active_features) if self.active_features else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoringConfig":
        active = d.get("active_features")
        return cls(
            feature_weights=d.get("feature_weights", dict(DEFAULT_NORMALIZED_WEIGHTS)),
            market_weight=float(d.get("market_weight", DEFAULT_NORMALIZED_MARKET_WEIGHT)),
            normalize=bool(d.get("normalize", True)),
            active_features=set(active) if active else None,
        )

    @classmethod
    def legacy(cls) -> "ScoringConfig":
        return cls(
            feature_weights=dict(LEGACY_FEATURE_WEIGHTS),
            market_weight=LEGACY_MARKET_WEIGHT,
            normalize=False,
            active_features=set(LEGACY_FEATURE_WEIGHTS.keys()),
        )

    @classmethod
    def raw_all_features(cls) -> "ScoringConfig":
        return cls(
            feature_weights=dict(RAW_FEATURE_WEIGHTS),
            market_weight=RAW_MARKET_WEIGHT,
            normalize=False,
        )

    @classmethod
    def load_tuned(cls, path: Optional[Path] = None) -> "ScoringConfig":
        path = path or WEIGHTS_CONFIG_PATH
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def current_baseline(cls) -> "ScoringConfig":
        """現行モデル（脚質・ドメイン知識なし）。"""
        cfg = cls.load_tuned()
        merged = {**dict(DEFAULT_NORMALIZED_WEIGHTS), **cfg.feature_weights}
        cfg.feature_weights = merged
        cfg.active_features = set(BASE_FEATURE_NAMES)
        return cfg

    @classmethod
    def with_style(cls) -> "ScoringConfig":
        """脚質特徴量を追加（ドメイン知識なし）。"""
        cfg = cls.current_baseline()
        cfg.active_features = set(BASE_FEATURE_NAMES) | set(STYLE_FEATURE_COLUMNS)
        return cfg

    @classmethod
    def with_style_and_domain(cls) -> "ScoringConfig":
        """脚質 + 園田ドメイン知識。"""
        cfg = cls.current_baseline()
        cfg.active_features = (
            set(BASE_FEATURE_NAMES)
            | set(STYLE_FEATURE_COLUMNS)
            | set(DOMAIN_FEATURE_COLUMNS)
        )
        return cfg

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or WEIGHTS_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path
