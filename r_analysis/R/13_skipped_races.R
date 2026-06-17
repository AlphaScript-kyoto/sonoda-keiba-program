prepare_backtest_skip_df <- function(bt) {
  if (!exists("STRATEGY_UPSET_LABEL", inherits = TRUE)) {
    source(
      file.path(PROJECT_ROOT, "r_analysis", "config", "strategy_constants.R"),
      encoding = "UTF-8"
    )
  }
  bt |>
    attach_hypothetical_place_return() |>
    dplyr::mutate(
      pred_odds_num = suppressWarnings(as.numeric(.data$pred_odds)),
      model_ev = .data$win_prob_top * .data$pred_odds_num,
      place_empirical_ev = dplyr::if_else(
        .data$place_hit,
        .data$hypothetical_place_return_yen / BET_UNIT_YEN,
        0
      ),
      hypothetical_win_return = dplyr::if_else(
        .data$win_hit,
        .data$pred_odds_num * BET_UNIT_YEN,
        0
      ),
      skip_reason = dplyr::case_when(
        .data$skip_win & .data$win_profile == STRATEGY_UPSET_LABEL ~ "upset_profile",
        .data$skip_win & .data$pred_odds_num > STRATEGY_WIN_MAX_PRED_ODDS ~ "high_odds_cap",
        .data$skip_win ~ "other_skip",
        TRUE ~ "played"
      )
    ) |>
    dplyr::filter(
      !is.na(.data$pred_odds_num),
      .data$pred_odds_num > 0,
      .data$win_high
    )
}

summarise_skip_vs_played <- function(bt) {
  bt |>
    dplyr::mutate(
      bet_group = dplyr::if_else(.data$skip_win, "skipped", "played")
    ) |>
    dplyr::group_by(.data$bet_group) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      mean_model_ev = mean(.data$model_ev, na.rm = TRUE),
      median_model_ev = stats::median(.data$model_ev, na.rm = TRUE),
      share_ev_ge_1 = mean(.data$model_ev >= SKIPPED_EV_THRESHOLD, na.rm = TRUE),
      win_hit_rate = mean(.data$win_hit, na.rm = TRUE),
      place_hit_rate = mean(.data$place_hit, na.rm = TRUE),
      hypothetical_win_roi_pct = sum(.data$hypothetical_win_return) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      hypothetical_place_roi_pct = sum(.data$hypothetical_place_return_yen) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      actual_win_roi_pct = sum(.data$win_return_yen) /
        sum(.data$win_invest_yen) * 100,
      actual_place_roi_pct = sum(.data$place_return_yen) /
        sum(.data$place_invest_yen) * 100,
      .groups = "drop"
    )
}

summarise_skipped_by_reason <- function(bt) {
  bt |>
    dplyr::filter(.data$skip_win) |>
    dplyr::group_by(.data$skip_reason, .data$win_profile) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      mean_model_ev = mean(.data$model_ev, na.rm = TRUE),
      share_ev_ge_1 = mean(.data$model_ev >= SKIPPED_EV_THRESHOLD, na.rm = TRUE),
      win_hit_rate = mean(.data$win_hit, na.rm = TRUE),
      place_hit_rate = mean(.data$place_hit, na.rm = TRUE),
      hypothetical_win_roi_pct = sum(.data$hypothetical_win_return) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      hypothetical_place_roi_pct = sum(.data$hypothetical_place_return_yen) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      missed_wins = sum(.data$win_hit, na.rm = TRUE),
      missed_places = sum(.data$place_hit, na.rm = TRUE),
      .groups = "drop"
    ) |>
    dplyr::arrange(dplyr::desc(.data$hypothetical_place_roi_pct))
}

identify_high_ev_skipped <- function(bt) {
  bt |>
    dplyr::filter(
      .data$skip_win,
      .data$model_ev >= SKIPPED_EV_THRESHOLD
    ) |>
    dplyr::arrange(dplyr::desc(.data$model_ev)) |>
    dplyr::select(
      dplyr::any_of(c(
        "date", "race_no", "race_name", "pred_umaban", "pred_horse",
        "pred_odds", "win_prob_top", "prob_gap", "win_profile",
        "exotic_profile", "skip_reason", "model_ev", "win_hit", "place_hit",
        "hypothetical_place_return_yen"
      ))
    )
}

