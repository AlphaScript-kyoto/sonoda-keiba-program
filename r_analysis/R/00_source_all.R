source_project <- function(...) {
  for (part in list(...)) {
    path <- file.path(PROJECT_ROOT, "r_analysis", "R", part)
    source(path, encoding = "UTF-8")
  }
}
source(file.path(PROJECT_ROOT, "r_analysis", "config", "settings.R"), encoding = "UTF-8")
source_project(
  "01_load_master.R",
  "02_clean_targets.R",
  "03_baseline_tables.R",
  "04_winrate_by_bins.R",
  "05_logistic_win.R",
  "06_feature_deciles.R",
  "07_payback_roi.R",
  "08_race_segments.R",
  "09_decile_extended.R",
  "10_bet_like_roi.R",
  "11_expected_value.R",
  "12_jockey_track_bias.R",
  "13_skipped_races.R",
  "14_july2026_review.R"
)
