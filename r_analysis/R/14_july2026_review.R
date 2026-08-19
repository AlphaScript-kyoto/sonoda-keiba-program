# July 2026 monthly review tables (backtest export + optional live compare)

JULY_FROM <- "20260701"
JULY_TO <- "20260731"
COMPARE_CSV <- file.path(PROJECT_ROOT, "r_analysis", "input", "july2026_compare_summary.csv")

filter_bt_period <- function(bt, from_ymd, to_ymd) {
  bt |>
    dplyr::mutate(date_chr = as.character(.data$date)) |>
    dplyr::filter(.data$date_chr >= from_ymd, .data$date_chr <= to_ymd) |>
    dplyr::select(-"date_chr")
}

# YYYYMMDD を確実に Date へ（readr が数値にすると as.Date が壊れる）
parse_yyyymmdd <- function(x) {
  as.Date(sprintf("%08d", suppressWarnings(as.integer(as.character(x)))), format = "%Y%m%d")
}

normalize_backtest_rows <- function(bt) {
  if (is.null(bt) || nrow(bt) == 0L) return(bt)
  bt |>
    dplyr::mutate(
      date = sprintf("%08d", suppressWarnings(as.integer(as.character(.data$date)))),
      win_profile = as.character(.data$win_profile),
      exotic_profile = as.character(.data$exotic_profile),
      dplyr::across(
        dplyr::any_of(c(
          "is_volatile", "win_high", "exotic_high",
          "win_hit", "place_hit", "skip_win", "skip_place",
          "sanrenpuku_hit", "sanrentan_hit", "wide_hit"
        )),
        ~ {
          if (is.logical(.x)) return(.x)
          xchr <- tolower(as.character(.x))
          dplyr::case_when(
            xchr %in% c("true", "1", "t", "yes") ~ TRUE,
            xchr %in% c("false", "0", "f", "no") ~ FALSE,
            TRUE ~ as.logical(NA)
          )
        }
      )
    )
}

ticket_roi_summary <- function(bt, label = "period") {
  if (is.null(bt) || nrow(bt) == 0L) {
    return(tibble::tibble(label = label, n_races = 0L))
  }
  safe_roi <- function(ret, inv) {
    inv_s <- sum(inv, na.rm = TRUE)
    if (is.na(inv_s) || inv_s <= 0) return(NA_real_)
    sum(ret, na.rm = TRUE) / inv_s * 100
  }
  # group_modify 後はキー列が g から外れることがあるので存在チェック
  share_eq <- function(col, val) {
    if (!col %in% names(bt)) return(NA_real_)
    mean(bt[[col]] == val, na.rm = TRUE)
  }
  mean_col <- function(col) {
    if (!col %in% names(bt)) return(NA_real_)
    mean(bt[[col]], na.rm = TRUE)
  }
  win_played <- bt |> dplyr::filter(.data$win_invest_yen > 0L)
  place_played <- bt |> dplyr::filter(.data$place_invest_yen > 0L)
  sp <- bt |> dplyr::filter(.data$sanrenpuku_invest_yen > 0L)
  st <- bt |> dplyr::filter(.data$sanrentan_invest_yen > 0L)
  wd <- bt |> dplyr::filter(.data$wide_invest_yen > 0L)
  tibble::tibble(
    label = label,
    n_races = nrow(bt),
    win_bets = nrow(win_played),
    win_hit_rate = if (nrow(win_played)) mean(win_played$win_hit) else NA_real_,
    win_roi_pct = safe_roi(bt$win_return_yen, bt$win_invest_yen),
    place_bets = nrow(place_played),
    place_roi_pct = safe_roi(bt$place_return_yen, bt$place_invest_yen),
    sanren_bets = nrow(sp),
    sanren_hit_rate = if (nrow(sp)) mean(sp$sanrenpuku_hit) else NA_real_,
    sanren_roi_pct = safe_roi(bt$sanrenpuku_return_yen, bt$sanrenpuku_invest_yen),
    sanrentan_bets = nrow(st),
    sanrentan_hit_rate = if (nrow(st)) mean(st$sanrentan_hit) else NA_real_,
    sanrentan_roi_pct = safe_roi(bt$sanrentan_return_yen, bt$sanrentan_invest_yen),
    wide_bets = nrow(wd),
    wide_roi_pct = safe_roi(bt$wide_return_yen, bt$wide_invest_yen),
    win_ken_share = share_eq("win_profile", "堅"),
    exotic_ken_share = share_eq("exotic_profile", "堅"),
    exotic_high_share = mean_col("exotic_high")
  )
}

