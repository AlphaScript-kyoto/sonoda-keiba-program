# EV decile analysis — confidence threshold guidance

Generated: 2026-06-15 13:17
Analysis period: master from 20240101

## 1. Summary (logistic model, flat win 100yen/bet)

- Total bets: 27923
- Overall ROI: 65.9%
- Weighted hit rate: 9.16%
- Weighted model EV: 0.661
- Weighted empirical EV: 0.773
- Mean calibration gap (pred - hit): 0

## 2. Stable profitable deciles (ROI>=100%, profit>0, n>=100)

- **Probability decile: none** — no decile meets all three criteria.
- **Model-EV decile: none** — no decile meets all three criteria.

## 3. High-probability deciles (top 3 deciles)

- ROI range: 72.6% - 81.4%
- Model EV>1 deciles in top-3: 2/3
- Empirical EV>1 deciles in top-3: 0/3
- Avg calibration gap (top-3): 0.0024

## 4. Mapping to production confidence (bets.py)

Current win_high thresholds (DEFAULT_WIN_THRESHOLDS):
- win_prob >= 85%
- prob_gap >= 60%
- mode = and (both required)

Statistical suggestions:
1. **Do not loosen** win_prob / prob_gap based on logistic EV deciles — no stable profitable band exists under flat-win criteria.
2. Model EV exceeds empirical EV in upper deciles (optimism). Prefer **tighter** calibration or higher effective threshold before adding win bets.
3. Top deciles still show ROI 76% on average — below 100%. Confidence 'high' is a **filter for exotic bets**, not proof of +EV win flat betting.

## 5. Production model (backtest_rows, win_high races)

- win_prob deciles analysed: 10 (n_bets per decile ~40)
- Stable profitable win decile: **none** on hypothetical mark win bets.
- Top-3 decile hypothetical win ROI: 83.7%
- Top-3 decile hypothetical place ROI: 93.8%
- Top-3 decile actual win ROI (current skip rules): 83%

Production note: win_high already enforces win_prob>=85% and gap>=60%. Decile splits within win_high show where skip rules help or hurt - see skipped_place_guidance.md.

## 6. Output files
- ev_by_prob_decile.csv
- ev_by_model_ev_decile.csv
- ev_stable_profitable_deciles.csv
- ev_production_win_prob_decile.csv (if backtest export exists)

