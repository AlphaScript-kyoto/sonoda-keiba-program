source(
  file.path(dirname(normalizePath(
    sub("^--file=", "", grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)[1]),
    winslash = "/"
  )), "bootstrap.R"),
  encoding = "UTF-8"
)
bootstrap_r_analysis()

ensure_output_dirs()
message("Loading master for ROI...")
df <- load_master_filtered()
message("Rows: ", nrow(df))
save_roi_tables(df)
message("Done. See r_analysis/output/tables/roi_*.csv")
