source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()
ensure_output_dirs()
if (!file.exists(PAYBACK_CACHE_JSON)) {
  stop("payback_cache.json required. Fetch paybacks before running this script.")
}
message("Jockey x track condition interaction (flat win ROI)...")
df <- load_master_filtered()
message("Rows: ", nrow(df))
save_jockey_track_bias_tables(df)
message("Done. See r_analysis/output/tables/jockey_track_*.csv and output/plots/")
