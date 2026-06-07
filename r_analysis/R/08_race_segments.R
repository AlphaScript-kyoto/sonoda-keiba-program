
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
  if (isTRUE(signals$class_upset)) return(STRATEGY_UPSET_LABEL)
  if (isTRUE(signals$dist_upset)) return(STRATEGY_UPSET_LABEL)
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
  if (isTRUE(signals$class_upset)) return(STRATEGY_UPSET_LABEL)
  if (isTRUE(signals$dist_upset)) return(STRATEGY_UPSET_LABEL)
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
