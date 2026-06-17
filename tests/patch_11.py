from pathlib import Path
path = Path(r"c:/Users/akimi/Desktop/programming/sonoda-keiba-program/r_analysis/R/11_expected_value.R")
text = path.read_text(encoding="utf-8")
old = """    lines <- c(
      lines,
      "",
      "## 5. Production model (backtest_rows, win_high races)",
      "",
      paste0(
        "- win_prob deciles analysed: ", nrow(production_decile_tbl),
        " (n_bets per decile ~", round(mean(production_decile_tbl$n_bets)), ")"
      ),
      if (nrow(prod_stable) == 0L) {
        "- Stable profitable win decile: **none** on hypothetical \u25ce win bets."
      } else {
        paste0(
          "- Stable profitable win decile(s): ",
          paste(prod_stable$decile, collapse = ", "),
          " (win_prob ", round(min(prod_stable$win_prob_min), 2),
          "-", round(max(prod_stable$win_prob_max), 2), ")"
        )
      },
      paste0(
        "- Top-3 decile hypothetical win ROI: ",
        round(mean(prod_high$win_roi_pct), 1), "%"
      ),
      paste0(
        "- Top-3 decile hypothetical place ROI: ",
        round(mean(prod_high$place_roi_pct), 1), "%"
      ),
      paste0(
        "- Top-3 decile actual win ROI (current skip rules): ",
        round(mean(prod_high$actual_win_roi_pct, na.rm = TRUE), 1), "%"
      ),
      "",
      "Production note: win_high already enforces win_prob>=85% and gap>=60%. Decile splits within win_high show where skip rules help or hurt \u2014 see skipped_place_guidance.md."
    )"""
new = """    prod_stable_line <- if (nrow(prod_stable) == 0L) {
      "- Stable profitable win decile: **none** on hypothetical mark win bets."
    } else {
      paste0(
        "- Stable profitable win decile(s): ",
        paste(prod_stable$decile, collapse = ", "),
        " (win_prob ", round(min(prod_stable$win_prob_min), 2),
        "-", round(max(prod_stable$win_prob_max), 2), ")"
      )
    }
    lines <- c(
      lines,
      "",
      "## 5. Production model (backtest_rows, win_high races)",
      "",
      paste0(
        "- win_prob deciles analysed: ", nrow(production_decile_tbl),
        " (n_bets per decile ~", round(mean(production_decile_tbl$n_bets)), ")"
      ),
      prod_stable_line,
      paste0(
        "- Top-3 decile hypothetical win ROI: ",
        round(mean(prod_high$win_roi_pct), 1), "%"
      ),
      paste0(
        "- Top-3 decile hypothetical place ROI: ",
        round(mean(prod_high$place_roi_pct), 1), "%"
      ),
      paste0(
        "- Top-3 decile actual win ROI (current skip rules): ",
        round(mean(prod_high$actual_win_roi_pct, na.rm = TRUE), 1), "%"
      ),
      "",
      "Production note: win_high already enforces win_prob>=85% and gap>=60%. Decile splits within win_high show where skip rules help or hurt - see skipped_place_guidance.md."
    )"""
# file uses actual unicode chars
old = old.replace("\\u25ce", "\u25ce").replace("\\u2014", "\u2014")
if old not in text:
    # try reading actual chars from file slice
    start = text.find("    lines <- c(\n      lines,\n      \"\",\n      \"## 5. Production model")
    print("start", start)
    raise SystemExit("pattern not found")
text = text.replace(old, new)
path.write_text(text, encoding="utf-8", newline="\n")
print("patched 11", path.read_bytes().count(b"\x00"))
