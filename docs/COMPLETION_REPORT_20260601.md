# 会社PC作業 完了報告（2026-06-01）

GitHub: https://github.com/AlphaScript-kyoto/sonoda-keiba-program
Commit: ca8a241（当時の main。リポジトリ移転後の履歴とは別）

## 完了
- 脚質キャッシュ 3756件
- tuned_weights_sanrenpuku.json
- 複勝荒見送り / クラス距離堅荒 / sanrenpuku objective
- PROJECT_STATUS.md 更新

## 結果（2026年5月）
- style三連複 85.7% vs sanrenpuku 61.4% (sanrenpuku未採用)
- 新ロジック: 単勝95.9% 複勝91.8% 三連複66.5% 三連単125.3% ワイド71.1%
- モデル比較: 脚質のみ最良（三連複85.7% 三連単140.4%）

## 次
1. build_features.py
2. backtest 2026/1-5
3. style vs sanrenpuku A/B
4. 期間分割 + 2025 holdout

詳細: docs/PROJECT_STATUS.md
