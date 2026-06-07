# RStudio setup check (does not run analysis)
source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "R", "00_source_all.R"), encoding = "UTF-8")

check_pkg <- function(pkg) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    message("[OK] ", pkg)
    TRUE
  } else {
    message("[NG] ", pkg, " - install.packages('", pkg, "')")
    FALSE
  }
}

message("=== sonoda-keiba R analysis setup ===")
message("PROJECT_ROOT: ", PROJECT_ROOT)
message("MASTER_CSV:   ", MASTER_CSV)

pkgs_ok <- all(vapply(c("tidyverse", "jsonlite"), check_pkg, logical(1)))

if (file.exists(MASTER_CSV)) {
  message("[OK] horses_master.csv")
} else {
  message("[NG] horses_master.csv not found: ", MASTER_CSV)
  pkgs_ok <- FALSE
}

if (file.exists(PAYBACK_CACHE_JSON)) {
  message("[OK] payback_cache.json")
} else {
  message("[WARN] payback_cache.json missing - hit-rate only")
  message("       fetch: .\\.venv\\Scripts\\python.exe scripts/fetch_paybacks.py --from YYYYMMDD --to YYYYMMDD")
}

if (file.exists(BACKTEST_ROWS_CSV)) {
  message("[OK] backtest_rows.csv (segment analysis)")
} else {
  message("[WARN] backtest_rows.csv missing - run export_backtest_for_r.py for (1)")
}

if (pkgs_ok) {
  message("")
  message("Ready. Next:")
  message('  source("r_analysis/scripts/01_run_baseline.R")')
  message('  source("r_analysis/scripts/02_run_models.R")')
  message('  source("r_analysis/scripts/03_roi_baseline.R")')
  message('  source("r_analysis/scripts/04_segment_analysis.R")')
  message('  source("r_analysis/scripts/05_decile_extended.R")')
  message('  source("r_analysis/scripts/06_bet_like_roi.R")')
  message('  source("r_analysis/scripts/run_all.R")')
} else {
  message("")
  message("Install missing packages and re-run.")
}

invisible(pkgs_ok)