summarise_skipped_ev_bins <- function(bt) {
  bt |>
    dplyr::filter(.data$skip_win) |>
    dplyr::mutate(ev_bin = cut(
      .data$model_ev,
      breaks = c(0, 0.5, 0.8, 1.0, 1.2, 1.5, 2, Inf),
      include.lowest = TRUE,
      right = FALSE
    )) |>
    dplyr::group_by(.data$ev_bin) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      win_hit_rate = mean(.data$win_hit, na.rm = TRUE),
      place_hit_rate = mean(.data$place_hit, na.rm = TRUE),
      hypothetical_win_roi_pct = sum(.data$hypothetical_win_return) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      hypothetical_place_roi_pct = sum(.data$hypothetical_place_return_yen) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      .groups = "drop"
    )
}

summarise_upset_skip_place_opportunity <- function(bt) {
  upset_skipped <- bt |>
    dplyr::filter(
      .data$skip_win,
      .data$skip_place,
      .data$skip_reason == "upset_profile"
    )
  if (nrow(upset_skipped) == 0L) {
    return(tibble::tibble())
  }
  upset_skipped |>
    dplyr::summarise(
      n_races = dplyr::n(),
      mean_model_ev = mean(.data$model_ev, na.rm = TRUE),
      win_hit_rate = mean(.data$win_hit, na.rm = TRUE),
      place_hit_rate = mean(.data$place_hit, na.rm = TRUE),
      mean_place_empirical_ev = mean(.data$place_empirical_ev, na.rm = TRUE),
      hypothetical_win_roi_pct = sum(.data$hypothetical_win_return) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      hypothetical_place_roi_pct = sum(.data$hypothetical_place_return_yen) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      place_profit_yen = sum(.data$hypothetical_place_return_yen) -
        (.data$n_races * BET_UNIT_YEN),
      place_roi_ge_100 = .data$hypothetical_place_roi_pct >= PLACE_OPPORTUNITY_MIN_ROI_PCT,
      .groups = "drop"
    )
}

summarise_upset_skip_place_by_ev_bin <- function(bt) {
  bt |>
    dplyr::filter(
      .data$skip_win,
      .data$skip_place,
      .data$skip_reason == "upset_profile"
    ) |>
    dplyr::mutate(ev_bin = cut(
      .data$model_ev,
      breaks = c(0, 0.8, 1.0, 1.2, 1.5, 2, Inf),
      include.lowest = TRUE,
      right = FALSE
    )) |>
    dplyr::group_by(.data$ev_bin) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      place_hit_rate = mean(.data$place_hit, na.rm = TRUE),
      hypothetical_place_roi_pct = sum(.data$hypothetical_place_return_yen) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      profit_yen = sum(.data$hypothetical_place_return_yen) -
        (.data$n_races * BET_UNIT_YEN),
      meets_place_criteria = .data$hypothetical_place_roi_pct >= PLACE_OPPORTUNITY_MIN_ROI_PCT &
        .data$profit_yen > 0 &
        .data$n_races >= PLACE_OPPORTUNITY_MIN_BETS,
      .groups = "drop"
    ) |>
    dplyr::arrange(dplyr::desc(.data$hypothetical_place_roi_pct))
}

identify_place_opportunity_races <- function(bt) {
  bt |>
    dplyr::filter(
      .data$skip_win,
      .data$skip_place,
      .data$skip_reason == "upset_profile"
    ) |>
    dplyr::mutate(
      place_would_profit = .data$hypothetical_place_return_yen > BET_UNIT_YEN
    ) |>
    dplyr::arrange(dplyr::desc(.data$model_ev)) |>
    dplyr::select(
      dplyr::any_of(c(
        "date", "race_no", "race_name", "pred_umaban", "pred_horse",
        "pred_odds", "win_prob_top", "prob_gap", "model_ev",
        "win_hit", "place_hit", "hypothetical_place_return_yen",
        "place_would_profit", "place_payout_yen"
      ))
    )
}

