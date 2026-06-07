"""One-shot generator for R analysis phase 2 files. Run: python tools/_gen_phase2.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPORT_PY = r'''"""Export backtest rows for R segment analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY, should_skip_win_bet
from src.predictor.score import load_master
from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs

DEFAULT_OUT = ROOT / "r_analysis" / "input" / "backtest_rows.csv"
FIRM = "\u5805"
UPSET = "\u8352"


def records_to_export_df(records, *, strategy=DEFAULT_STRATEGY) -> pd.DataFrame:
    rows = []
    for rec in records:
        exotic_high = _exotic_high_for_record(rec, strategy)
        skip_win = should_skip_win_bet(rec.win_profile, rec.pred_odds, strategy)
        skip_place = rec.win_profile == UPSET and strategy.skip_place_on_upset

        win_invest = 0 if skip_win else BET_UNIT
        win_return = rec.win_payout if (not skip_win and rec.win_hit) else 0
        place_invest = 0 if skip_place else BET_UNIT
        place_return = rec.place_payout if (not skip_place and rec.place_hit) else 0

        if exotic_high and rec.exotic_profile == FIRM:
            sp_pts = rec.sanrenpuku_points
            sp_hit = rec.sanrenpuku_hit
            st_pts = rec.sanrentan_points
            st_hit = rec.sanrentan_hit
            if rec.is_volatile:
                wd_pts = rec.wide_upset_points
                wd_hit = rec.wide_upset_hit
                wd_return = rec.wide_upset_return_yen
            else:
                wd_pts = rec.wide_firm_points
                wd_hit = rec.wide_firm_hit
                wd_return = rec.wide_firm_return_yen
        elif exotic_high and rec.exotic_profile == UPSET:
            sp_pts = rec.sanrenpuku_box_points
            sp_hit = rec.sanrenpuku_box_hit
            st_pts = 0
            st_hit = False
            wd_pts = rec.wide_upset_points
            wd_hit = rec.wide_upset_hit
            wd_return = rec.wide_upset_return_yen
        else:
            sp_pts = st_pts = wd_pts = 0
            sp_hit = st_hit = wd_hit = False
            wd_return = 0

        sp_invest = sp_pts * BET_UNIT if sp_pts else 0
        sp_return = rec.fuku3_yen if (sp_pts and sp_hit) else 0
        st_invest = st_pts * BET_UNIT if st_pts else 0
        st_return = rec.tan3_yen if (st_pts and st_hit) else 0
        wd_invest = wd_pts * BET_UNIT if wd_pts else 0

        rows.append(
            {
                "date": rec.date,
                "race_no": rec.race_no,
                "race_name": rec.race_name,
                "pred_umaban": rec.pred_umaban,
                "pred_horse": rec.pred_horse,
                "pred_odds": rec.pred_odds,
                "actual_1st": rec.actual_1st,
                "win_prob_top": rec.win_prob_top,
                "prob_gap": rec.prob_gap,
                "exotic_prob_top": rec.exotic_prob_top,
                "exotic_prob_gap": rec.exotic_prob_gap,
                "win_profile": rec.win_profile,
                "exotic_profile": rec.exotic_profile,
                "is_volatile": rec.is_volatile,
                "win_high": rec.win_high,
                "exotic_high": exotic_high,
                "win_hit": rec.win_hit,
                "place_hit": rec.place_hit,
                "skip_win": skip_win,
                "skip_place": skip_place,
                "win_invest_yen": win_invest,
                "win_return_yen": win_return,
                "place_invest_yen": place_invest,
                "place_return_yen": place_return,
                "sanrenpuku_points": sp_pts,
                "sanrenpuku_hit": sp_hit,
                "sanrenpuku_invest_yen": sp_invest,
                "sanrenpuku_return_yen": sp_return,
                "sanrentan_points": st_pts,
                "sanrentan_hit": st_hit,
                "sanrentan_invest_yen": st_invest,
                "sanrentan_return_yen": st_return,
                "wide_points": wd_pts,
                "wide_hit": wd_hit,
                "wide_invest_yen": wd_invest,
                "wide_return_yen": wd_return,
            }
        )
    return pd.DataFrame(rows)


