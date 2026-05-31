"""特徴量スコアによるレース予想。"""



from __future__ import annotations



from pathlib import Path

from typing import Dict, List, Optional



import numpy as np

import pandas as pd



from config.settings import HORSES_MASTER_PATH

from src.features.build_features import (
    FEATURE_COLUMNS,
    jockey_trainer_pair_key,
    parse_body_weight,
)
from src.features.sonoda_domain import (
    DOMAIN_LOOKUP_FEATURES,
    apply_domain_lookups,
)
from src.scraper.race_lap import load_lap_cache
from src.scraper.running_style import parse_kyakushitsu_from_shutuba, style_to_score

from src.predictor.normalize import normalize_race_features, z_column

from src.predictor.scoring_config import (

    DEFAULT_NORMALIZED_MARKET_WEIGHT,

    DEFAULT_NORMALIZED_WEIGHTS,

    ScoringConfig,

)

from src.scraper.race_list import list_race_ids_for_shutuba

from src.scraper.shutuba import fetch_shutuba_html, parse_shutuba



# 後方互換（import 用）

FEATURE_WEIGHTS: Dict[str, float] = dict(DEFAULT_NORMALIZED_WEIGHTS)

MARKET_WEIGHT = DEFAULT_NORMALIZED_MARKET_WEIGHT



_LOOKUP_FEATURES = frozenset(
    {
        "jockey_trainer_win_rate",
        "trainer_win_rate",
        "waku_win_rate",
        *DOMAIN_LOOKUP_FEATURES,
    }
)



_DEFAULT_CONFIG: Optional[ScoringConfig] = None





def get_scoring_config() -> ScoringConfig:

    global _DEFAULT_CONFIG

    if _DEFAULT_CONFIG is None:

        _DEFAULT_CONFIG = ScoringConfig.load_tuned()

    return _DEFAULT_CONFIG





def set_scoring_config(config: ScoringConfig) -> None:

    global _DEFAULT_CONFIG

    _DEFAULT_CONFIG = config





def _softmax_series(s: pd.Series) -> pd.Series:

    if s.notna().sum() == 0:

        return pd.Series(np.nan, index=s.index)

    filled = s.fillna(s.min() - 1.0)

    exp = np.exp(filled - filled.max())

    return exp / exp.sum()





def load_master(path: Optional[Path] = None) -> pd.DataFrame:

    path = path or HORSES_MASTER_PATH

    if not path.exists():

        raise FileNotFoundError(

            f"{path} がありません。先に python scripts/build_features.py を実行してください。"

        )

    return pd.read_csv(path, dtype=str)





def _latest_features(master: pd.DataFrame, before_date: str) -> pd.DataFrame:

    """指定日より前の各馬の最新特徴量行（騎手×調教師・調教師単独は除く）。"""

    horse_features = [c for c in FEATURE_COLUMNS if c not in _LOOKUP_FEATURES]

    hist = master[master["date"].astype(str) < before_date].copy()

    if hist.empty:

        return pd.DataFrame(columns=["horse_id", *horse_features])

    hist["race_no"] = pd.to_numeric(hist["race_no"], errors="coerce")

    hist = hist.sort_values(["horse_id", "date", "race_no"])

    cols = ["horse_id", *horse_features]

    return hist.groupby("horse_id", as_index=False).tail(1)[cols]





def _lookup_jockey_trainer_win_rates(

    master: pd.DataFrame, before_date: str

) -> Dict[str, float]:

    hist = master[master["date"].astype(str) < before_date].copy()

    if hist.empty:

        return {}



    pair = jockey_trainer_pair_key(hist["jockey"], hist["trainer"])

    jockey = hist["jockey"].fillna("").astype(str).str.strip()

    trainer = hist["trainer"].fillna("").astype(str).str.strip()

    valid = jockey.str.len().gt(0) & trainer.str.len().gt(0)

    hist = hist.loc[valid].copy()

    pair = pair.loc[valid]

    if hist.empty:

        return {}



    finish = pd.to_numeric(hist["finish"], errors="coerce")

    stats = pd.DataFrame({"pair": pair, "win": finish == 1})

    grouped = stats.groupby("pair", sort=False)

    rates = grouped["win"].sum() / grouped.size()

    return rates.astype(float).to_dict()





