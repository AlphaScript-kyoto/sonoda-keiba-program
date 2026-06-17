get_project_root <- function() {
  env_root <- Sys.getenv("SONODA_KEIBA_ROOT", unset = "")
  if (nzchar(env_root)) {
    return(normalizePath(env_root, winslash = "/", mustWork = TRUE))
  }
  script_dir <- tryCatch({
    args <- commandArgs(trailingOnly = FALSE)
    f <- sub("^--file=", "", args[grep("^--file=", args)])
    if (length(f) > 0) dirname(normalizePath(f[1], winslash = "/"))
    else getwd()
  }, error = function(e) getwd())
  candidates <- c(
    normalizePath(file.path(script_dir, "..", ".."), winslash = "/", mustWork = FALSE),
    normalizePath(script_dir, winslash = "/", mustWork = FALSE),
    normalizePath(getwd(), winslash = "/", mustWork = FALSE)
  )
  for (root in unique(candidates)) {
    if (dir.exists(file.path(root, "data", "processed"))) return(root)
  }
  stop("Set SONODA_KEIBA_ROOT or run from repo root.")
}

PROJECT_ROOT <- get_project_root()
MASTER_CSV <- file.path(PROJECT_ROOT, "data", "processed", "horses_master.csv")
PAYBACK_CACHE_JSON <- file.path(PROJECT_ROOT, "data", "processed", "payback_cache.json")
OUTPUT_DIR <- file.path(PROJECT_ROOT, "r_analysis", "output")
BET_UNIT_YEN <- 100L
TABLES_DIR <- file.path(OUTPUT_DIR, "tables")
MODELS_DIR <- file.path(OUTPUT_DIR, "models")
PLOTS_DIR <- file.path(OUTPUT_DIR, "plots")
ANALYSIS_DATE_FROM <- "20240101"
ANALYSIS_DATE_TO <- NULL
MIN_FEATURE_NONNA_RATE <- 0.15
POPULARITY_BINS <- c(1, 2, 3, 4, 6, 9, Inf)
ODDS_BREAKS <- c(0, 2, 3, 5, 10, 20, 50, Inf)
EV_DECILE_N <- 10L
JOCKEY_TRACK_MIN_BETS <- 30L
JOCKEY_TRACK_ROI_LIFT_MIN <- 1.15
SKIPPED_EV_THRESHOLD <- 1.0
EV_PROFITABLE_MIN_BETS <- 100L
EV_PROFITABLE_MIN_ROI_PCT <- 100
PLACE_OPPORTUNITY_MIN_BETS <- 30L
PLACE_OPPORTUNITY_MIN_ROI_PCT <- 100
REPORTS_DIR <- file.path(OUTPUT_DIR, "reports")

ensure_output_dirs <- function() {
  dir.create(TABLES_DIR, recursive = TRUE, showWarnings = FALSE)
  dir.create(MODELS_DIR, recursive = TRUE, showWarnings = FALSE)
  dir.create(PLOTS_DIR, recursive = TRUE, showWarnings = FALSE)
  dir.create(REPORTS_DIR, recursive = TRUE, showWarnings = FALSE)
}
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
