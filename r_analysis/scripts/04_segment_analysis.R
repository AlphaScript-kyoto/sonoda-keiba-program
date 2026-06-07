source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()

ensure_output_dirs()
message("Segment analysis (profiles / confidence)...")
save_segment_tables()
message("Done. See r_analysis/output/tables/segment_*.csv")
