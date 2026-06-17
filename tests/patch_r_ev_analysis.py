"""Patch r_analysis R files for EV decile + skipped place analysis (UTF-8 safe)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch_settings() -> None:
    path = ROOT / "r_analysis" / "config" / "settings.R"
    text = path.read_text(encoding="utf-8")
    if "EV_PROFITABLE_MIN_BETS" in text:
        return
    text = text.replace(
        "SKIPPED_EV_THRESHOLD <- 1.0\n",
        "SKIPPED_EV_THRESHOLD <- 1.0\n"
        "EV_PROFITABLE_MIN_BETS <- 100L\n"
        "EV_PROFITABLE_MIN_ROI_PCT <- 100\n"
        "PLACE_OPPORTUNITY_MIN_BETS <- 30L\n"
        "PLACE_OPPORTUNITY_MIN_ROI_PCT <- 100\n"
        'REPORTS_DIR <- file.path(OUTPUT_DIR, "reports")\n',
    )
    text = text.replace(
        "  dir.create(PLOTS_DIR, recursive = TRUE, showWarnings = FALSE)\n}",
        "  dir.create(PLOTS_DIR, recursive = TRUE, showWarnings = FALSE)\n"
        "  dir.create(REPORTS_DIR, recursive = TRUE, showWarnings = FALSE)\n}",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def write_11_expected_value() -> None:
    path = ROOT / "r_analysis" / "R" / "11_expected_value.R"
    path.write_text(_ELEVEN_CONTENT, encoding="utf-8", newline="\n")


def write_13_skipped_races() -> None:
    path = ROOT / "r_analysis" / "R" / "13_skipped_races.R"
    path.write_text(_THIRTEEN_CONTENT, encoding="utf-8", newline="\n")


_ELEVEN_CONTENT = r'''load_or_fit_logistic_win <- function(df) {
  fit_path <- file.path(MODELS_DIR, "logistic_win_fit.rds")
  if (file.exists(fit_path)) {
    message("Using saved logistic model: ", fit_path)
    return(readRDS(fit_path))
  }
  message("No saved model; fitting logistic_win on filtered master...")
  fit_logistic_win(df)
}

attach_logistic_predictions <- function(df, fit) {
  feats <- setdiff(names(stats::coef(fit)), "(Intercept)")
  missing_feats <- setdiff(feats, names(df))
  if (length(missing_feats) > 0L) {
    stop("Missing model features in master: ", paste(missing_feats, collapse = ", "))
  }
  work <- coerce_model_matrix(df, feats) |>
    dplyr::filter(!is.na(.data$odds_num), .data$odds_num > 0)
  complete <- stats::complete.cases(work[, feats, drop = FALSE])
  work$pred_win_prob <- NA_real_
  if (any(complete)) {
    work$pred_win_prob[complete] <- stats::predict(
      fit,
      newdata = work[complete, , drop = FALSE],
      type = "response"
    )
  }
  work |>
    dplyr::filter(!is.na(.data$pred_win_prob)) |>
    dplyr::mutate(
      model_ev = .data$pred_win_prob * .data$odds_num,
      realized_return = dplyr::if_else(.data$is_win, .data$odds_num, 0)
    )
}

add_flat_bet_roi_columns <- function(tbl) {
  tbl |>
    dplyr::mutate(
      n_bets = .data$n,
      total_stake = .data$n_bets * BET_UNIT_YEN,
      total_return = .data$mean_realized_return * .data$n_bets * BET_UNIT_YEN,
      roi_pct = dplyr::if_else(
        .data$total_stake > 0,
        .data$total_return / .data$total_stake * 100,
        NA_real_
      ),
      profit_yen = .data$total_return - .data$total_stake,
      calibration_gap = .data$mean_pred_prob - .data$hit_rate,
      is_stable_profitable = .data$roi_pct >= EV_PROFITABLE_MIN_ROI_PCT &
        .data$profit_yen > 0 &
        .data$n_bets >= EV_PROFITABLE_MIN_BETS
    )
}

summarise_ev_by_decile <- function(df, n_bins = EV_DECILE_N, decile_col = "pred_win_prob") {
  df |>
    dplyr::mutate(decile = dplyr::ntile(.data[[decile_col]], n_bins)) |>
    dplyr::group_by(.data$decile) |>
    dplyr::summarise(
      n = dplyr::n(),
      n_races = dplyr::n_distinct(.data$race_id),
      decile_min = min(.data[[decile_col]], na.rm = TRUE),
      decile_max = max(.data[[decile_col]], na.rm = TRUE),
      mean_pred_prob = mean(.data$pred_win_prob, na.rm = TRUE),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      mean_odds = mean(.data$odds_num, na.rm = TRUE),
      mean_model_ev = mean(.data$model_ev, na.rm = TRUE),
      empirical_ev = .data$hit_rate * .data$mean_odds,
      mean_realized_return = mean(.data$realized_return, na.rm = TRUE),
      model_ev_gt_1 = .data$mean_model_ev > 1,
      empirical_ev_gt_1 = .data$empirical_ev > 1,
      .groups = "drop"
    ) |>
    dplyr::arrange(.data$decile) |>
    add_flat_bet_roi_columns()
}

identify_stable_profitable_deciles <- function(decile_tbl) {
  decile_tbl |>
    dplyr::filter(.data$is_stable_profitable) |>
    dplyr::arrange(dplyr::desc(.data$roi_pct))
}

prepare_backtest_ev_df <- function(bt) {
  bt |>
    dplyr::mutate(
      pred_odds_num = suppressWarnings(as.numeric(.data$pred_odds)),
      model_ev = .data$win_prob_top * .data$pred_odds_num,
      hypothetical_win_return = dplyr::if_else(
        .data$win_hit,
        .data$pred_odds_num * BET_UNIT_YEN,
        0
      )
    ) |>
    dplyr::filter(
      !is.na(.data$pred_odds_num),
      .data$pred_odds_num > 0,
      .data$win_high
    )
}

attach_hypothetical_place_return <- function(bt) {
  if ("hypothetical_place_return_yen" %in% names(bt)) {
    return(bt)
  }
  if ("place_payout_yen" %in% names(bt)) {
    return(bt |>
      dplyr::mutate(
        hypothetical_place_return_yen = dplyr::if_else(
          .data$place_hit,
          .data$place_payout_yen,
          0L
        )
      ))
  }
  bt |>
    dplyr::mutate(
      hypothetical_place_return_yen = dplyr::if_else(
        .data$place_hit & !.data$skip_place,
        .data$place_return_yen,
        0L
      )
    )
}

summarise_production_ev_deciles <- function(bt, n_bins = EV_DECILE_N) {
  prep <- prepare_backtest_ev_df(bt)
  prep <- attach_hypothetical_place_return(prep)
  prep |>
    dplyr::mutate(decile = dplyr::ntile(.data$win_prob_top, n_bins)) |>
    dplyr::group_by(.data$decile) |>
    dplyr::summarise(
      n_races = dplyr::n(),
      win_prob_min = min(.data$win_prob_top, na.rm = TRUE),
      win_prob_max = max(.data$win_prob_top, na.rm = TRUE),
      prob_gap_mean = mean(.data$prob_gap, na.rm = TRUE),
      mean_model_ev = mean(.data$model_ev, na.rm = TRUE),
      win_hit_rate = mean(.data$win_hit, na.rm = TRUE),
      place_hit_rate = mean(.data$place_hit, na.rm = TRUE),
      mean_pred_odds = mean(.data$pred_odds_num, na.rm = TRUE),
      win_roi_pct = sum(.data$hypothetical_win_return) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      place_roi_pct = sum(.data$hypothetical_place_return_yen) /
        (.data$n_races * BET_UNIT_YEN) * 100,
      actual_win_roi_pct = sum(.data$win_return_yen) /
        sum(.data$win_invest_yen) * 100,
      actual_place_roi_pct = sum(.data$place_return_yen) /
        sum(.data$place_invest_yen) * 100,
      share_skipped_win = mean(.data$skip_win, na.rm = TRUE),
      .groups = "drop"
    ) |>
    dplyr::mutate(
      n_bets = .data$n_races,
      total_stake = .data$n_bets * BET_UNIT_YEN,
      total_return = .data$win_roi_pct / 100 * .data$total_stake,
      roi_pct = .data$win_roi_pct,
      profit_yen = .data$total_return - .data$total_stake,
      is_stable_profitable = .data$roi_pct >= EV_PROFITABLE_MIN_ROI_PCT &
        .data$profit_yen > 0 &
        .data$n_bets >= EV_PROFITABLE_MIN_BETS
    ) |>
    dplyr::arrange(.data$decile)
}

write_text_report <- function(filename, lines) {
  path <- file.path(REPORTS_DIR, filename)
  writeLines(lines, path, useBytes = FALSE)
  message("Wrote report: ", path)
  invisible(path)
}

write_ev_confidence_guidance <- function(
    prob_decile_tbl,
    model_ev_decile_tbl,
    stable_prob,
    stable_model_ev,
    production_decile_tbl = NULL
) {
  overall <- prob_decile_tbl |>
    dplyr::summarise(
      n = sum(.data$n_bets),
      hit_rate = stats::weighted.mean(.data$hit_rate, .data$n_bets),
      mean_model_ev = stats::weighted.mean(.data$mean_model_ev, .data$n_bets),
      empirical_ev = stats::weighted.mean(.data$empirical_ev, .data$n_bets),
      roi_pct = sum(.data$total_return) / sum(.data$total_stake) * 100,
      mean_cal_gap = stats::weighted.mean(.data$calibration_gap, .data$n_bets),
      .groups = "drop"
    )

  high_deciles <- prob_decile_tbl |>
    dplyr::filter(.data$decile >= max(1L, EV_DECILE_N - 2L))

  lines <- c(
    "# EV decile analysis — confidence threshold guidance",
    "",
    paste0("Generated: ", format(Sys.time(), "%Y-%m-%d %H:%M")),
    paste0("Analysis period: master from ", ANALYSIS_DATE_FROM),
    "",
    "## 1. Summary (logistic model, flat win 100yen/bet)",
    "",
    paste0("- Total bets: ", overall$n),
    paste0("- Overall ROI: ", round(overall$roi_pct, 1), "%"),
    paste0("- Weighted hit rate: ", round(100 * overall$hit_rate, 2), "%"),
    paste0("- Weighted model EV: ", round(overall$mean_model_ev, 3)),
    paste0("- Weighted empirical EV: ", round(overall$empirical_ev, 3)),
    paste0("- Mean calibration gap (pred - hit): ", round(overall$mean_cal_gap, 4)),
    "",
    "## 2. Stable profitable deciles (ROI>=100%, profit>0, n>=100)",
    ""
  )

  if (nrow(stable_prob) == 0L) {
    lines <- c(lines, "- **Probability decile: none** — no decile meets all three criteria.")
  } else {
    lines <- c(
      lines,
      "- **Probability decile (stable):**",
      paste0(
        "  - decile ", stable_prob$decile,
        ": ROI ", round(stable_prob$roi_pct, 1), "%, profit ",
        round(stable_prob$profit_yen), " yen, n=", stable_prob$n_bets,
        ", pred_prob [", round(stable_prob$decile_min, 3), "-",
        round(stable_prob$decile_max, 3), "]"
      )
    )
  }

  if (nrow(stable_model_ev) == 0L) {
    lines <- c(lines, "- **Model-EV decile: none** — no decile meets all three criteria.")
  } else {
    lines <- c(
      lines,
      "- **Model-EV decile (stable):**",
      paste0(
        "  - decile ", stable_model_ev$decile,
        ": ROI ", round(stable_model_ev$roi_pct, 1), "%, profit ",
        round(stable_model_ev$profit_yen), " yen, n=", stable_model_ev$n_bets
      )
    )
  }

  lines <- c(
    lines,
    "",
    "## 3. High-probability deciles (top 3 deciles)",
    "",
    paste0(
      "- ROI range: ", round(min(high_deciles$roi_pct), 1), "% - ",
      round(max(high_deciles$roi_pct), 1), "%"
    ),
    paste0(
      "- Model EV>1 deciles in top-3: ",
      sum(high_deciles$model_ev_gt_1), "/", nrow(high_deciles)
    ),
    paste0(
      "- Empirical EV>1 deciles in top-3: ",
      sum(high_deciles$empirical_ev_gt_1), "/", nrow(high_deciles)
    ),
    paste0(
      "- Avg calibration gap (top-3): ",
      round(mean(high_deciles$calibration_gap), 4)
    ),
    "",
    "## 4. Mapping to production confidence (bets.py)",
    "",
    "Current win_high thresholds (DEFAULT_WIN_THRESHOLDS):",
    "- win_prob >= 85%",
    "- prob_gap >= 60%",
    "- mode = and (both required)",
    "",
    "Statistical suggestions:"
  )

  if (nrow(stable_prob) == 0L) {
    lines <- c(
      lines,
      "1. **Do not loosen** win_prob / prob_gap based on logistic EV deciles — no stable profitable band exists under flat-win criteria.",
      "2. Model EV exceeds empirical EV in upper deciles (optimism). Prefer **tighter** calibration or higher effective threshold before adding win bets.",
      paste0(
        "3. Top deciles still show ROI ",
        round(mean(high_deciles$roi_pct), 1),
        "% on average — below 100%. Confidence 'high' is a **filter for exotic bets**, not proof of +EV win flat betting."
      )
    )
  } else {
    lines <- c(
      lines,
      paste0(
        "1. Stable bands exist at decile(s): ",
        paste(stable_prob$decile, collapse = ", "),
        ". Consider aligning win_prob threshold with lower bound pred_prob ",
        round(min(stable_prob$decile_min), 2),
        " only after backtest validation on **played** races."
      ),
      "2. Keep prob_gap filter; gap<=0.65 is an upset signal in bets.py — do not remove.",
      "3. Re-run export_backtest_for_r.py after any threshold change and compare skipped_*.csv."
    )
  }

  if (!is.null(production_decile_tbl) && nrow(production_decile_tbl) > 0L) {
    prod_stable <- production_decile_tbl |>
      dplyr::filter(.data$is_stable_profitable)
    prod_high <- production_decile_tbl |>
      dplyr::filter(.data$decile >= max(1L, EV_DECILE_N - 2L))
    lines <- c(
      lines,
      "",
      "## 5. Production model (backtest_rows, win_high races)",
      "",
      paste0(
        "- win_prob deciles analysed: ", nrow(production_decile_tbl),
        " (n_bets per decile ~", round(mean(production_decile_tbl$n_bets)), ")"
      ),
      if (nrow(prod_stable) == 0L) {
        "- Stable profitable win decile: **none** on hypothetical ◎ win bets."
      } else {
        paste0(
          "- Stable profitable win decile(s): ",
          paste(prod_stable$decile, collapse = ", "),
          " (win_prob ", round(min(prod_stable$win_prob_min), 2),
          "-", round(max(prod_stable$win_prob_max), 2), ")"
        )
      },
      paste0(
        "- Top-3 decile hypothetical win ROI: ",
        round(mean(prod_high$win_roi_pct), 1), "%"
      ),
      paste0(
        "- Top-3 decile hypothetical place ROI: ",
        round(mean(prod_high$place_roi_pct), 1), "%"
      ),
      paste0(
        "- Top-3 decile actual win ROI (current skip rules): ",
        round(mean(prod_high$actual_win_roi_pct, na.rm = TRUE), 1), "%"
      ),
      "",
      "Production note: win_high already enforces win_prob>=85% and gap>=60%. Decile splits within win_high show where skip rules help or hurt — see skipped_place_guidance.md."
    )
  }

  lines <- c(
    lines,
    "",
    "## 6. Output files",
    "- ev_by_prob_decile.csv",
    "- ev_by_model_ev_decile.csv",
    "- ev_stable_profitable_deciles.csv",
    "- ev_production_win_prob_decile.csv (if backtest export exists)",
    ""
  )
  write_text_report("ev_confidence_guidance.md", lines)
}

save_expected_value_plots <- function(decile_tbl) {
  if (!requireNamespace("ggplot2", quietly = TRUE)) {
    message("Skip EV plot: install ggplot2")
    return(invisible(NULL))
  }
  long <- decile_tbl |>
    tidyr::pivot_longer(
      cols = c("empirical_ev", "mean_model_ev"),
      names_to = "ev_type",
      values_to = "ev_value"
    ) |>
    dplyr::mutate(
      ev_label = dplyr::recode(
        .data$ev_type,
        empirical_ev = "hit_rate x mean_odds",
        mean_model_ev = "mean(pred_prob x odds)"
      )
    )

  p1 <- ggplot2::ggplot(decile_tbl, ggplot2::aes(x = .data$decile, y = .data$empirical_ev)) +
    ggplot2::geom_col(fill = "#4C78A8") +
    ggplot2::geom_line(
      ggplot2::aes(x = .data$decile, y = .data$mean_model_ev),
      color = "#E45756",
      linewidth = 1
    ) +
    ggplot2::geom_point(
      ggplot2::aes(x = .data$decile, y = .data$mean_model_ev),
      color = "#E45756",
      size = 2
    ) +
    ggplot2::geom_hline(yintercept = 1, linetype = "dashed", color = "gray40") +
    ggplot2::labs(
      title = "Expected value by predicted-probability decile",
      subtitle = "Bars: empirical EV; line: model EV",
      x = "Predicted win probability decile (1=low, 10=high)",
      y = "Expected return per 1-unit stake"
    ) +
    ggplot2::theme_minimal()

  p2 <- ggplot2::ggplot(
    long,
    ggplot2::aes(
      x = factor(.data$decile),
      y = .data$ev_value,
      fill = .data$ev_label
    )
  ) +
    ggplot2::geom_col(position = "dodge") +
    ggplot2::geom_hline(yintercept = 1, linetype = "dashed", color = "gray40") +
    ggplot2::labs(
      title = "Model vs empirical EV by decile",
      x = "Probability decile",
      y = "EV",
      fill = NULL
    ) +
    ggplot2::theme_minimal() +
    ggplot2::theme(legend.position = "bottom")

  if ("roi_pct" %in% names(decile_tbl)) {
    p3 <- ggplot2::ggplot(decile_tbl, ggplot2::aes(x = .data$decile, y = .data$roi_pct)) +
      ggplot2::geom_col(
        ggplot2::aes(fill = .data$is_stable_profitable),
        show.legend = TRUE
      ) +
      ggplot2::geom_hline(yintercept = EV_PROFITABLE_MIN_ROI_PCT, linetype = "dashed") +
      ggplot2::scale_fill_manual(
        values = c("TRUE" = "#54A24B", "FALSE" = "#BAB0AC"),
        labels = c("FALSE" = "other", "TRUE" = "stable profitable"),
        name = NULL
      ) +
      ggplot2::labs(
        title = "Flat-win ROI by probability decile",
        x = "Decile",
        y = "ROI %"
      ) +
      ggplot2::theme_minimal()
    ggplot2::ggsave(
      file.path(PLOTS_DIR, "ev_roi_by_prob_decile.png"),
      p3,
      width = 9,
      height = 5,
      dpi = 150
    )
  }

  ggplot2::ggsave(
    file.path(PLOTS_DIR, "ev_by_prob_decile.png"),
    p1,
    width = 9,
    height = 5,
    dpi = 150
  )
  ggplot2::ggsave(
    file.path(PLOTS_DIR, "ev_model_vs_empirical_decile.png"),
    p2,
    width = 9,
    height = 5,
    dpi = 150
  )
  invisible(list(bar = p1, dodge = p2))
}

save_expected_value_tables <- function(df) {
  fit <- load_or_fit_logistic_win(df)
  scored <- attach_logistic_predictions(df, fit)

  prob_decile_tbl <- summarise_ev_by_decile(scored, n_bins = EV_DECILE_N, decile_col = "pred_win_prob") |>
    dplyr::rename(prob_decile = .data$decile)
  save_csv_table(prob_decile_tbl, "ev_by_prob_decile.csv")

  model_ev_tbl <- summarise_ev_by_decile(scored, n_bins = EV_DECILE_N, decile_col = "model_ev") |>
    dplyr::rename(model_ev_decile = .data$decile)
  save_csv_table(model_ev_tbl, "ev_by_model_ev_decile.csv")

  stable_prob <- identify_stable_profitable_deciles(
    prob_decile_tbl |> dplyr::rename(decile = .data$prob_decile)
  )
  stable_model_ev <- identify_stable_profitable_deciles(
    model_ev_tbl |> dplyr::rename(decile = .data$model_ev_decile)
  )
  stable_all <- dplyr::bind_rows(
    stable_prob |> dplyr::mutate(decile_type = "pred_win_prob"),
    stable_model_ev |> dplyr::mutate(decile_type = "model_ev")
  )
  save_csv_table(stable_all, "ev_stable_profitable_deciles.csv")

  positive <- prob_decile_tbl |>
    dplyr::filter(.data$empirical_ev_gt_1 | .data$model_ev_gt_1)
  save_csv_table(positive, "ev_positive_deciles.csv")

  overall <- scored |>
    dplyr::summarise(
      n = dplyr::n(),
      hit_rate = mean(.data$is_win, na.rm = TRUE),
      mean_odds = mean(.data$odds_num, na.rm = TRUE),
      mean_model_ev = mean(.data$model_ev, na.rm = TRUE),
      empirical_ev = .data$hit_rate * .data$mean_odds,
      .groups = "drop"
    )
  save_csv_table(overall, "ev_overall_summary.csv")

  production_decile_tbl <- NULL
  bt <- load_backtest_rows()
  if (!is.null(bt)) {
    production_decile_tbl <- summarise_production_ev_deciles(bt)
    save_csv_table(production_decile_tbl, "ev_production_win_prob_decile.csv")
    prod_stable <- production_decile_tbl |> dplyr::filter(.data$is_stable_profitable)
    save_csv_table(prod_stable, "ev_production_stable_profitable_deciles.csv")
  } else {
    message("Skip production EV deciles: backtest_rows.csv not found")
  }

  save_expected_value_plots(prob_decile_tbl |> dplyr::rename(decile = .data$prob_decile))
  write_ev_confidence_guidance(
    prob_decile_tbl |> dplyr::rename(decile = .data$prob_decile),
    model_ev_tbl |> dplyr::rename(decile = .data$model_ev_decile),
    stable_prob,
    stable_model_ev,
    production_decile_tbl
  )

  message(
    "EV deciles with empirical EV > 1: ",
    sum(prob_decile_tbl$empirical_ev_gt_1, na.rm = TRUE),
    " / ",
    nrow(prob_decile_tbl),
    " | stable profitable (prob): ",
    nrow(stable_prob)
  )
  invisible(list(
    scored = scored,
    prob_deciles = prob_decile_tbl,
    stable = stable_all
  ))
}
'''

_THIRTEEN_CONTENT = r'''prepare_backtest_skip_df <- function(bt) {
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
'''


def patch_export_backtest() -> None:
    path = ROOT / "scripts" / "export_backtest_for_r.py"
    text = path.read_text(encoding="utf-8")
    if "hypothetical_place_return_yen" in text:
        return
    text = text.replace(
        '                "place_return_yen": place_return,\n',
        '                "place_payout_yen": rec.place_payout,\n'
        '                "hypothetical_place_return_yen": (\n'
        "                    rec.place_payout if rec.place_hit else 0\n"
        "                ),\n"
        '                "place_return_yen": place_return,\n',
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    patch_settings()
    write_11_expected_value()
    write_13_skipped_races()
    patch_export_backtest()
    for rel in [
        "r_analysis/R/11_expected_value.R",
        "r_analysis/R/13_skipped_races.R",
        "r_analysis/config/settings.R",
    ]:
        p = ROOT / rel
        print(rel, "nulls", p.read_bytes().count(b"\x00"))
    print("done")


if __name__ == "__main__":
    main()
