from pathlib import Path
ROOT = Path(r"c:/Users/akimi/Desktop/programming/sonoda-keiba-program")
s07 = (
    'source("r_analysis/config/settings.R", encoding = "UTF-8")\n'
    'source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")\n'
    "bootstrap_r_analysis()\n"
    "ensure_output_dirs()\n"
    'message("Expected value analysis...")\n'
    "df <- load_master_filtered()\n"
    'message("Rows: ", nrow(df))\n'
    "save_expected_value_tables(df)\n"
    'message("Done. See r_analysis/output/tables/ev_*.csv and output/reports/ev_confidence_guidance.md")\n'
)
s09 = (
    'source("r_analysis/config/settings.R", encoding = "UTF-8")\n'
    'source(file.path(PROJECT_ROOT, "r_analysis", "scripts", "bootstrap.R"), encoding = "UTF-8")\n'
    "bootstrap_r_analysis()\n"
    "ensure_output_dirs()\n"
    'message("Skipped-race EV review...")\n'
    "save_skipped_races_tables()\n"
    'message("Done. See r_analysis/output/tables/skipped_*.csv and output/reports/skipped_place_guidance.md")\n'
)
for rel, text in [("r_analysis/scripts/07_expected_value.R", s07), ("r_analysis/scripts/09_skipped_races.R", s09)]:
    p = ROOT / rel
    p.write_text(text, encoding="utf-8", newline="\n")
    print(rel, p.read_bytes().count(b"\x00"))
