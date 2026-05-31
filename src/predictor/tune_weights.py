"""重み探索（正規化 z-score 前提）。学習期間は training_window に従う。"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.predictor.normalize import normalize_race_features, z_column
from src.predictor.scoring_config import DEFAULT_NORMALIZED_WEIGHTS, ScoringConfig
from src.predictor.score import compute_race_scores, enrich_master_rows, load_master
from src.predictor.training_window import get_training_ranges

ALL_FEATURE_NAMES = list(DEFAULT_NORMALIZED_WEIGHTS.keys())


def feature_names_for(config: ScoringConfig) -> List[str]:
    if config.active_features:
        return sorted(config.active_features)
    return list(ALL_FEATURE_NAMES)


@dataclass
class RaceCache:
    finish: np.ndarray
    features: np.ndarray
    market: np.ndarray
    sample_weight: float = 1.0


@dataclass
class TuneResult:
    config: ScoringConfig
    win_hit_rate: float
    top3_hit_rate: float
    races: int


def _prepare_enriched_races(
    master: pd.DataFrame,
    from_date: str,
    to_date: str,
) -> List[pd.DataFrame]:
    df = master[
        (master["date"].astype(str) >= from_date)
        & (master["date"].astype(str) <= to_date)
    ].copy()
    df["finish"] = pd.to_numeric(df["finish"], errors="coerce")

    races: List[pd.DataFrame] = []
    for _, day in df.groupby("date", sort=True):
        enriched = enrich_master_rows(day, master=master)
        for _, race in enriched.groupby("race_id", sort=False):
            if race["finish"].notna().any():
                races.append(race)
    return races


def _prepare_enriched_races_from_ranges(
    master: pd.DataFrame,
    ranges: List[Tuple[str, str]],
) -> List[pd.DataFrame]:
    races: List[pd.DataFrame] = []
    for from_date, to_date in ranges:
        races.extend(_prepare_enriched_races(master, from_date, to_date))
    return races


def prepare_enriched_races_for_reference(
    master: pd.DataFrame,
    reference_date: str,
) -> List[pd.DataFrame]:
    """2年前・1年前・当年YTD の3期間から学習用レースを構築。"""
    return _prepare_enriched_races_from_ranges(
        master, get_training_ranges(reference_date)
    )


def recency_weight(
    date_yyyymmdd: str,
    ref_date: str,
    *,
    half_life_days: int = 730,
) -> float:
    """ref_date からの経過日数で減衰（半減期既定2年）。"""
    ref = pd.to_datetime(ref_date, format="%Y%m%d")
    dt = pd.to_datetime(str(date_yyyymmdd), format="%Y%m%d")
    days_ago = max(0, (ref - dt).days)
    return 0.5 ** (days_ago / half_life_days)


def build_race_caches(
    races: List[pd.DataFrame],
    feature_names: Optional[List[str]] = None,
    *,
    ref_date: Optional[str] = None,
    use_recency: bool = False,
    half_life_days: int = 730,
) -> List[RaceCache]:
    """レースごとに z-score 済み特徴量行列を事前計算。"""
    feats = feature_names or ALL_FEATURE_NAMES
    caches: List[RaceCache] = []
    z_cols = [z_column(f) for f in feats]

    for race in races:
        norm = normalize_race_features(race, feats)
        norm = normalize_race_features(norm, ["market_score"])
        finish = pd.to_numeric(race["finish"], errors="coerce").to_numpy(dtype=float)
        feat_mat = norm[z_cols].to_numpy(dtype=float)
        market = norm[z_column("market_score")].to_numpy(dtype=float)
        sw = 1.0
        if use_recency and ref_date:
            sw = recency_weight(str(race["date"].iloc[0]), ref_date, half_life_days=half_life_days)
        caches.append(
            RaceCache(finish=finish, features=feat_mat, market=market, sample_weight=sw)
        )
    return caches


def _eval_weight_vector(
    caches: List[RaceCache],
    weights: np.ndarray,
    market_weight: float,
    *,
    weighted: bool = False,
) -> Tuple[float, float, int]:
    hits = 0.0
    top3 = 0.0
    total_w = 0.0
    total = len(caches)
    for rc in caches:
        scores = rc.features @ weights + market_weight * rc.market
        pred = int(np.argmax(scores))
        w = rc.sample_weight if weighted else 1.0
        if rc.finish[pred] == 1:
            hits += w
        k = min(3, len(scores))
        top_idx = np.argpartition(-scores, k - 1)[:k]
        if np.any(rc.finish[top_idx] == 1):
            top3 += w
        total_w += w

    if weighted and total_w > 0:
        return hits / total_w, top3 / total_w, total
    if total == 0:
        return 0.0, 0.0, 0
    return hits / total, top3 / total, total


def _config_to_vectors(
    config: ScoringConfig, feature_names: Optional[List[str]] = None
) -> Tuple[np.ndarray, float]:
    names = feature_names or feature_names_for(config)
    w = config.weights_for_scoring()
    vec = np.array([w.get(f, 0.0) for f in names], dtype=float)
    return vec, float(config.market_weight)


def _vectors_to_config(
    vec: np.ndarray,
    market_weight: float,
    feature_names: List[str],
    base: Optional[ScoringConfig] = None,
) -> ScoringConfig:
    weights = dict(base.feature_weights if base else DEFAULT_NORMALIZED_WEIGHTS)
    for i, f in enumerate(feature_names):
        weights[f] = float(vec[i])
    return ScoringConfig(
        feature_weights=weights,
        market_weight=market_weight,
        normalize=True,
        active_features=base.active_features if base else None,
    )


def _random_config(
    rng: random.Random, feature_names: List[str], base: Optional[ScoringConfig] = None
) -> ScoringConfig:
    weights = dict(base.feature_weights if base else DEFAULT_NORMALIZED_WEIGHTS)
    for f in feature_names:
        weights[f] = rng.choice([0.0, 0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0])
    market = base.market_weight if base else rng.choice([0.5, 1.0, 1.5, 2.0, 2.5])
    return ScoringConfig(
        feature_weights=weights,
        market_weight=market,
        normalize=True,
        active_features=base.active_features if base else set(feature_names),
    )


def _mutate_config(
    cfg: ScoringConfig, rng: random.Random, feature_names: List[str]
) -> ScoringConfig:
    weights = dict(cfg.feature_weights)
    feat = rng.choice(feature_names)
    weights[feat] = rng.choice([0.0, 0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5])
    market = cfg.market_weight
    if rng.random() < 0.2:
        market = rng.choice([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    return ScoringConfig(
        feature_weights=weights,
        market_weight=market,
        normalize=True,
        active_features=cfg.active_features,
    )


def evaluate_raw_config_on_races(
    races: List[pd.DataFrame], config: ScoringConfig
) -> TuneResult:
    """非正規化設定用の評価。"""
    hits = 0
    top3 = 0
    total = 0
    for race in races:
        valid = race.dropna(subset=["finish"])
        if valid.empty:
            continue
        scores = compute_race_scores(race, config)
        pred_idx = scores.idxmax()
        if valid.loc[pred_idx, "finish"] == 1:
            hits += 1
        top = scores.nlargest(min(3, len(scores))).index
        if (valid.loc[top, "finish"] == 1).any():
            top3 += 1
        total += 1
    return TuneResult(
        config=config,
        win_hit_rate=hits / total if total else 0.0,
        top3_hit_rate=top3 / total if total else 0.0,
        races=total,
    )


def evaluate_config_on_races(
    races: List[pd.DataFrame], config: ScoringConfig
) -> TuneResult:
    if not config.normalize:
        return evaluate_raw_config_on_races(races, config)
    names = feature_names_for(config)
    caches = build_race_caches(races, feature_names=names)
    return evaluate_config_on_caches(caches, config, feature_names=names)


def evaluate_config_on_caches(
    caches: List[RaceCache],
    config: ScoringConfig,
    *,
    weighted: bool = False,
    feature_names: Optional[List[str]] = None,
) -> TuneResult:
    names = feature_names or feature_names_for(config)
    vec, mw = _config_to_vectors(config, names)
    win_rate, top3_rate, total = _eval_weight_vector(caches, vec, mw, weighted=weighted)
    return TuneResult(
        config=config,
        win_hit_rate=win_rate,
        top3_hit_rate=top3_rate,
        races=total,
    )


def tune_weights_random_search(
    from_date: str = "20240101",
    to_date: str = "20241231",
    *,
    reference_date: Optional[str] = None,
    n_iter: int = 400,
    seed: int = 42,
    master: Optional[pd.DataFrame] = None,
    use_recency: bool = False,
    ref_date: Optional[str] = None,
    half_life_days: int = 730,
    base_config: Optional[ScoringConfig] = None,
) -> Tuple[List[TuneResult], List[RaceCache]]:
    master = master if master is not None else load_master()
    base = base_config or ScoringConfig()
    names = feature_names_for(base)
    if reference_date:
        ref = ref_date or reference_date
        races = prepare_enriched_races_for_reference(master, reference_date)
    else:
        ref = ref_date or to_date
        races = _prepare_enriched_races(master, from_date, to_date)
    caches = build_race_caches(
        races,
        feature_names=names,
        ref_date=ref,
        use_recency=use_recency,
        half_life_days=half_life_days,
    )
    rng = random.Random(seed)
    weighted_metric = use_recency

    results: List[TuneResult] = []
    best: Optional[TuneResult] = None

    for i in range(n_iter):
        cfg = (
            _random_config(rng, names, base)
            if i < n_iter // 2 or best is None
            else _mutate_config(best.config, rng, names)
        )
        res = evaluate_config_on_caches(caches, cfg, weighted=weighted_metric, feature_names=names)
        results.append(res)
        if best is None or res.win_hit_rate > best.win_hit_rate or (
            res.win_hit_rate == best.win_hit_rate and res.top3_hit_rate > best.top3_hit_rate
        ):
            best = res

    results.sort(key=lambda r: (r.win_hit_rate, r.top3_hit_rate), reverse=True)
    return results, caches


def tune_weights_coordinate(
    caches: List[RaceCache],
    start: ScoringConfig,
    *,
    market_candidates: Optional[List[float]] = None,
    max_rounds: int = 2,
    weighted: bool = False,
    feature_names: Optional[List[str]] = None,
) -> TuneResult:
    names = feature_names or feature_names_for(start)
    market_candidates = market_candidates or [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    best = evaluate_config_on_caches(caches, start, weighted=weighted, feature_names=names)

    for _ in range(max_rounds):
        improved = False
        vec, mw = _config_to_vectors(best.config, names)

        for i, feat in enumerate(names):
            for w in [0.0, 0.5, 1.0, 1.5, 2.0]:
                trial = vec.copy()
                trial[i] = w
                win_rate, top3_rate, total = _eval_weight_vector(
                    caches, trial, mw, weighted=weighted
                )
                if win_rate > best.win_hit_rate or (
                    win_rate == best.win_hit_rate and top3_rate > best.top3_hit_rate
                ):
                    best = TuneResult(
                        config=_vectors_to_config(trial, mw, names, base=best.config),
                        win_hit_rate=win_rate,
                        top3_hit_rate=top3_rate,
                        races=total,
                    )
                    vec = trial.copy()
                    improved = True

        for m in market_candidates:
            win_rate, top3_rate, total = _eval_weight_vector(
                caches, vec, m, weighted=weighted
            )
            if win_rate > best.win_hit_rate or (
                win_rate == best.win_hit_rate and top3_rate > best.top3_hit_rate
            ):
                best = TuneResult(
                    config=_vectors_to_config(vec, m, names, base=best.config),
                    win_hit_rate=win_rate,
                    top3_hit_rate=top3_rate,
                    races=total,
                )
                mw = m
                improved = True

        if not improved:
            break

    return best


def tune_and_refine(
    from_date: str = "20240101",
    to_date: str = "20241231",
    *,
    reference_date: Optional[str] = None,
    n_iter: int = 300,
    master: Optional[pd.DataFrame] = None,
    use_recency: bool = False,
    ref_date: Optional[str] = None,
    half_life_days: int = 730,
    seed: int = 42,
) -> TuneResult:
    """ランダム探索 + 座標探索を一括実行。"""
    results, caches = tune_weights_random_search(
        from_date,
        to_date,
        reference_date=reference_date,
        n_iter=n_iter,
        seed=seed,
        master=master,
        use_recency=use_recency,
        ref_date=ref_date,
        half_life_days=half_life_days,
    )
    return tune_weights_coordinate(
        caches,
        results[0].config,
        weighted=use_recency,
    )


def tune_and_refine_for_reference(
    reference_date: str,
    *,
    n_iter: int = 400,
    master: Optional[pd.DataFrame] = None,
    seed: int = 42,
    base_config: Optional[ScoringConfig] = None,
) -> Tuple[TuneResult, List[RaceCache], List[Tuple[str, str]]]:
    """2年前・1年前・当年YTD で重みを探索し、結果とキャッシュを返す。"""
    ranges = get_training_ranges(reference_date)
    base = base_config or ScoringConfig()
    names = feature_names_for(base)
    results, caches = tune_weights_random_search(
        reference_date=reference_date,
        n_iter=n_iter,
        seed=seed,
        master=master,
        base_config=base,
    )
    refined = tune_weights_coordinate(caches, results[0].config, feature_names=names)
    return refined, caches, ranges