def _lookup_trainer_win_rates(

    master: pd.DataFrame, before_date: str

) -> Dict[str, float]:

    hist = master[master["date"].astype(str) < before_date].copy()

    if hist.empty:

        return {}



    trainer = hist["trainer"].fillna("").astype(str).str.strip()

    valid = trainer.str.len().gt(0)

    hist = hist.loc[valid].copy()

    trainer = trainer.loc[valid]

    if hist.empty:

        return {}



    finish = pd.to_numeric(hist["finish"], errors="coerce")

    stats = pd.DataFrame({"trainer": trainer, "win": finish == 1})

    grouped = stats.groupby("trainer", sort=False)

    rates = grouped["win"].sum() / grouped.size()

    return rates.astype(float).to_dict()





def _lookup_waku_win_rates(

    master: pd.DataFrame, before_date: str

) -> Dict[str, float]:

    hist = master[master["date"].astype(str) < before_date].copy()

    if hist.empty:

        return {}



    waku = pd.to_numeric(hist.get("waku", pd.Series(dtype=str)), errors="coerce")

    valid = waku.notna()

    hist = hist.loc[valid].copy()

    waku = waku.loc[valid].astype(int).astype(str)

    if hist.empty:

        return {}



    finish = pd.to_numeric(hist["finish"], errors="coerce")

    stats = pd.DataFrame({"waku": waku, "win": finish == 1})

    grouped = stats.groupby("waku", sort=False)

    rates = grouped["win"].sum() / grouped.size()

    return rates.astype(float).to_dict()





def _attach_entry_race_context(df: pd.DataFrame) -> pd.DataFrame:

    out = df.copy()

    out["entry_waku"] = pd.to_numeric(out.get("waku", pd.Series(dtype=str)), errors="coerce")

    head = pd.to_numeric(out.get("head_count", pd.Series(dtype=str)), errors="coerce")

    if "race_id" in out.columns:

        runner_count = out.groupby("race_id")["horse_id"].transform("count")

        out["entry_head_count"] = head.fillna(runner_count)

    else:

        out["entry_head_count"] = head

    return out





def _apply_waku_win_rate(

    df: pd.DataFrame, waku_rates: Dict[str, float]

) -> pd.DataFrame:

    out = df.copy()

    waku_key = pd.to_numeric(out.get("waku", pd.Series(dtype=str)), errors="coerce")

    out["waku_win_rate"] = waku_key.map(

        lambda w: waku_rates.get(str(int(w)), np.nan) if pd.notna(w) else np.nan

    )

    return out





def _attach_entry_physicals(df: pd.DataFrame) -> pd.DataFrame:

    out = df.copy()

    if "body_weight" in out.columns:

        parsed = out["body_weight"].apply(parse_body_weight)

        out["entry_body_weight"] = parsed.apply(lambda t: t[0])

        out["entry_body_weight_delta"] = parsed.apply(lambda t: t[1])

    else:

        out["entry_body_weight"] = np.nan

        out["entry_body_weight_delta"] = np.nan



    out["entry_carried_weight"] = pd.to_numeric(

        out.get("carried_weight", pd.Series(dtype=str)), errors="coerce"

    )

    avg_bw = pd.to_numeric(out.get("last_avg_body_weight"), errors="coerce")

    out["body_weight_vs_avg"] = out["entry_body_weight"] - avg_bw

    return out





def _market_score(odds: pd.Series) -> pd.Series:

    numeric = pd.to_numeric(odds, errors="coerce")

    with np.errstate(divide="ignore", invalid="ignore"):

        score = 1.0 / numeric

    return score.replace([np.inf, -np.inf], np.nan)





def _race_lap_pace(race_id: str) -> str:
    lap = load_lap_cache().get(str(race_id), {})
    return str(lap.get("pace", ""))