identify_place_opportunity_loss_high_ev <- function(bt) {
  identify_place_opportunity_races(bt) |>
    dplyr::filter(.data$model_ev >= SKIPPED_EV_THRESHOLD)
}

compare_upset_place_relaxation <- function(bt) {
  upset <- bt |>
    dplyr::filter(.data$skip_reason == "upset_profile")
  skipped_both <- upset |>
    dplyr::filter(.data$skip_win, .data$skip_place)
  n_high <- sum(skipped_both$model_ev >= SKIPPED_EV_THRESHOLD, na.rm = TRUE)
  high_place_return <- sum(
    skipped_both$hypothetical_place_return_yen[
      skipped_both$model_ev >= SKIPPED_EV_THRESHOLD
    ],
    na.rm = TRUE
  )
  tibble::tibble(
    scenario = c(
      "current_actual_place",
      "hypothetical_place_all_upset_skipped",
      "hypothetical_place_high_ev_skipped",
      "hypothetical_win_all_upset_skipped"
    ),
    n_races = c(
      sum(!upset$skip_place, na.rm = TRUE),
      nrow(skipped_both),
      n_high,
      nrow(skipped_both)
    ),
    roi_pct = c(
      sum(upset$place_return_yen, na.rm = TRUE) /
        sum(upset$place_invest_yen, na.rm = TRUE) * 100,
      sum(skipped_both$hypothetical_place_return_yen, na.rm = TRUE) /
        (nrow(skipped_both) * BET_UNIT_YEN) * 100,
      if (n_high > 0L) high_place_return / (n_high * BET_UNIT_YEN) * 100 else NA_real_,
      sum(skipped_both$hypothetical_win_return, na.rm = TRUE) /
        (nrow(skipped_both) * BET_UNIT_YEN) * 100
    ),
    profit_yen = c(
      sum(upset$place_return_yen, na.rm = TRUE) - sum(upset$place_invest_yen, na.rm = TRUE),
      sum(skipped_both$hypothetical_place_return_yen, na.rm = TRUE) -
        nrow(skipped_both) * BET_UNIT_YEN,
      high_place_return - n_high * BET_UNIT_YEN,
      sum(skipped_both$hypothetical_win_return, na.rm = TRUE) -
        nrow(skipped_both) * BET_UNIT_YEN
    )
  )
}

