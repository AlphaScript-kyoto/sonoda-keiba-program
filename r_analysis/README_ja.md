# 園田競馬 R 分析（RStudio 向け）

## 1. 開き方

`sonoda-keiba-program.Rproj` をダブルクリック

## 2. セットアップ

```r
install.packages(c("tidyverse", "jsonlite"))
source("r_analysis/scripts/00_setup.R")
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
source("r_analysis/scripts/run_all.R")              # 一括
```

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

## 6. 改善の進め方

1. `decile_gap_summary.csv` で効く特徴量を確認
2. `segment_*.csv` で堅荒・自信度別の弱点を確認
3. `roi_bet_like_*.csv` で見送り/BOXの仮説を確認
4. Python `config/tuned_weights_*.json` / `bets.py` へ手動反映
5. `scripts/backtest_bets.py` で検証