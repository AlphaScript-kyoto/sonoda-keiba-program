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
