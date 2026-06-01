# プロジェクト現状メモ（2026-05 時点）

出先 PC や新しい Cursor セッション向け。**会話履歴が無くてもここを読めば続きが分かる**。

**リポジトリ / フォルダ名:** `sonoda-keiba-program`（旧: 園田特化予想プログラム）

| 環境 | パス例 |
|------|--------|
| オリジナル PC | `C:\Users\1180075\Desktop\プログラミング\sonoda-keiba-program` |
| その他 | `git clone` 後 `cd sonoda-keiba-program` |

---

## 1. プロジェクト概要

| 項目 | 内容 |
|------|------|
| 対象 | 園田競馬（netkeiba 地方 / jyo_cd=50） |
| パイプライン | raw CSV → build_features.py → horses_master.csv → スコアリング → predict.py / 馬券案 |
| モデル | **style モデル**（脚質系特徴量中心）。ドメイン特徴量は JSON にあるが active_features では未使用 |
| 馬券 | 自信度「高」のレースのみ。堅/荒で買い方を分岐 |

---

## 2. 現在の馬券戦略（重要）

実装: `src/predictor/bets.py` / バックテスト: `src/predictor/backtest.py`

### 単勝 vs 三連系の思考ロジックは分離済み

| 概念 | 関数 | 用途 |
|------|------|------|
| **単勝プロファイル** | detect_win_profile() | 厳しめ。荒 → 単勝見送り |
| **三連系プロファイル** | detect_exotic_profile() | 流し ↔ BOX の切替 |
| **ボラティリティ** | is_volatile_race() | 堅い三連系でもワイド拡張・穴馬選定 |

### 単勝（win_profile == 荒 で見送り）

- 1番人気オッズ >= 3.0
- または upset_score >= 4 かつ 1番人気 >= 2.5 かつ gap <= 0.65
- skip_win_on_upset=True（デフォルト）

### 三連系（exotic_profile）

**堅（流し + 三連単 + ワイド）**

- 自信度: exotic_firm（勝率85% & gap75%）
- 三連複: ◎1軸流し6点
- 三連単: ◎→○▲→△☆ 4点
- ワイド: ◎-○▲（2点）。is_volatile_race なら ◎-○▲△（3点）

**荒（BOX、三連単なし）**

- 自信度: exotic_upset（勝率80% & gap55%）
- 三連複: **上位4頭 + 穴2 = 20点 BOX**
- ワイド: ◎-○▲△（3点）
- 穴馬: オッズ穴 + モデル中位を混在（_pick_exotic_longshots）

### upset_score（compute_upset_score）

- 1番人気 >= 3.0 → +2
- gap <= 0.65 → +1
- 12頭以上 → +1
- 1位勝率 < 0.88 → +1
- odds_std >= 88 → +1

---

## 3. スコアリング重み

| ファイル | 説明 |
|---------|------|
| **config/tuned_weights.json** | **デフォルト（style 重み）** |
| config/tuned_weights_style.json | style のバックアップ |
| config/tuned_weights_walkforward.json | walkforward 版（2026 三連複 ROI は style より劣る） |
| config/tuned_weights_domain.json | 脚質+園田ドメイン（比較用） |

---

## 4. バックテスト参考値（style 重み + 現行馬券戦略）

| 期間 | 単勝(堅のみ) | 三連複 | 三連単 | ワイド |
|------|-------------|--------|--------|--------|
| 2026/3-5 | 55.9% / 92.3% | 45.0% / 87.3% | 10.9% / 79.8% | 69.2% / 84.0% |
| 2026/1-5 | 54.3% / 89.5% | 42.9% / 72.6% | 9.8% / 66.0% | 69.9% / 68.8% |
| 2025 通年 | 48.0% / 83.4% | 40.0% / 74.8% | 8.9% / 70.9% | 64.9% / 76.2% |

```powershell
python scripts/backtest_bets.py --from 20260301 --to 20260531
```

payback キャッシュが無い場合は `--fetch-payback`（数時間かかる）。

---

## 5. データファイル（GitHub に無い → iCloud 等で持ち出し）

| 優先度 | パス | 用途 |
|--------|------|------|
| **必須** | data/processed/horses_master.csv | 予想・評価の本体 |
| **必須** | data/processed/payback_cache.json | バックテスト払戻 |
| 推奨 | data/raw/*.csv | 特徴量再生成 |
| 推奨 | data/processed/race_style_cache.json | 脚質キャッシュ |
| 任意 | data/processed/race_lap_cache.json | ラップ（未完成 ~263/2154） |

---

## 6. 主要スクリプト

| コマンド | 用途 |
|---------|------|
| python scripts/fetch_races.py --date YYYYMMDD --save | レース取得 |
| python scripts/build_features.py | 特徴量 → master 更新 |
| python scripts/predict.py --date YYYYMMDD | 予想 + 馬券案 |
| python scripts/backtest_bets.py --from ... --to ... | 馬券バックテスト |
| python scripts/tune_weights.py | 重みチューニング |
| python scripts/walkforward_tune.py | ウォークフォワード再チューニング |
| python scripts/analyze_profile_features.py | 堅/荒特徴量比較 |
| python scripts/analyze_upset_races.py | 高配当レース分析 |
| python scripts/backfill_race_meta.py | 脚質・ラップキャッシュ |

---

## 7. 分析メモ（堅 vs 荒）

- 印外勝ち: 堅 10.3% → 荒 12.5%
- 有効: 1番人気>=3.0, head>=12, gap<=0.65, odds_std>=88, 下位クラス
- 無効: top3_prob_sum, odds_spread
- distance 列が master で 0 のまま

---

## 8. 未完了・次の候補

- ラップキャッシュのバックフィル完了
- 三連複 ROI 目的の重みチューニング
- クラス・距離を堅/荒判定に組み込み
- 複勝の荒れ見送り検討
- domain モデル本格比較（lap 完了後）

---

## 9. 直近の変更履歴

1. 堅/荒分岐 + 荒れ三連複 BOX（4+穴2）
2. 荒れ単勝見送り
3. win_profile / exotic_profile 分離
4. walkforward 再チューニング → style 重みをデフォルトに復帰

*大きな方針変更があったらこのファイルを更新すること。*