def export_backtest_rows(
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    out_path: Path = DEFAULT_OUT,
    *,
    fetch_payback: bool = False,
) -> Path:
    master = load_master()
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ]
    if hist.empty:
        raise SystemExit(f"No master rows for {from_yyyymmdd}..{to_yyyymmdd}")

    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)
    win_cfg = ScoringConfig.load_tuned()
    _, ex_cfg = load_split_scoring_configs()
    records = _collect_race_records(
        from_yyyymmdd,
        to_yyyymmdd,
        master,
        paybacks,
        win_cfg,
        ex_cfg,
        DEFAULT_STRATEGY,
    )
    df = records_to_export_df(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export backtest rows for R analysis")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output CSV path")
    parser.add_argument("--fetch-payback", action="store_true")
    args = parser.parse_args()
    out = export_backtest_rows(
        args.from_date,
        args.to_date,
        Path(args.out),
        fetch_payback=args.fetch_payback,
    )
    n = len(pd.read_csv(out))
    print(f"Exported {out} ({n} rows)")


if __name__ == "__main__":
    main()
'''

R_FILES: dict[str, str] = {
"r_analysis/config/strategy_constants.R": r"""
# Mirrors src/predictor/bets.py BetStrategyConfig defaults (ASCII labels: firm/upset)
STRATEGY_FIRM_LABEL <- "\u5805"
STRATEGY_UPSET_LABEL <- "\u8352"

STRATEGY_WIN_FAV_ODDS_SKIP <- 3.0
STRATEGY_WIN_UPSET_SCORE_MIN <- 4L
STRATEGY_WIN_PROB_GAP_MAX <- 0.65
STRATEGY_WIN_FAV_SOFT <- 2.5
STRATEGY_FAV_ODDS_UPSET <- 3.0
STRATEGY_UPSET_SCORE_MIN <- 3L
STRATEGY_EXOTIC_HEAD_MIN <- 12L
STRATEGY_EXOTIC_ODDS_STD_MIN <- 88.0
STRATEGY_EXOTIC_CLASS_SCORE_MIN <- 2L
STRATEGY_EXOTIC_DIST_MIN_M <- 1700.0
STRATEGY_EXOTIC_DIST_SCORE_MIN <- 2L
STRATEGY_EXOTIC_UPSET_CLASSES <- c("C1", "C2", "C3", "B2")
STRATEGY_WIN_MAX_PRED_ODDS <- 25.0
STRATEGY_LONGSHOT_MAX_ODDS <- 50.0
""",
"r_analysis/R/08_race_segments.R": r"""
source(file.path(PROJECT_ROOT, "r_analysis", "config", "strategy_constants.R"), encoding = "UTF-8")

parse_distance_m <- function(x) {
  x <- as.character(x)
  x <- gsub("m$", "", x)
  suppressWarnings(as.numeric(x))
}

is_lower_class <- function(race_class, classes = STRATEGY_EXOTIC_UPSET_CLASSES) {
  cls <- toupper(trimws(as.character(race_class)))
  if (!nzchar(cls)) return(FALSE)
  any(startsWith(cls, classes))
}

compute_upset_score <- function(
    fav_odds,
    prob_gap,
    head_count,
    win_prob_top,
    odds_std = 0
) {
  score <- 0L
  if (!is.na(fav_odds) && fav_odds >= 3.0) score <- score + 2L
  if (!is.na(prob_gap) && prob_gap <= 0.65) score <- score + 1L
  if (!is.na(head_count) && head_count >= 12L) score <- score + 1L
  if (!is.na(win_prob_top) && win_prob_top < 0.88) score <- score + 1L
  if (!is.na(odds_std) && odds_std >= STRATEGY_EXOTIC_ODDS_STD_MIN) score <- score + 1L
  score
}

detect_win_profile_r <- function(signals) {
  if (signals$fav_odds >= STRATEGY_WIN_FAV_ODDS_SKIP) return(STRATEGY_UPSET_LABEL)
  if (
    signals$upset_score >= STRATEGY_WIN_UPSET_SCORE_MIN &&
      signals$fav_odds >= STRATEGY_WIN_FAV_SOFT &&
      signals$prob_gap <= STRATEGY_WIN_PROB_GAP_MAX
  ) return(STRATEGY_UPSET_LABEL)
  if (signals$class_upset) return(STRATEGY_UPSET_LABEL)
  if (signals$dist_upset) return(STRATEGY_UPSET_LABEL)
  STRATEGY_FIRM_LABEL
}

detect_exotic_profile_r <- function(signals) {
  if (signals$fav_odds >= STRATEGY_FAV_ODDS_UPSET) return(STRATEGY_UPSET_LABEL)
  if (signals$upset_score >= 4L) return(STRATEGY_UPSET_LABEL)
  if (
    signals$upset_score >= STRATEGY_UPSET_SCORE_MIN &&
      signals$fav_odds >= STRATEGY_WIN_FAV_SOFT &&
      signals$prob_gap <= 0.70
  ) return(STRATEGY_UPSET_LABEL)
  if (signals$class_upset) return(STRATEGY_UPSET_LABEL)
  if (signals$dist_upset) return(STRATEGY_UPSET_LABEL)
  STRATEGY_FIRM_LABEL
}

build_race_signals_master <- function(race_df) {
  odds <- suppressWarnings(as.numeric(race_df$odds_num))
  odds <- odds[!is.na(odds) & odds > 0]
  fav_odds <- if (length(odds)) min(odds) else 99.0
  head_count <- {
    hc <- suppressWarnings(as.integer(race_df$head_count[1]))
    if (!is.na(hc) && hc > 0L) hc else nrow(race_df)
  }
  odds_std <- if (length(odds) >= 2L) stats::sd(odds) else 0.0
  ord <- order(odds)
  implied <- 1 / odds[ord]
  implied <- implied / sum(implied)
  win_prob_top <- if (length(implied)) implied[1] else 0.0
  prob_gap <- if (length(implied) >= 2L) implied[1] - implied[2] else 0.0
  race_class <- as.character(race_df$race_class[1])
  distance_m <- parse_distance_m(race_df$distance[1])
  upset_score <- compute_upset_score(
    fav_odds, prob_gap, head_count, win_prob_top, odds_std
  )
  class_upset <- is_lower_class(race_class) &&
    upset_score >= STRATEGY_EXOTIC_CLASS_SCORE_MIN
  dist_upset <- !is.na(distance_m) &&
    distance_m >= STRATEGY_EXOTIC_DIST_MIN_M &&
    upset_score >= STRATEGY_EXOTIC_DIST_SCORE_MIN
  tibble::tibble(
    fav_odds = fav_odds,
    head_count = head_count,
    odds_std = odds_std,
    win_prob_top = win_prob_top,
    prob_gap = prob_gap,
    upset_score = upset_score,
    race_class = race_class,
    distance_m = distance_m,
    class_upset = class_upset,
    dist_upset = dist_upset
  )
}

build_race_level_master <- function(df) {
  df |>
    dplyr::group_by(.data$race_id, .data$date, .data$race_no) |>
    dplyr::group_modify(function(grp, ...) {
      sig <- build_race_signals_master(grp)
      dplyr::mutate(
        sig,
        win_profile_master = detect_win_profile_r(sig),
        exotic_profile_master = detect_exotic_profile_r(sig),
        is_volatile_master = sig$head_count >= STRATEGY_EXOTIC_HEAD_MIN ||
          sig$odds_std >= STRATEGY_EXOTIC_ODDS_STD_MIN ||
          sig$class_upset
      )
    }) |>
    dplyr::ungroup()
}

load_backtest_rows <- function() {
  if (!file.exists(BACKTEST_ROWS_CSV)) {
    return(NULL)
  }
  readr::read_csv(BACKTEST_ROWS_CSV, show_col_types = FALSE, progress = FALSE)
}

summarise_bet_roi <- function(df, group_vars = character()) {
  if (nrow(df) == 0L) return(tibble::tibble())
  if (length(group_vars) == 0L) {
    return(tibble::tibble(
      n_races = dplyr::n(),
      win_roi_pct = sum(.data$win_return_yen) / sum(.data$win_invest_yen) * 100,
      place_roi_pct = sum(.data$place_return_yen) / sum(.data$place_invest_yen) * 100,
      sanren_roi_pct = sum(.data$sanrenpuku_return_yen) / sum(.data$sanrenpuku_invest_yen) * 100,
      sanrentan_roi_pct = sum(.data$sanrentan_return_yen) / sum(.data$sanrentan_invest_yen) * 100,
      wide_roi_pct = sum(.data$wide_return_yen) / sum(.data$wide_invest_yen) * 100
    ))
  }
  df |>
    dplyr::group_by(dplyr::across(dplyr::all_of(group_vars))) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      win_hit_rate = mean(.data$win_hit, na.rm = TRUE),
      win_roi_pct = sum(.data$win_return_yen) / sum(.data$win_invest_yen) * 100,
      sanren_hit_rate = mean(.data$sanrenpuku_hit, na.rm = TRUE),
      sanren_roi_pct = sum(.data$sanrenpuku_return_yen) / sum(.data$sanrenpuku_invest_yen) * 100,
      wide_roi_pct = sum(.data$wide_return_yen) / sum(.data$wide_invest_yen) * 100,
      .groups = "drop"
    )
}

save_segment_tables <- function() {
  bt <- load_backtest_rows()
  if (is.null(bt)) {
    message("No backtest_rows.csv - run export_backtest_for_r.py first")
    message("Writing master-only segment tables (market proxy profiles)")
    df <- load_master_filtered()
    races <- build_race_level_master(df)
    seg <- races |>
      dplyr::summarise(
        n_races = dplyr::n(),
        mean_fav_odds = mean(.data$fav_odds, na.rm = TRUE),
        .by = c("win_profile_master", "exotic_profile_master")
      )
    save_csv_table(seg, "segment_master_profiles.csv")
    return(invisible(races))
  }

  bt <- bt |>
    dplyr::mutate(
      win_high_lab = dplyr::if_else(.data$win_high, "high", "normal"),
      exotic_high_lab = dplyr::if_else(.data$exotic_high, "high", "normal")
    )

  save_csv_table(summarise_bet_roi(bt, "win_profile"), "segment_by_win_profile.csv")
  save_csv_table(summarise_bet_roi(bt, "exotic_profile"), "segment_by_exotic_profile.csv")
  save_csv_table(summarise_bet_roi(bt, "win_high_lab"), "segment_by_confidence.csv")
  save_csv_table(
    summarise_bet_roi(bt, c("win_profile", "win_high_lab")),
    "segment_by_profile_confidence.csv"
  )
  save_csv_table(
    summarise_bet_roi(bt, c("exotic_profile", "exotic_high_lab")),
    "segment_by_exotic_confidence.csv"
  )

  sp <- bt |>
    dplyr::filter(.data$exotic_high, .data$sanrenpuku_invest_yen > 0L)
  save_csv_table(summarise_bet_roi(sp, "exotic_profile"), "segment_sanrenpuku_by_profile.csv")

  invisible(bt)
}
""",
"r_analysis/R/09_decile_extended.R": r"""
save_extended_decile_tables <- function(df) {
  gaps <- list()
  for (feat in DECILE_EXTENDED_FEATURES) {
    if (!feat %in% names(df)) next
    sub <- df |>
      dplyr::filter(!is.na(.data[[feat]])) |>
      dplyr::mutate(decile = dplyr::ntile(.data[[feat]], 10L))
    if (nrow(sub) < 100L) next
    rate <- mean(!is.na(sub[[feat]]))
    if (rate < MIN_FEATURE_NONNA_RATE) next
    tbl <- sub |>
      dplyr::group_by(.data$decile) |>
      dplyr::summarise(
        feature = feat,
        n = dplyr::n(),
        feat_min = min(.data[[feat]], na.rm = TRUE),
        feat_max = max(.data[[feat]], na.rm = TRUE),
        feat_mean = mean(.data[[feat]], na.rm = TRUE),
        win_rate = mean(.data$is_win, na.rm = TRUE),
        top3_rate = mean(.data$is_top3, na.rm = TRUE),
        .groups = "drop"
      )
    save_csv_table(tbl, paste0("decile_winrate_", feat, ".csv"))
    if (nrow(tbl) >= 2L) {
      gaps[[feat]] <- tibble::tibble(
        feature = feat,
        win_rate_d1 = tbl$win_rate[1],
        win_rate_d10 = tbl$win_rate[nrow(tbl)],
        win_rate_gap = tbl$win_rate[nrow(tbl)] - tbl$win_rate[1],
        top3_rate_gap = tbl$top3_rate[nrow(tbl)] - tbl$top3_rate[1],
        n_rows = sum(tbl$n)
      )
    }
  }
  if (length(gaps)) {
    save_csv_table(dplyr::bind_rows(gaps), "decile_gap_summary.csv")
  }
  invisible(gaps)
}
""",
"r_analysis/R/10_bet_like_roi.R": r"""
flatten_fuku3_payouts <- function(cache) {
  rows <- lapply(names(cache), function(race_id) {
    entry <- cache[[race_id]]
    ums <- entry$fuku3_umaban
    if (is.null(ums) || length(ums) == 0L) return(NULL)
    tibble::tibble(
      race_id = race_id,
      fuku3_u1 = as.character(ums[[1]]),
      fuku3_u2 = as.character(ums[[2]]),
      fuku3_u3 = as.character(ums[[3]]),
      fuku3_yen = as.integer(entry$fuku3_yen %||% 0L)
    )
  })
  dplyr::bind_rows(rows)
}

`%||%` <- function(x, y) if (is.null(x)) y else x

pick_pop_top_n <- function(race_df, n) {
  race_df |>
    dplyr::filter(!is.na(.data$popularity_num)) |>
    dplyr::arrange(.data$popularity_num) |>
    dplyr::slice_head(n = n) |>
    dplyr::pull(.data$umaban) |>
    as.character()
}

check_fuku3_combo <- function(selected, u1, u2, u3) {
  sort(selected) == sort(c(u1, u2, u3))
}

summarise_scenario_roi <- function(df, scenario) {
  df |>
    dplyr::summarise(
      scenario = scenario,
      n_bets = dplyr::n(),
      n_races = dplyr::n_distinct(.data$race_id),
      hit_rate = mean(.data$hit, na.rm = TRUE),
      total_stake = sum(.data$stake, na.rm = TRUE),
      total_return = sum(.data$return_yen, na.rm = TRUE),
      roi_pct = .data$total_return / .data$total_stake * 100,
      profit_yen = .data$total_return - .data$total_stake,
      .groups = "drop"
    )
}

build_bet_like_scenarios <- function(joined, cache) {
  fuku3 <- flatten_fuku3_payouts(cache)
  races <- joined |>
    dplyr::group_by(.data$race_id, .data$date) |>
    dplyr::group_modify(function(grp, key) {
      sig <- build_race_signals_master(grp)
      win_prof <- detect_win_profile_r(sig)
      pop1 <- grp |> dplyr::filter(.data$popularity_num == 1)
      top_win <- if (nrow(pop1) > 0L) pop1 else {
        grp |> dplyr::slice_min(.data$odds_num, n = 1, with_ties = FALSE)
      }
      feat_top <- grp |> dplyr::slice_max(.data$horse_win_rate, n = 1, with_ties = FALSE)
      pop123 <- pick_pop_top_n(grp, 3)
      pop14 <- pick_pop_top_n(grp, 4)
      rid <- as.character(key$race_id[1])
      frow <- fuku3 |> dplyr::filter(.data$race_id == rid)
      fuku_yen <- if (nrow(frow)) frow$fuku3_yen[1] else 0L
      fuku_hit_123 <- nrow(frow) > 0L && length(pop123) >= 3L && check_fuku3_combo(
        pop123, frow$fuku3_u1[1], frow$fuku3_u2[1], frow$fuku3_u3[1]
      )
      fuku_hit_14 <- nrow(frow) > 0L && length(pop14) >= 3L &&
        any(vapply(
          utils::combn(pop14, 3, simplify = FALSE),
          function(cmb) check_fuku3_combo(cmb, frow$fuku3_u1[1], frow$fuku3_u2[1], frow$fuku3_u3[1]),
          logical(1)
        ))
      pop1_hit <- nrow(pop1) > 0L && isTRUE(pop1$is_win[1])
      top_hit <- nrow(top_win) > 0L && isTRUE(top_win$is_win[1])
      top_odds <- if (nrow(top_win) > 0L) top_win$odds_num[1] else NA_real_
      tibble::tibble(
        win_profile = win_prof,
        fav_win_hit = pop1_hit,
        fav_tansho_return = if (pop1_hit) pop1$return_yen[1] else 0L,
        firm_skip = win_prof == STRATEGY_UPSET_LABEL,
        pred_high_odds_skip = !is.na(top_odds) && top_odds > STRATEGY_WIN_MAX_PRED_ODDS,
        pred_tansho_hit = top_hit,
        pred_tansho_return = if (top_hit) top_win$return_yen[1] else 0L,
        fuku_hit_123 = fuku_hit_123,
        fuku_hit_14 = fuku_hit_14,
        fuku3_yen = fuku_yen
      )
    }) |>
    dplyr::ungroup()

  pop1_rows <- joined |> dplyr::filter(.data$popularity_num == 1)
  pred_rows <- races |>
    dplyr::filter(!.data$firm_skip, !.data$pred_high_odds_skip)

  scenarios <- list(
    summarise_scenario_roi(
      tibble::tibble(
        race_id = pop1_rows$race_id,
        hit = pop1_rows$is_win,
        stake = BET_UNIT_YEN,
        return_yen = pop1_rows$return_yen
      ),
      "fav_tansho_100"
    ),
    summarise_scenario_roi(
      tibble::tibble(
        race_id = pred_rows$race_id,
        hit = pred_rows$pred_tansho_hit,
        stake = BET_UNIT_YEN,
        return_yen = dplyr::if_else(
          pred_rows$pred_tansho_hit,
          pred_rows$pred_tansho_return,
          0L
        )
      ),
      "pred_tansho_firm_no_high_odds"
    ),
    summarise_scenario_roi(
      tibble::tibble(
        race_id = races$race_id,
        hit = races$fuku_hit_123,
        stake = BET_UNIT_YEN,
        return_yen = dplyr::if_else(races$fuku_hit_123, races$fuku3_yen, 0L)
      ),
      "sanren_pop123_box_100"
    ),
    summarise_scenario_roi(
      tibble::tibble(
        race_id = races$race_id,
        hit = races$fuku_hit_14,
        stake = 4L * BET_UNIT_YEN,
        return_yen = dplyr::if_else(races$fuku_hit_14, races$fuku3_yen, 0L)
      ),
      "sanren_pop14_box_400"
    )
  )

  overall <- dplyr::bind_rows(scenarios)
  save_csv_table(overall, "roi_bet_like_overall.csv")

  by_prof <- races |>
    dplyr::mutate(
      stake = BET_UNIT_YEN,
      return_yen = dplyr::if_else(
        .data$pred_tansho_hit & .data$win_profile == STRATEGY_FIRM_LABEL & !.data$pred_high_odds_skip,
        .data$pred_tansho_return,
        0L
      ),
      hit = .data$pred_tansho_hit & .data$win_profile == STRATEGY_FIRM_LABEL & !.data$pred_high_odds_skip,
      bet = .data$win_profile == STRATEGY_FIRM_LABEL & !.data$pred_high_odds_skip
    ) |>
    dplyr::filter(.data$bet) |>
    dplyr::group_by(.data$win_profile) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      hit_rate = mean(.data$hit, na.rm = TRUE),
      roi_pct = sum(.data$return_yen) / sum(.data$stake) * 100,
      .groups = "drop"
    )
  save_csv_table(by_prof, "roi_bet_like_by_win_profile.csv")

  bt <- load_backtest_rows()
  if (!is.null(bt)) {
    bt_roi <- tibble::tibble(
      scenario = c("bt_win", "bt_sanren", "bt_wide"),
      n_bets = c(
        sum(bt$win_invest_yen > 0L),
        sum(bt$sanrenpuku_invest_yen > 0L),
        sum(bt$wide_invest_yen > 0L)
      ),
      total_stake = c(
        sum(bt$win_invest_yen),
        sum(bt$sanrenpuku_invest_yen),
        sum(bt$wide_invest_yen)
      ),
      total_return = c(
        sum(bt$win_return_yen),
        sum(bt$sanrenpuku_return_yen),
        sum(bt$wide_return_yen)
      )
    ) |>
      dplyr::mutate(roi_pct = .data$total_return / .data$total_stake * 100)
    save_csv_table(bt_roi, "roi_backtest_export_summary.csv")
  }

  invisible(overall)
}

save_bet_like_roi_tables <- function(df) {
  cache <- load_payback_cache()
  joined <- attach_tansho_payouts(df, cache)
  build_bet_like_scenarios(joined, cache)
}
""",
"r_analysis/scripts/04_segment_analysis.R": r"""source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()

ensure_output_dirs()
message("Segment analysis (profiles / confidence)...")
save_segment_tables()
message("Done. See r_analysis/output/tables/segment_*.csv")
""",
"r_analysis/scripts/05_decile_extended.R": r"""source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()

ensure_output_dirs()
message("Loading master for extended deciles...")
df <- load_master_filtered()
message("Rows: ", nrow(df))
save_extended_decile_tables(df)
message("Done. See decile_winrate_*.csv and decile_gap_summary.csv")
""",
"r_analysis/scripts/06_bet_like_roi.R": r"""source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()

ensure_output_dirs()
message("Loading master for bet-like ROI...")
df <- load_master_filtered()
message("Rows: ", nrow(df))
save_bet_like_roi_tables(df)
message("Done. See r_analysis/output/tables/roi_bet_like_*.csv")
""",
}


def write_utf8(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    print("wrote", rel)


SETTINGS_APPEND = r"""
BACKTEST_ROWS_CSV <- file.path(PROJECT_ROOT, "r_analysis", "input", "backtest_rows.csv")
DECILE_EXTENDED_FEATURES <- c(
  "horse_win_rate_track",
  "trainer_win_rate",
  "last5_avg_finish",
  "style_track_win_rate",
  "waku_distance_win_rate",
  "last3_avg_style_score",
  "jockey_trainer_roi",
  "pace_style_fit",
  "sonoda_waku_style_fit",
  "sonoda_front_bonus",
  "dam_sire_win_rate",
  "entry_head_count",
  "last_body_weight_delta",
  "last3_avg_time_index",
  "horse_best_time_index",
  "body_weight_vs_avg"
)
"""

SOURCE_ALL_SNIPPET = '''  "07_payback_roi.R",
  "08_race_segments.R",
  "09_decile_extended.R",
  "10_bet_like_roi.R"
)'''

RUN_ALL_EXTRA = r"""
source(file.path(scripts_dir, "04_segment_analysis.R"), local = FALSE)
source(file.path(scripts_dir, "05_decile_extended.R"), local = FALSE)
if (file.exists(PAYBACK_CACHE_JSON)) {
  source(file.path(scripts_dir, "06_bet_like_roi.R"), local = FALSE)
} else {
  message("Skip bet-like ROI: payback_cache.json not found")
}
"""


def patch_settings() -> None:
    path = ROOT / "r_analysis/config/settings.R"
    text = path.read_text(encoding="utf-8")
    if "BACKTEST_ROWS_CSV" not in text:
        path.write_text(text.rstrip() + "\n" + SETTINGS_APPEND.strip() + "\n", encoding="utf-8")
        print("patched settings.R")


def patch_source_all() -> None:
    path = ROOT / "r_analysis/R/00_source_all.R"
    text = path.read_text(encoding="utf-8")
    if "08_race_segments" not in text:
        text = text.replace(
            '  "07_payback_roi.R"\n)',
            SOURCE_ALL_SNIPPET,
        )
        path.write_text(text, encoding="utf-8")
        print("patched 00_source_all.R")


def patch_run_all() -> None:
    path = ROOT / "r_analysis/scripts/run_all.R"
    text = path.read_text(encoding="utf-8")
    if "04_segment_analysis" not in text:
        marker = '} else {\n  message("Skip ROI: payback_cache.json not found")\n}'
        if marker in text:
            text = text.replace(
                marker,
                marker + "\n" + RUN_ALL_EXTRA.strip(),
            )
        path.write_text(text, encoding="utf-8")
        print("patched run_all.R")


def patch_gitignore() -> None:
    path = ROOT / "r_analysis/.gitignore"
    text = path.read_text(encoding="utf-8")
    if "input/" not in text:
        path.write_text(text.rstrip() + "\ninput/\n", encoding="utf-8")
        print("patched r_analysis/.gitignore")


def main() -> None:
    write_utf8("scripts/export_backtest_for_r.py", EXPORT_PY)
    for rel, content in R_FILES.items():
        write_utf8(rel, content)
    patch_settings()
    patch_source_all()
    patch_run_all()
    patch_gitignore()


if __name__ == "__main__":
    main()
