# 園田競馬 R 分析（RStudio 向け）

## 1. 開き方

`sonoda-keiba-program.Rproj` をダブルクリック

## 2. セットアップ

```r
install.packages(c("tidyverse", "jsonlite"))
source("r_analysis/scripts/00_setup.R")
```

**Windows 注意:** `.R` ファイルは **UTF-8** 必須。Cursor の Write で UTF-16 化すると `オブジェクト 'l' がありません` 等の謎エラーになる。直す場合:

```powershell
.\.venv\Scripts\python.exe tests\gen_r_analysis_utf8.py
```

## 3. Python エクスポート（セグメント分析の前に推奨）

```powershell
.\.venv\Scripts\python.exe scripts/export_backtest_for_r.py --from 20260101 --to 20260531
```

出力: `r_analysis/input/backtest_rows.csv`（1レース1行・自信度/堅荒/券種別投資払戻）

## 4. 分析の実行順

```r
source("r_analysis/scripts/01_run_baseline.R")   # 的中率ベースライン
source("r_analysis/scripts/02_run_models.R")      # ロジスティック
source("r_analysis/scripts/03_roi_baseline.R")    # フラット単勝ROI
source("r_analysis/scripts/04_segment_analysis.R") # (1) 堅荒・自信度・券種別
source("r_analysis/scripts/05_decile_extended.R")  # (2) 重みJSON未検証特徴量デシル
source("r_analysis/scripts/06_bet_like_roi.R")     # (3) 実馬券に近いROI
source("r_analysis/scripts/07_expected_value.R")   # (4) 期待値デシル
source("r_analysis/scripts/08_jockey_track_bias.R") # (5) 騎手×馬場
source("r_analysis/scripts/09_skipped_races.R")    # (6) 見送り最適化
source("r_analysis/scripts/10_july2026_review.R")  # (7) 2026/7 振り返り
source("r_analysis/scripts/run_all.R")              # 一括
```

### 2026年7月だけ振り返るとき

コピペ全文: **`r_analysis/scripts/JULY2026_COMMANDS.txt`**

```powershell
.\.venv\Scripts\python.exe scripts\analyze_july2026.py
.\.venv\Scripts\python.exe scripts\export_backtest_for_r.py --from 20260101 --to 20260731
```

```r
source("r_analysis/scripts/10_july2026_review.R", encoding = "UTF-8")
```

出力の起点: `r_analysis/output/reports/july2026_logic_guidance.md`

## 5. 主な出力

### (1) セグメント `segment_*.csv`
- `segment_by_win_profile.csv` / `segment_by_exotic_profile.csv`
- `segment_by_confidence.csv` / `segment_by_profile_confidence.csv`
- `segment_sanrenpuku_by_profile.csv`

### (2) デシル拡張 `decile_winrate_*.csv` + `decile_gap_summary.csv`
重みJSONで使っているが旧デシルに無かった特徴量（`style_track_win_rate` 等）

### (3) 実馬券風ROI `roi_bet_like_*.csv`
- `roi_bet_like_overall.csv`（1番人気単勝、堅◎単勝、人気1-3三連複BOX 等）
- `roi_bet_like_by_win_profile.csv`
- `roi_backtest_export_summary.csv`（エクスポートCSVがある場合）

### (4) 期待値デシル `ev_*.csv` + `output/plots/ev_*.png` + `output/reports/`
- `ev_by_prob_decile.csv` … 予測確率デシル（ROI / profit / 校正ギャップ付き）
- `ev_by_model_ev_decile.csv` … model EV デシル
- `ev_stable_profitable_deciles.csv` … **ROI>=100% & profit>0 & n>=100** を満たす安定利益デシル
- `ev_production_win_prob_decile.csv` … 本番モデル（backtest_rows）の win_prob デシル
- `output/reports/ev_confidence_guidance.md` … 自信度閾値の統計的示唆
- `07_expected_value.R`

### (5) 騎手×馬場 `jockey_track_*.csv`
- `jockey_track_roi.csv` … 騎手×馬場状態（良/稍/重/不良）のフラット単勝ROI
- `jockey_track_hot_combos.csv` … 全体ROI比で跳ねる組み合わせ
- `08_jockey_track_bias.R`（旧案の `05_jockey_track_bias.R` 相当）

### (6) 見送り再分析 `skipped_*.csv` + `output/reports/`
- `skipped_vs_played_summary.csv` … 見送り vs 購入（単勝・複勝の仮想ROI含む）
- `skipped_high_ev_races.csv` … EV>=1 なのに見送ったレース
- `skipped_missed_wins.csv` … 見送ったが◎が勝ったレース
- `skipped_place_opportunity_summary.csv` … 荒れ見送りレースの**複勝**仮想ROI
- `skipped_place_by_ev_bin.csv` … EV帯別の複勝仮想ROI（緩和候補帯）
- `skipped_place_opportunity_races.csv` / `skipped_place_opportunity_loss.csv` … 機会損失レース一覧
- `skipped_place_relaxation_scenarios.csv` … 「複勝だけ拾う」シナリオ比較
- `output/reports/skipped_place_guidance.md` … 複勝見送り緩和の統計的示唆
- `09_skipped_races.R`

**前提:** `export_backtest_for_r.py` で `place_payout_yen` / `hypothetical_place_return_yen` 列が必要（再エクスポート推奨）

## 6. 改善の進め方

1. `ev_stable_profitable_deciles.csv` / `ev_confidence_guidance.md` で自信度閾値の補正方針を確認
2. `skipped_place_guidance.md` / `skipped_place_relaxation_scenarios.csv` で複勝見送り緩和を検証
3. `decile_gap_summary.csv` / `ev_by_prob_decile.csv` で効く特徴量・EV帯を確認
4. `segment_*.csv` / `skipped_*.csv` で堅荒・見送りの弱点を確認
5. `roi_bet_like_*.csv` で見送り/BOXの仮説を確認
6. Python `config/tuned_weights_*.json` / `bets.py` へ手動反映
7. `scripts/backtest_bets.py` で検証