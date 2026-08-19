# 2026-07 ロジック見直しメモ（R 自動生成）

生成元: `r_analysis/scripts/10_july2026_review.R`

## 1. 7月バックテスト要約

- レース数: 179
- 単勝ROI: 87.9% (bets=117, hit=51.3%)
- 三連複ROI: 71.7% (bets=157, hit=41.4%)
- 三連単ROI: 101.3%
- ワイドROI: 82.5%
- 堅シェア 単勝プロフ: 65.4% / 三連プロフ: 67.0%

## 2. 改善仮説（データ確認用チェックリスト）

1. **校正ギャップ**: `july_calibration_bins.csv` で mean_pred >> actual なら自信度閾値を上げる候補
2. **堅/荒のROI差**: `july_segment_exotic_profile.csv` で荒だけ崩れていないか
3. **週次クラッシュ**: `july_weekly_roi.csv` で 7/22 週など特定週だけ悪化していないか
4. **ライブ不安定**: `july_compare_by_snapshot.csv` の ex_prof match が低い → T-10再判定/見送り強化
5. **損失レース**: `july_sanren_loss_drivers.csv` 上位の共通点（クラス・距離・volatile）
6. **複勝見送り**: `skipped_*` 系（09）を 7 月行に絞って機会損失を確認

## 3. 三連系プロフ別

- 堅: sanren ROI 69.5% / hit 45.7% (n=116)
- 荒: sanren ROI 79.4% / hit 29.3% (n=41)

## 4. 校正ギャップが大きいビン

- bin 8: pred=100.0% actual=38.9% gap=61.1pt (n=18)
- bin 3: pred=93.2% actual=33.3% gap=59.9pt (n=18)
- bin 10: pred=100.0% actual=41.2% gap=58.8pt (n=17)

## 5. 当日スナップ vs Final

- t_minus_10: final top3 73.9% / ◎match 75% / ex_prof match 66%
- t_minus_20: final top3 74.0% / ◎match 75% / ex_prof match 64%
- t_minus_30: final top3 74.0% / ◎match 72% / ex_prof match 73%

## 6. 次アクション（本番ロジック変更は検証後）

- まず Python `scripts/backtest_bets.py --from 20260701 --to 20260731` と本レポートを突合
- 閾値を動かすなら `scripts/tune_exotic_thresholds.py` を **7月だけに過学習しない** よう 1-6月 holdout 併用
- T-10 のプロフィール反転時は送信見送り、をコード化する前に `july_compare_by_day.csv` で損失減効果を試算

