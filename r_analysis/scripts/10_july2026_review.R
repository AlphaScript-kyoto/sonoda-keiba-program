# 2026年7月 振り返り（RStudio / Rscript どちらも可）
# 前提: r_analysis/input/backtest_rows.csv に 7 月行があること

source("r_analysis/config/settings.R", encoding = "UTF-8")
source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")
bootstrap_r_analysis()
ensure_output_dirs()
message("July 2026 logic review...")
save_july2026_review_tables()
message("Done. Open r_analysis/output/reports/july2026_logic_guidance.md")