write_skipped_place_guidance <- function(
    prep,
    place_summary,
    place_ev_bins,
    relaxation_cmp
) {
  upset_n <- sum(prep$skip_win & prep$skip_place & prep$skip_reason == "upset_profile")
  lines <- c(
    "# Skipped-race place relaxation guidance",
    "",
    paste0("Generated: ", format(Sys.time(), "%Y-%m-%d %H:%M")),
    "",
    "## 1. Context",
    "",
    paste0("- win_high races analysed: ", nrow(prep)),
    paste0("- upset profile, win+place skipped: ", upset_n, " races"),
    paste0("- Current rule: skip_place_on_upset=TRUE in bets.py"),
    "",
    "## 2. Hypothetical place on upset-skipped races (all)",
    ""
  )

  if (nrow(place_summary) > 0L) {
    ps <- place_summary[1, ]
    lines <- c(
      lines,
      paste0("- Place hit rate: ", round(100 * ps$place_hit_rate, 1), "%"),
      paste0("- Win hit rate (reference): ", round(100 * ps$win_hit_rate, 1), "%"),
      paste0("- Hypothetical place ROI: ", round(ps$hypothetical_place_roi_pct, 1), "%"),
      paste0("- Hypothetical win ROI: ", round(ps$hypothetical_win_roi_pct, 1), "%"),
      paste0("- Place profit (100yen x ", ps$n_races, "R): ", round(ps$place_profit_yen), " yen"),
      paste0("- Place ROI >= 100%: ", ps$place_roi_ge_100)
    )
  } else {
    lines <- c(lines, "- No upset-skipped races in export.")
  }

  if (nrow(relaxation_cmp) > 0L) {
    lines <- c(lines, "", "## 3. Scenario comparison", "")
    for (i in seq_len(nrow(relaxation_cmp))) {
      row <- relaxation_cmp[i, ]
      lines <- c(
        lines,
        paste0(
          "- **", row$scenario, "**: n=", row$n_races,
          ", ROI=", round(row$roi_pct, 1), "%, profit=", round(row$profit_yen), " yen"
        )
      )
    }
  }

  qualifying_bins <- place_ev_bins |>
    dplyr::filter(.data$meets_place_criteria)
  lines <- c(lines, "", "## 4. EV bins with place ROI>=100% and n>=30", "")
  if (nrow(qualifying_bins) == 0L) {
    lines <- c(
      lines,
      "- **None** — no EV bin meets ROI>=100%, profit>0, n>=30 on upset-skipped races."
    )
  } else {
    for (i in seq_len(nrow(qualifying_bins))) {
      row <- qualifying_bins[i, ]
      lines <- c(
        lines,
        paste0(
          "- ", row$ev_bin, ": place ROI ", round(row$hypothetical_place_roi_pct, 1),
          "%, n=", row$n_races
        )
      )
    }
  }

  place_roi <- if (nrow(place_summary) > 0L) place_summary$hypothetical_place_roi_pct[[1]] else 0
  win_roi <- if (nrow(place_summary) > 0L) place_summary$hypothetical_win_roi_pct[[1]] else 0
  lines <- c(
    lines,
    "",
    "## 5. Recommendation (statistical)",
    ""
  )
  if (place_roi >= PLACE_OPPORTUNITY_MIN_ROI_PCT && place_roi > win_roi) {
    lines <- c(
      lines,
      paste0(
        "1. **Consider pilot**: `skip_place_on_upset=FALSE` for upset win-skipped races only.",
        " Aggregate hypothetical place ROI (", round(place_roi, 1),
        "%) exceeds win (", round(win_roi, 1), "%)."
      ),
      "2. Prefer narrow rollout: only EV bins that pass criteria in skipped_place_by_ev_bin.csv.",
      "3. Keep skip_win_on_upset=TRUE — win side remains negative EV.",
      "4. Validate with: python scripts/backtest_bets.py after code change."
    )
  } else {
    lines <- c(
      lines,
      paste0(
        "1. **Keep skip_place_on_upset=TRUE** — hypothetical place ROI (",
        round(place_roi, 1), "%) does not beat win alternative or 100% threshold."
      ),
      "2. High model EV on skipped races does not imply profitable place — check skipped_place_ev_bins.csv.",
      "3. Opportunity-loss races (skipped_place_opportunity_loss.csv) are for manual review, not auto-bet."
    )
  }

  lines <- c(
    lines,
    "",
    "## 6. Output files",
    "- skipped_place_opportunity_summary.csv",
    "- skipped_place_by_ev_bin.csv",
    "- skipped_place_opportunity_races.csv",
    "- skipped_place_opportunity_loss.csv",
    "- skipped_place_relaxation_scenarios.csv",
    ""
  )
  write_text_report("skipped_place_guidance.md", lines)
}

