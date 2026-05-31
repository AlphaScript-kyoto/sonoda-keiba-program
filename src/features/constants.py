"""特徴量列名の定数。"""

STYLE_FEATURE_COLUMNS = [
    "horse_style_score",
    "last3_avg_style_score",
    "style_front_ratio",
    "corner_pos_avg_last",
]

DOMAIN_COMPUTED_FEATURES = [
    "sonoda_waku_style_fit",
    "season_weight_score",
    "pace_style_fit",
    "sonoda_front_bonus",
]

DOMAIN_LOOKUP_FEATURES = frozenset(
    {
        "waku_distance_win_rate",
        "style_track_win_rate",
        "jockey_trainer_roi",
        "sire_win_rate",
        "dam_sire_win_rate",
    }
)

DOMAIN_FEATURE_COLUMNS = DOMAIN_COMPUTED_FEATURES + list(DOMAIN_LOOKUP_FEATURES)