segment_ticket_roi <- function(bt, group_vars) {
  if (is.null(bt) || nrow(bt) == 0L) return(tibble::tibble())
  # group_modify は group 列を keys に移す → キーを戻してから集計
  bt |>
    dplyr::group_by(dplyr::across(dplyr::all_of(group_vars))) |>
    dplyr::group_modify(function(g, keys) {
      g2 <- dplyr::bind_cols(keys, g)
      ticket_roi_summary(
        g2,
        label = paste(as.character(unlist(keys, use.names = FALSE)), collapse = "|")
      )
    }) |>
    dplyr::ungroup()
}

july_weekly_roi <- function(bt) {
  if (is.null(bt) || nrow(bt) == 0L) return(tibble::tibble())
  bt |>
    dplyr::mutate(
      date_parsed = parse_yyyymmdd(.data$date),
      week = format(.data$date_parsed, "%G-W%V")
    ) |>
    dplyr::group_by(.data$week) |>
    dplyr::group_modify(function(g, keys) {
      g2 <- dplyr::bind_cols(keys, g)
      ticket_roi_summary(g2, label = as.character(keys$week[[1]]))
    }) |>
    dplyr::ungroup()
}

july_daily_roi <- function(bt) {
  if (is.null(bt) || nrow(bt) == 0L) return(tibble::tibble())
  bt |>
    dplyr::group_by(.data$date) |>
    dplyr::group_modify(function(g, keys) {
      g2 <- dplyr::bind_cols(keys, g)
      ticket_roi_summary(g2, label = as.character(keys$date[[1]]))
    }) |>
    dplyr::ungroup() |>
    dplyr::arrange(.data$date)
}

july_loss_drivers <- function(bt) {
  # races that hurt Sanrenpuku most (invested, no hit, high stake)
  bt |>
    dplyr::filter(.data$sanrenpuku_invest_yen > 0L) |>
    dplyr::mutate(
      sp_loss = .data$sanrenpuku_invest_yen - .data$sanrenpuku_return_yen,
      cal_gap = .data$win_prob_top - dplyr::if_else(.data$win_hit, 1, 0)
    ) |>
    dplyr::arrange(dplyr::desc(.data$sp_loss)) |>
    dplyr::select(
      "date", "race_no", "race_name", "win_profile", "exotic_profile",
      "is_volatile", "win_prob_top", "prob_gap", "exotic_prob_top", "exotic_prob_gap",
      "pred_umaban", "actual_1st", "pred_odds",
      "sanrenpuku_invest_yen", "sanrenpuku_return_yen", "sp_loss",
      "sanrenpuku_hit", "wide_hit", "win_hit"
    )
}

july_calibration_bins <- function(bt, n_bins = 10L) {
  if (is.null(bt) || nrow(bt) < n_bins) return(tibble::tibble())
  bt |>
    dplyr::mutate(
      prob_bin = dplyr::ntile(.data$win_prob_top, n_bins)
    ) |>
    dplyr::group_by(.data$prob_bin) |>
    dplyr::summarise(
      n = dplyr::n(),
      mean_pred = mean(.data$win_prob_top, na.rm = TRUE),
      actual_win_rate = mean(.data$win_hit, na.rm = TRUE),
      calibration_gap = .data$mean_pred - .data$actual_win_rate,
      mean_odds = mean(suppressWarnings(as.numeric(.data$pred_odds)), na.rm = TRUE),
      .groups = "drop"
    )
}

load_compare_summary <- function() {
  if (!file.exists(COMPARE_CSV)) return(NULL)
  readr::read_csv(COMPARE_CSV, show_col_types = FALSE, progress = FALSE)
}

summarise_compare <- function(cmp) {
  if (is.null(cmp) || nrow(cmp) == 0L) return(tibble::tibble())
  cmp |>
    dplyr::group_by(.data$snapshot) |>
    dplyr::summarise(
      days = dplyr::n(),
      races = sum(.data$n_races, na.rm = TRUE),
      top3_final_rate = sum(.data$top3_final, na.rm = TRUE) /
        sum(.data$top3_final_n, na.rm = TRUE),
      top3_live_rate = sum(.data$top3_live, na.rm = TRUE) /
        sum(.data$top3_live_n, na.rm = TRUE),
      mean_mark_match = stats::weighted.mean(.data$mark_match_pct, .data$n_races, na.rm = TRUE),
      mean_win_prof_match = stats::weighted.mean(.data$win_prof_match_pct, .data$n_races, na.rm = TRUE),
      mean_ex_prof_match = stats::weighted.mean(.data$ex_prof_match_pct, .data$n_races, na.rm = TRUE),
      mean_ex_conf_match = stats::weighted.mean(.data$ex_conf_match_pct, .data$n_races, na.rm = TRUE),
      .groups = "drop"
    )
}