def enrich_master_rows(
    entries: pd.DataFrame,
    master: Optional[pd.DataFrame] = None,
    *,
    use_domain: bool = True,
) -> pd.DataFrame:
    """マスタ行（特徴量列済み）に当日斤量・オッズスコア等を付与。"""
    if entries.empty:
        return entries
    out = _attach_entry_physicals(entries)
    out = _attach_entry_race_context(out)
    if master is not None:
        before_date = str(entries["date"].iloc[0])
        waku_rates = _lookup_waku_win_rates(master, before_date)
        out = _apply_waku_win_rate(out, waku_rates)
        if use_domain:
            rid = str(entries["race_id"].iloc[0]) if "race_id" in entries.columns else ""
            out = apply_domain_lookups(out, master, before_date, lap_pace=_race_lap_pace(rid))
    out["market_score"] = _market_score(out.get("odds", pd.Series(dtype=str)))
    return out


def enrich_entries(entries: pd.DataFrame, master: pd.DataFrame, *, use_domain: bool = True) -> pd.DataFrame:

    """出走馬に特徴量・当日斤量等を付与（スコア計算前）。"""

    if entries.empty:

        return entries



    before_date = str(entries["date"].iloc[0])

    latest = _latest_features(master, before_date)

    pair_rates = _lookup_jockey_trainer_win_rates(master, before_date)

    trainer_rates = _lookup_trainer_win_rates(master, before_date)

    waku_rates = _lookup_waku_win_rates(master, before_date)

    out = entries.merge(latest, on="horse_id", how="left", suffixes=("", "_hist"))

    out["_pair"] = jockey_trainer_pair_key(out["jockey"], out["trainer"])

    out["jockey_trainer_win_rate"] = out["_pair"].map(pair_rates)

    out["trainer_win_rate"] = (

        out["trainer"].fillna("").astype(str).str.strip().map(trainer_rates)

    )

    out = out.drop(columns=["_pair"])

    out = _attach_entry_physicals(out)

    out = _attach_entry_race_context(out)

    out = _apply_waku_win_rate(out, waku_rates)

    if use_domain:
        rid = str(entries["race_id"].iloc[0]) if "race_id" in entries.columns else ""
        out = apply_domain_lookups(out, master, before_date, lap_pace=_race_lap_pace(rid))

    out["market_score"] = _market_score(out.get("odds", pd.Series(dtype=str)))

    return out





def _feature_series(race_df: pd.DataFrame, feat: str) -> pd.Series:
    """レース内の特徴量列。欠損列は 0 埋め。"""
    if feat in race_df.columns:
        return pd.to_numeric(race_df[feat], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=race_df.index, dtype=float)





def compute_race_scores(

    race_df: pd.DataFrame,

    config: Optional[ScoringConfig] = None,

) -> pd.Series:

    """1レース分のスコアを返す。"""

    cfg = config or get_scoring_config()

    weights = cfg.weights_for_scoring()

    if not weights:

        return pd.Series(0.0, index=race_df.index)



    if cfg.normalize:

        feats = list(weights.keys())

        norm = normalize_race_features(race_df, feats)

        norm = normalize_race_features(norm, ["market_score"])

        score = pd.Series(0.0, index=race_df.index, dtype=float)

        for feat, w in weights.items():

            score = score + w * norm[z_column(feat)]

        score = score + cfg.market_weight * norm[z_column("market_score")]

        return score



    score = pd.Series(0.0, index=race_df.index, dtype=float)

    for feat, w in weights.items():

        score = score + w * _feature_series(race_df, feat)

    market = _feature_series(race_df, "market_score")

    score = score + cfg.market_weight * market

    return score





def compute_score_row(row: pd.Series, config: Optional[ScoringConfig] = None) -> float:

    """単行スコア（非正規化レガシー互換）。"""

    cfg = config or get_scoring_config()

    weights = cfg.weights_for_scoring()

    score = 0.0

    for feat, weight in weights.items():

        val = pd.to_numeric(row.get(feat), errors="coerce")

        if pd.notna(val):

            score += weight * float(val)

    market = pd.to_numeric(row.get("market_score"), errors="coerce")

    if pd.notna(market):

        score += cfg.market_weight * float(market)

    return score





