
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
  identical(sort(as.character(selected)), sort(as.character(c(u1, u2, u3))))
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