save_skipped_races_tables <- function() {
  bt <- load_backtest_rows()
  if (is.null(bt)) {
    stop(
      "backtest_rows.csv not found. Run:\n",
      "  python scripts/export_backtest_for_r.py --from YYYYMMDD --to YYYYMMDD"
    )
  }

  prep <- prepare_backtest_skip_df(bt)
  message(
    "Backtest rows (win_high only): ",
    nrow(prep),
    " | skipped: ",
    sum(prep$skip_win),
    " | played: ",
    sum(!prep$skip_win)
  )

  save_csv_table(summarise_skip_vs_played(prep), "skipped_vs_played_summary.csv")
  save_csv_table(summarise_skipped_by_reason(prep), "skipped_by_reason_profile.csv")
  save_csv_table(summarise_skipped_ev_bins(prep), "skipped_ev_bins.csv")

  high_ev <- identify_high_ev_skipped(prep)
  save_csv_table(high_ev, "skipped_high_ev_races.csv")

  missed <- prep |>
    dplyr::filter(.data$skip_win, .data$win_hit) |>
    dplyr::arrange(dplyr::desc(.data$model_ev))
  save_csv_table(
    dplyr::select(
      missed,
      dplyr::any_of(c(
        "date", "race_no", "race_name", "pred_umaban", "pred_odds",
        "win_profile", "skip_reason", "model_ev"
      ))
    ),
    "skipped_missed_wins.csv"
  )

  place_summary <- summarise_upset_skip_place_opportunity(prep)
  save_csv_table(place_summary, "skipped_place_opportunity_summary.csv")

  place_ev_bins <- summarise_upset_skip_place_by_ev_bin(prep)
  save_csv_table(place_ev_bins, "skipped_place_by_ev_bin.csv")

  place_races <- identify_place_opportunity_races(prep)
  save_csv_table(place_races, "skipped_place_opportunity_races.csv")

  place_loss <- identify_place_opportunity_loss_high_ev(prep)
  save_csv_table(place_loss, "skipped_place_opportunity_loss.csv")

  relaxation_cmp <- compare_upset_place_relaxation(prep)
  save_csv_table(relaxation_cmp, "skipped_place_relaxation_scenarios.csv")

  write_skipped_place_guidance(prep, place_summary, place_ev_bins, relaxation_cmp)

  if (requireNamespace("ggplot2", quietly = TRUE)) {
    p <- ggplot2::ggplot(
      prep,
      ggplot2::aes(x = .data$model_ev, fill = .data$skip_win)
    ) +
      ggplot2::geom_histogram(bins = 40, alpha = 0.6, position = "identity") +
      ggplot2::geom_vline(xintercept = SKIPPED_EV_THRESHOLD, linetype = "dashed") +
      ggplot2::labs(
        title = "Model EV distribution: played vs skipped (win_high races)",
        x = "win_prob_top x pred_odds",
        y = "Count",
        fill = "skip_win"
      ) +
      ggplot2::theme_minimal()
    ggplot2::ggsave(
      file.path(PLOTS_DIR, "skipped_ev_histogram.png"),
      p,
      width = 9,
      height = 5,
      dpi = 150
    )

    upset_skipped <- prep |>
      dplyr::filter(.data$skip_win, .data$skip_place, .data$skip_reason == "upset_profile")
    if (nrow(upset_skipped) > 0L) {
      p2 <- ggplot2::ggplot(
        upset_skipped,
        ggplot2::aes(x = .data$model_ev, y = .data$hypothetical_place_return_yen)
      ) +
        ggplot2::geom_point(alpha = 0.5, color = "#4C78A8") +
        ggplot2::geom_hline(yintercept = BET_UNIT_YEN, linetype = "dashed", color = "gray40") +
        ggplot2::labs(
          title = "Upset-skipped races: model EV vs hypothetical place return",
          x = "model EV",
          y = "hypothetical place return (yen)"
        ) +
        ggplot2::theme_minimal()
      ggplot2::ggsave(
        file.path(PLOTS_DIR, "skipped_place_ev_scatter.png"),
        p2,
        width = 9,
        height = 5,
        dpi = 150
      )
    }
  }

  n_high <- nrow(high_ev)
  hypo_roi <- prep |>
    dplyr::filter(.data$skip_win) |>
    dplyr::summarise(
      roi = sum(.data$hypothetical_win_return) / (dplyr::n() * BET_UNIT_YEN) * 100
    )
  place_roi_msg <- if (nrow(place_summary) > 0L) {
    round(place_summary$hypothetical_place_roi_pct[[1]], 1)
  } else {
    NA_real_
  }
  message(
    "Skipped with EV>=", SKIPPED_EV_THRESHOLD, ": ", n_high,
    " | all-skipped hypothetical win ROI: ",
    round(hypo_roi$roi[[1]], 1), "%",
    " | upset-skipped hypothetical place ROI: ",
    place_roi_msg, "%"
  )
  invisible(list(data = prep, high_ev = high_ev, place_summary = place_summary))
}