def score_entries(

    entries: pd.DataFrame,

    master: pd.DataFrame,

    config: Optional[ScoringConfig] = None,

) -> pd.DataFrame:

    """出走馬にマスタの過去特徴量を付与してスコアリング。"""

    if entries.empty:

        return entries



    cfg = config or get_scoring_config()

    out = enrich_entries(entries, master)

    scores: List[float] = []

    for _, group in out.groupby("race_id", sort=False):

        race_scores = compute_race_scores(group, cfg)

        scores.extend(race_scores.tolist())

    out["score"] = scores



    out["win_prob"] = out.groupby("race_id")["score"].transform(

        lambda s: _softmax_series(s.astype(float))

    )

    out["rank_pred"] = out.groupby("race_id")["score"].rank(ascending=False, method="first")

    return out.sort_values(["race_no", "rank_pred"])





def predict_date(

    date_yyyymmdd: str,

    master: Optional[pd.DataFrame] = None,

    *,

    fetch_entries: bool = True,

    config: Optional[ScoringConfig] = None,

) -> pd.DataFrame:

    master = master if master is not None else load_master()



    if fetch_entries:

        race_ids = list_race_ids_for_shutuba(date_yyyymmdd)

        if not race_ids:

            return pd.DataFrame()



        entries: List[dict] = []

        for race_id in race_ids:

            html = fetch_shutuba_html(race_id)

            entries.extend(parse_shutuba(html, race_id))

        entries_df = pd.DataFrame(entries)

    else:

        entries_df = master[master["date"].astype(str) == date_yyyymmdd].copy()



    if fetch_entries:

        return score_entries(entries_df, master, config=config)

    out = enrich_master_rows(entries_df, master=master)

    cfg = config or get_scoring_config()

    scores: List[float] = []

    for _, group in out.groupby("race_id", sort=False):

        scores.extend(compute_race_scores(group, cfg).tolist())

    out["score"] = scores

    out["win_prob"] = out.groupby("race_id")["score"].transform(

        lambda s: _softmax_series(s.astype(float))

    )

    out["rank_pred"] = out.groupby("race_id")["score"].rank(ascending=False, method="first")

    return out.sort_values(["race_no", "rank_pred"])





def evaluate_master(

    master: Optional[pd.DataFrame] = None,

    *,

    min_date: str = "20240101",

    max_date: Optional[str] = None,

    config: Optional[ScoringConfig] = None,

) -> dict:

    """マスタ上の過去レースで1着的中率を簡易評価。"""

    master = master if master is not None else load_master()

    df = master[master["date"].astype(str) >= min_date].copy()

    if max_date:

        df = df[df["date"].astype(str) <= max_date]

    df["finish"] = pd.to_numeric(df["finish"], errors="coerce")



    scored_groups = []

    for _, group in df.groupby("date", sort=True):

        out = enrich_master_rows(group, master=master)

        cfg = config or get_scoring_config()

        race_scores_list: List[float] = []

        for _, race in out.groupby("race_id", sort=False):

            race_scores_list.extend(compute_race_scores(race, cfg).tolist())

        out["score"] = race_scores_list

        scored_groups.append(out)

    scored = pd.concat(scored_groups, ignore_index=True) if scored_groups else df



    hits = 0

    total = 0

    for _, group in scored.groupby("race_id"):

        valid = group.dropna(subset=["finish", "score"])

        if valid.empty:

            continue

        pred_idx = valid["score"].astype(float).idxmax()

        if valid.loc[pred_idx, "finish"] == 1:

            hits += 1

        total += 1



    top3 = 0

    for _, group in scored.groupby("race_id"):

        valid = group.dropna(subset=["finish", "score"])

        if valid.empty:

            continue

        top = valid["score"].astype(float).nlargest(3).index

        if (valid.loc[top, "finish"] == 1).any():

            top3 += 1



    return {

        "races": total,

        "win_hit_rate": hits / total if total else 0.0,

        "top3_hit_rate": top3 / total if total else 0.0,

    }