write_july_guidance_md <- function(overall, by_ex, cal, cmp_sum, out_path) {
  lines <- c(
    "# 2026-07 ロジック見直しメモ（R 自動生成）",
    "",
    "生成元: `r_analysis/scripts/10_july2026_review.R`",
    "",
    "## 1. 7月バックテスト要約",
    ""
  )
  if (!is.null(overall) && nrow(overall) > 0L) {
    o <- overall[1, ]
    lines <- c(
      lines,
      sprintf("- レース数: %s", o$n_races),
      sprintf("- 単勝ROI: %.1f%% (bets=%s, hit=%.1f%%)", o$win_roi_pct, o$win_bets, 100 * o$win_hit_rate),
      sprintf("- 三連複ROI: %.1f%% (bets=%s, hit=%.1f%%)", o$sanren_roi_pct, o$sanren_bets, 100 * o$sanren_hit_rate),
      sprintf("- 三連単ROI: %.1f%%", o$sanrentan_roi_pct),
      sprintf("- ワイドROI: %.1f%%", o$wide_roi_pct),
      sprintf("- 堅シェア 単勝プロフ: %.1f%% / 三連プロフ: %.1f%%", 100 * o$win_ken_share, 100 * o$exotic_ken_share),
      ""
    )
  } else {
    lines <- c(lines, "- (backtest_rows なし → export を先に実行)", "")
  }

  lines <- c(lines, "## 2. 改善仮説（データ確認用チェックリスト）", "")
  lines <- c(
    lines,
    "1. **校正ギャップ**: `july_calibration_bins.csv` で mean_pred >> actual なら自信度閾値を上げる候補",
    "2. **堅/荒のROI差**: `july_segment_exotic_profile.csv` で荒だけ崩れていないか",
    "3. **週次クラッシュ**: `july_weekly_roi.csv` で 7/22 週など特定週だけ悪化していないか",
    "4. **ライブ不安定**: `july_compare_by_snapshot.csv` の ex_prof match が低い → T-10再判定/見送り強化",
    "5. **損失レース**: `july_sanren_loss_drivers.csv` 上位の共通点（クラス・距離・volatile）",
    "6. **複勝見送り**: `skipped_*` 系（09）を 7 月行に絞って機会損失を確認",
    ""
  )

  if (!is.null(by_ex) && nrow(by_ex) > 0L) {
    lines <- c(lines, "## 3. 三連系プロフ別", "")
    for (i in seq_len(nrow(by_ex))) {
      r <- by_ex[i, ]
      lines <- c(
        lines,
        sprintf(
          "- %s: sanren ROI %.1f%% / hit %.1f%% (n=%s)",
          r$exotic_profile, r$sanren_roi_pct, 100 * r$sanren_hit_rate, r$sanren_bets
        )
      )
    }
    lines <- c(lines, "")
  }

  if (!is.null(cal) && nrow(cal) > 0L) {
    worst <- cal |> dplyr::slice_max(order_by = .data$calibration_gap, n = 3, with_ties = FALSE)
    lines <- c(lines, "## 4. 校正ギャップが大きいビン", "")
    for (i in seq_len(nrow(worst))) {
      r <- worst[i, ]
      lines <- c(
        lines,
        sprintf(
          "- bin %s: pred=%.1f%% actual=%.1f%% gap=%.1fpt (n=%s)",
          r$prob_bin, 100 * r$mean_pred, 100 * r$actual_win_rate, 100 * r$calibration_gap, r$n
        )
      )
    }
    lines <- c(lines, "")
  }

  if (!is.null(cmp_sum) && nrow(cmp_sum) > 0L) {
    lines <- c(lines, "## 5. 当日スナップ vs Final", "")
    for (i in seq_len(nrow(cmp_sum))) {
      r <- cmp_sum[i, ]
      lines <- c(
        lines,
        sprintf(
          "- %s: final top3 %.1f%% / ◎match %.0f%% / ex_prof match %.0f%%",
          r$snapshot, 100 * r$top3_final_rate, r$mean_mark_match, r$mean_ex_prof_match
        )
      )
    }
    lines <- c(lines, "")
  }

  lines <- c(
    lines,
    "## 6. 次アクション（本番ロジック変更は検証後）",
    "",
    "- まず Python `scripts/backtest_bets.py --from 20260701 --to 20260731` と本レポートを突合",
    "- 閾値を動かすなら `scripts/tune_exotic_thresholds.py` を **7月だけに過学習しない** よう 1-6月 holdout 併用",
    "- T-10 のプロフィール反転時は送信見送り、をコード化する前に `july_compare_by_day.csv` で損失減効果を試算",
    ""
  )
  dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, out_path, useBytes = FALSE)
  invisible(out_path)
}

