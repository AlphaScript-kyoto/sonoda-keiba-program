source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()
scripts_dir <- file.path(PROJECT_ROOT, "r_analysis", "scripts")
source(file.path(scripts_dir, "01_run_baseline.R"), local = FALSE)
source(file.path(scripts_dir, "02_run_models.R"), local = FALSE)
if (file.exists(PAYBACK_CACHE_JSON)) {
  source(file.path(scripts_dir, "03_roi_baseline.R"), local = FALSE)
} else {
  message("Skip ROI: payback_cache.json not found")
}
source(file.path(scripts_dir, "04_segment_analysis.R"), local = FALSE)
source(file.path(scripts_dir, "05_decile_extended.R"), local = FALSE)
if (file.exists(PAYBACK_CACHE_JSON)) {
  source(file.path(scripts_dir, "06_bet_like_roi.R"), local = FALSE)
} else {
  message("Skip bet-like ROI: payback_cache.json not found")
}
source(file.path(scripts_dir, "07_expected_value.R"), local = FALSE)
if (file.exists(PAYBACK_CACHE_JSON)) {
  source(file.path(scripts_dir, "08_jockey_track_bias.R"), local = FALSE)
} else {
  message("Skip jockey x track: payback_cache.json not found")
}
if (file.exists(BACKTEST_ROWS_CSV)) {
  source(file.path(scripts_dir, "09_skipped_races.R"), local = FALSE)
} else {
  message("Skip skipped-race EV: backtest_rows.csv not found")
}
