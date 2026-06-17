normalize_track_condition <- function(x) {
  x <- stringr::str_trim(as.character(x))
  dplyr::case_when(
    x %in% c("\u826f", "\u826f\u99ac\u5834") ~ "good",
    x %in% c("\u7a0d", "\u7a0d\u91cd", "\u7a0d\u3005") ~ "yielding",
    x %in% c("\u91cd", "\u91cd\u99ac\u5834") ~ "soft",
    x %in% c("\u4e0d", "\u4e0d\u826f", "\u4e0d\u826f\u99ac\u5834") ~ "heavy",
    !is.na(x) & nzchar(x) ~ "other",
    TRUE ~ NA_character_
  )
}

prepare_jockey_track_df <- function(df) {
  cache <- load_payback_cache()
  joined <- attach_tansho_payouts(df, cache) |>
    dplyr::mutate(
      track_condition = normalize_track_condition(.data$track),
      jockey_name = stringr::str_trim(as.character(.data$jockey))
    )
  covered_race_ids <- joined |>
    dplyr::filter(!is.na(.data$tansho_yen)) |>
    dplyr::distinct(.data$race_id) |>
    dplyr::pull(.data$race_id)
  joined |>
    dplyr::filter(
      .data$race_id %in% covered_race_ids,
      !is.na(.data$track_condition),
      !is.na(.data$jockey_name),
      nzchar(.data$jockey_name)
    )
}

summarise_jockey_track_roi <- function(df, min_bets = JOCKEY_TRACK_MIN_BETS) {
  overall_roi <- sum(df$return_yen, na.rm = TRUE) /
    (nrow(df) * BET_UNIT_YEN) * 100

  tbl <- df |>
    dplyr::group_by(.data$jockey_name, .data$track_condition) |>
    dplyr::summarise(
      n_bets = dplyr::n(),
      n_races = dplyr::n_distinct(.data$race_id),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      mean_odds = mean(.data$odds_num, na.rm = TRUE),
      total_stake = .data$n_bets * BET_UNIT_YEN,
      total_return = sum(.data$return_yen, na.rm = TRUE),
      roi_pct = .data$total_return / .data$total_stake * 100,
      profit_yen = .data$total_return - .data$total_stake,
      .groups = "drop"
    ) |>
    dplyr::filter(.data$n_bets >= min_bets) |>
    dplyr::mutate(
      overall_roi_pct = overall_roi,
      roi_lift = .data$roi_pct / .data$overall_roi_pct,
      roi_lift_gt_threshold = .data$roi_lift >= JOCKEY_TRACK_ROI_LIFT_MIN
    ) |>
    dplyr::arrange(dplyr::desc(.data$roi_pct))

  tbl
}

summarise_jockey_track_wide <- function(df, min_bets = JOCKEY_TRACK_MIN_BETS) {
  df |>
    dplyr::group_by(.data$jockey_name) |>
    dplyr::group_modify(function(grp, key) {
      by_track <- grp |>
        dplyr::group_by(.data$track_condition) |>
        dplyr::summarise(
          n_bets = dplyr::n(),
          roi_pct = sum(.data$return_yen, na.rm = TRUE) /
            (.data$n_bets * BET_UNIT_YEN) * 100,
          hit_rate = mean(.data$is_win, na.rm = TRUE),
          .groups = "drop"
        ) |>
        dplyr::filter(.data$n_bets >= min_bets)

      if (nrow(by_track) < 2L) {
        return(tibble::tibble())
      }

      best <- by_track[which.max(by_track$roi_pct), , drop = FALSE]
      worst <- by_track[which.min(by_track$roi_pct), , drop = FALSE]
      tibble::tibble(
        n_bets_total = nrow(grp),
        best_track = best$track_condition[[1]],
        best_track_roi_pct = best$roi_pct[[1]],
        best_track_hit_rate = best$hit_rate[[1]],
        worst_track = worst$track_condition[[1]],
        worst_track_roi_pct = worst$roi_pct[[1]],
        roi_spread = best$roi_pct[[1]] - worst$roi_pct[[1]]
      )
    }) |>
    dplyr::ungroup() |>
    dplyr::filter(.data$n_bets_total >= min_bets * 2L) |>
    dplyr::arrange(dplyr::desc(.data$roi_spread))
}

save_jockey_track_bias_tables <- function(df) {
  if (!file.exists(PAYBACK_CACHE_JSON)) {
    stop("payback_cache.json required for jockey x track ROI")
  }
  prep <- prepare_jockey_track_df(df)
  message(
    "Jockey x track rows with payback: ",
    nrow(prep),
    " (",
    dplyr::n_distinct(prep$race_id),
    " races)"
  )

  combo <- summarise_jockey_track_roi(prep)
  save_csv_table(combo, "jockey_track_roi.csv")

  hot <- combo |>
    dplyr::filter(.data$roi_lift_gt_threshold) |>
    dplyr::arrange(dplyr::desc(.data$roi_lift))
  save_csv_table(hot, "jockey_track_hot_combos.csv")

  by_track_only <- prep |>
    dplyr::group_by(.data$track_condition) |>
    dplyr::summarise(
      n_bets = dplyr::n(),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      roi_pct = sum(.data$return_yen, na.rm = TRUE) /
        (.data$n_bets * BET_UNIT_YEN) * 100,
      .groups = "drop"
    )
  save_csv_table(by_track_only, "roi_by_track_condition.csv")

  spread <- summarise_jockey_track_wide(prep)
  save_csv_table(spread, "jockey_track_roi_spread.csv")

  if (requireNamespace("ggplot2", quietly = TRUE) && nrow(hot) > 0L) {
    top <- hot |>
      dplyr::slice_head(n = 20) |>
      dplyr::mutate(
        label = paste(.data$jockey_name, .data$track_condition, sep = " / ")
      )
    p <- ggplot2::ggplot(
      top,
      ggplot2::aes(
        x = reorder(.data$label, .data$roi_pct),
        y = .data$roi_pct,
        fill = .data$track_condition
      )
    ) +
      ggplot2::geom_col() +
      ggplot2::coord_flip() +
      ggplot2::geom_hline(
        yintercept = unique(top$overall_roi_pct)[1],
        linetype = "dashed",
        color = "gray40"
      ) +
      ggplot2::labs(
        title = "Top jockey x track combinations (flat win ROI)",
        x = NULL,
        y = "ROI %"
      ) +
      ggplot2::theme_minimal()
    ggplot2::ggsave(
      file.path(PLOTS_DIR, "jockey_track_hot_combos.png"),
      p,
      width = 9,
      height = 6,
      dpi = 150
    )
  }

  message("Hot combos (ROI lift >= ", JOCKEY_TRACK_ROI_LIFT_MIN, "): ", nrow(hot))
  invisible(list(all = combo, hot = hot))
}
