
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
