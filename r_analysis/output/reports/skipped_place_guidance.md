# Skipped-race place relaxation guidance

Generated: 2026-06-19 16:45

## 1. Context

- win_high races analysed: 481
- upset profile, win+place skipped: 86 races
- Current rule: skip_place_on_upset=TRUE in bets.py

## 2. Hypothetical place on upset-skipped races (all)

- Place hit rate: 76.7%
- Win hit rate (reference): 44.2%
- Hypothetical place ROI: 88.8%
- Hypothetical win ROI: 78.1%
- Place profit (100yen x 86R): -960 yen
- Place ROI >= 100%: FALSE

## 3. Scenario comparison

- **current_actual_place**: n=0, ROI=NaN%, profit=0 yen
- **hypothetical_place_all_upset_skipped**: n=86, ROI=88.8%, profit=-960 yen
- **hypothetical_place_high_ev_skipped**: n=85, ROI=88.7%, profit=-960 yen
- **hypothetical_win_all_upset_skipped**: n=86, ROI=78.1%, profit=-1880 yen

## 4. EV bins with place ROI>=100% and n>=30

- **None** — no EV bin meets ROI>=100%, profit>0, n>=30 on upset-skipped races.

## 5. Recommendation (statistical)

1. **Keep skip_place_on_upset=TRUE** — hypothetical place ROI (88.8%) does not beat win alternative or 100% threshold.
2. High model EV on skipped races does not imply profitable place — check skipped_place_ev_bins.csv.
3. Opportunity-loss races (skipped_place_opportunity_loss.csv) are for manual review, not auto-bet.

## 6. Output files
- skipped_place_opportunity_summary.csv
- skipped_place_by_ev_bin.csv
- skipped_place_opportunity_races.csv
- skipped_place_opportunity_loss.csv
- skipped_place_relaxation_scenarios.csv

