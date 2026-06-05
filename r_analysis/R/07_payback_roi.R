require_jsonlite <- function() {
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("Install jsonlite: install.packages('jsonlite')")
  }
}

load_payback_cache <- function() {
  require_jsonlite()
  if (!file.exists(PAYBACK_CACHE_JSON)) {
    stop("Missing payback cache: ", PAYBACK_CACHE_JSON)
  }
  jsonlite::fromJSON(PAYBACK_CACHE_JSON, simplifyVector = FALSE)
}

flatten_tansho_payouts <- function(cache) {
  rows <- lapply(names(cache), function(race_id) {
    entry <- cache[[race_id]]
    tansho <- entry$tansho
    if (is.null(tansho) || length(tansho) == 0L) {
      return(NULL)
    }
    tibble::tibble(
      race_id = race_id,
      umaban = names(tansho),
      tansho_yen = as.integer(unlist(tansho, use.names = FALSE))
    )
  })
  dplyr::bind_rows(rows)
}

attach_tansho_payouts <- function(df, cache) {
  payouts <- flatten_tansho_payouts(cache) |>
    dplyr::mutate(
      race_id = as.character(.data$race_id),
      umaban = as.character(.data$umaban)
    )
  df |>
    dplyr::mutate(
      race_id = as.character(.data$race_id),
      umaban = as.character(.data$umaban)
    ) |>
    dplyr::left_join(payouts, by = c("race_id", "umaban")) |>
    dplyr::mutate(
      return_yen = dplyr::if_else(.data$is_win, .data$tansho_yen, 0L)
    )
}

summarise_roi <- function(df, group_vars) {
  df |>
    dplyr::group_by(dplyr::across(dplyr::all_of(group_vars))) |>
    dplyr::summarise(
      n = dplyr::n(),
      n_races = dplyr::n_distinct(.data$race_id),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      total_stake = .data$n * BET_UNIT_YEN,
      total_return = sum(.data$return_yen, na.rm = TRUE),
      roi_pct = .data$total_return / .data$total_stake * 100,
      profit_yen = .data$total_return - .data$total_stake,
      .groups = "drop"
    )
}

save_roi_tables <- function(df) {
  cache <- load_payback_cache()
  joined <- attach_tansho_payouts(df, cache)
  covered_races <- length(unique(joined$race_id[!is.na(joined$tansho_yen)]))
  total_races <- dplyr::n_distinct(joined$race_id)
  message(
    "Payback join: ", covered_races, " / ", total_races,
    " races (", round(100 * covered_races / total_races, 1), "%)"
  )

  overall <- joined |>
    dplyr::summarise(
      n_rows = dplyr::n(),
      n_races = dplyr::n_distinct(.data$race_id),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      total_stake = dplyr::n() * BET_UNIT_YEN,
      total_return = sum(.data$return_yen, na.rm = TRUE),
      roi_pct = .data$total_return / .data$total_stake * 100,
      profit_yen = .data$total_return - .data$total_stake,
      .groups = "drop"
    )
  save_csv_table(overall, "roi_overall_tansho_flat.csv")

  odds_tbl <- joined |>
    dplyr::filter(!is.na(.data$odds_num), .data$odds_num > 0) |>
    dplyr::mutate(
      odds_bin = cut(
        .data$odds_num,
        breaks = ODDS_BREAKS,
        include.lowest = TRUE,
        right = FALSE
      )
    )
  save_csv_table(summarise_roi(odds_tbl, "odds_bin"), "roi_by_odds_bin.csv")

  pop_tbl <- joined |>
    dplyr::filter(!is.na(.data$popularity_num)) |>
    dplyr::mutate(
      pop_bin = cut(
        .data$popularity_num,
        breaks = POPULARITY_BINS,
        include.lowest = TRUE,
        right = TRUE
      )
    )
  save_csv_table(summarise_roi(pop_tbl, "pop_bin"), "roi_by_popularity_bin.csv")

  class_tbl <- joined |>
    dplyr::filter(!is.na(.data$race_class), nzchar(.data$race_class))
  save_csv_table(summarise_roi(class_tbl, "race_class"), "roi_by_race_class.csv")

  fav <- joined |>
    dplyr::filter(.data$popularity_num == 1) |>
    dplyr::summarise(
      n = dplyr::n(),
      n_races = dplyr::n_distinct(.data$race_id),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      total_stake = dplyr::n() * BET_UNIT_YEN,
      total_return = sum(.data$return_yen, na.rm = TRUE),
      roi_pct = .data$total_return / .data$total_stake * 100,
      profit_yen = .data$total_return - .data$total_stake,
      .groups = "drop"
    )
  save_csv_table(fav, "roi_favorite_tansho.csv")

  invisible(joined)
}