save_july2026_review_tables <- function() {
  ensure_output_dirs()
  bt_all <- load_backtest_rows()
  if (is.null(bt_all)) {
    stop(
      "r_analysis/input/backtest_rows.csv がありません。\n",
      "先に: .\\.venv\\Scripts\\python.exe scripts/export_backtest_for_r.py --from 20260701 --to 20260731"
    )
  }
  bt_all <- normalize_backtest_rows(bt_all)

  # Prefer multi-month export if available so comparison tables work
  periods <- list(
    list(label = "2026-07", from = "20260701", to = "20260731"),
    list(label = "2026-06", from = "20260601", to = "20260630"),
    list(label = "2026-04-05", from = "20260401", to = "20260531"),
    list(label = "2026-01-03", from = "20260101", to = "20260331"),
    list(label = "2026-01-07", from = "20260101", to = "20260731")
  )

  period_rows <- lapply(periods, function(p) {
    ticket_roi_summary(filter_bt_period(bt_all, p$from, p$to), p$label)
  })
  period_tbl <- dplyr::bind_rows(period_rows)
  save_csv_table(period_tbl, "july_period_compare.csv")

  july <- filter_bt_period(bt_all, JULY_FROM, JULY_TO)
  if (nrow(july) == 0L) {
    stop("backtest_rows に 202607 の行がありません。export の --from/--to を確認してください。")
  }

  overall <- ticket_roi_summary(july, "2026-07")
  save_csv_table(overall, "july_overall_roi.csv")
  save_csv_table(july_daily_roi(july), "july_daily_roi.csv")
  save_csv_table(july_weekly_roi(july), "july_weekly_roi.csv")

  by_win <- segment_ticket_roi(july, "win_profile")
  by_ex <- segment_ticket_roi(july, "exotic_profile")
  by_volatile <- segment_ticket_roi(
    july |> dplyr::mutate(vol = dplyr::if_else(.data$is_volatile, "volatile", "stable")),
    "vol"
  )
  by_ex_high <- segment_ticket_roi(
    july |> dplyr::mutate(ex_h = dplyr::if_else(.data$exotic_high, "high", "normal")),
    "ex_h"
  )
  by_prof_conf <- segment_ticket_roi(
    july |>
      dplyr::mutate(
        ex_h = dplyr::if_else(.data$exotic_high, "high", "normal")
      ),
    c("exotic_profile", "ex_h")
  )

  save_csv_table(by_win, "july_segment_win_profile.csv")
  save_csv_table(by_ex, "july_segment_exotic_profile.csv")
  save_csv_table(by_volatile, "july_segment_volatile.csv")
  save_csv_table(by_ex_high, "july_segment_exotic_confidence.csv")
  save_csv_table(by_prof_conf, "july_segment_profile_x_conf.csv")

  loss <- july_loss_drivers(july)
  save_csv_table(loss, "july_sanren_loss_drivers.csv")
  save_csv_table(utils::head(loss, 30L), "july_sanren_loss_top30.csv")

  cal <- july_calibration_bins(july)
  save_csv_table(cal, "july_calibration_bins.csv")

  # class-ish proxy from race_name prefix is noisy; use invest>0 exotic only hit factors
  sp_only <- july |> dplyr::filter(.data$sanrenpuku_invest_yen > 0L)
  if (nrow(sp_only) > 0L) {
    sp_bins <- sp_only |>
      dplyr::mutate(
        gap_bin = cut(
          .data$exotic_prob_gap,
          breaks = c(-Inf, 0.3, 0.5, 0.7, 0.9, Inf),
          labels = c("<0.3", "0.3-0.5", "0.5-0.7", "0.7-0.9", ">=0.9"),
          right = FALSE
        )
      ) |>
      dplyr::group_by(.data$exotic_profile, .data$gap_bin) |>
      dplyr::summarise(
        n = dplyr::n(),
        hit_rate = mean(.data$sanrenpuku_hit, na.rm = TRUE),
        roi_pct = sum(.data$sanrenpuku_return_yen) / sum(.data$sanrenpuku_invest_yen) * 100,
        .groups = "drop"
      )
    save_csv_table(sp_bins, "july_sanren_by_gap_bin.csv")
  }

  cmp <- load_compare_summary()
  cmp_sum <- summarise_compare(cmp)
  if (!is.null(cmp)) {
    save_csv_table(cmp, "july_compare_by_day.csv")
    save_csv_table(cmp_sum, "july_compare_by_snapshot.csv")
  }

  report_path <- file.path(REPORTS_DIR, "july2026_logic_guidance.md")
  write_july_guidance_md(overall, by_ex, cal, cmp_sum, report_path)
  message("Wrote: ", report_path)
  message("Tables under r_analysis/output/tables/july_*.csv")
  invisible(list(overall = overall, period = period_tbl, compare = cmp_sum))
}
