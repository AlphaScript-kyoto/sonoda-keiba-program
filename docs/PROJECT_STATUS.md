# プロジェクト現状メモ（2026-06 時点）

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

### クラス・距離（detect_win_profile / detect_exotic_profile 共通）

- 下位クラス（C1/C2/C3/B2）かつ upset_score >= 2 → 荒
- 1700m 以上かつ upset_score >= 2 → 荒

### 複勝

- **荒レース（win_profile == 荒）は複勝◎も見送り**（`skip_place_on_upset=True`）

---

## 3. スコアリング重み

| ファイル | 説明 |
|---------|------|
| **config/tuned_weights.json** | **デフォルト（style 重み）— 採用中** |
| config/tuned_weights_sanrenpuku.json | 三連複ROI目的チューニング（2026-06。**未採用・要検証**） |
| config/tuned_weights_style.json | style のバックアップ |
| config/tuned_weights_walkforward.json | walkforward 版 |
| config/tuned_weights_domain.json | 脚質+園田ドメイン（比較用） |

### 三連複ROIチューニング結果（参考・5月のみ）

`scripts/tune_weights.py --objective sanrenpuku --reference-date 20260430`

| 重み | 5月 三連複回収率 | 備考 |
|------|-----------------|------|
| style（現行） | **85.7%** | compare_models.log（脚質のみ） |
| sanrenpuku 新重み | **61.4%** | 5月で再選定したが style より劣る |

→ **5月だけ見て採用しないこと。** 下記「次にやること」で 1〜5月通しを評価する。

---

## 4. バックテスト参考値

### 旧ロジック（§4 以前・複勝見送りなし等）

| 期間 | 単勝(堅のみ) | 三連複 | 三連単 | ワイド |
|------|-------------|--------|--------|--------|
| 2026/3-5 | 55.9% / 92.3% | 45.0% / 87.3% | 10.9% / 79.8% | 69.2% / 84.0% |
| 2026/1-5 | 54.3% / 89.5% | 42.9% / 72.6% | 9.8% / 66.0% | 69.9% / 68.8% |
| 2025 通年 | 48.0% / 83.4% | 40.0% / 74.8% | 8.9% / 70.9% | 64.9% / 76.2% |

### 新ロジック（複勝・単勝荒見送り + クラス/距離堅荒）— 2026/5 のみ

`backtest_place_skip.log`（style 重み・現行デフォルト）

| 券種 | 回収率 |
|------|--------|
| 単勝◎(堅のみ) | 95.9%（114R） |
| 複勝◎ | 91.8%（114R） |
| 三連複 | 66.5%（124R） |
| 三連単 | 125.3%（109R） |
| ワイド | 71.1%（124R） |

※ 旧 §4 表とは馬券ロジックが異なるため直接比較不可。

```powershell
python scripts/backtest_bets.py --from 20260101 --to 20260531
```

payback キャッシュが無い場合は `--fetch-payback`（数時間かかる）。

---

## 5. データファイル（GitHub に無い → iCloud 等で持ち出し）

| 優先度 | パス | 用途 |
|--------|------|------|
| **必須** | data/processed/horses_master.csv | 予想・評価の本体 |
| **必須** | data/processed/payback_cache.json | バックテスト払戻 |
| 推奨 | data/raw/*.csv | 特徴量再生成 |
| **Git あり** | data/processed/race_style_cache.json | 脚質キャッシュ（**3756件完了 2026-06**） |
| 任意 | data/processed/race_lap_cache.json | ラップ（取得可能 263件のみ。2026/04 以降の園田） |

---

## 6. 主要スクリプト

| コマンド | 用途 |
|---------|------|
| python scripts/fetch_races.py --date YYYYMMDD --save | レース取得 |
| python scripts/build_features.py | 特徴量 → master 更新 |
| python scripts/predict.py --date YYYYMMDD | 予想 + 馬券案 |
| python scripts/backtest_bets.py --from ... --to ... | 馬券バックテスト |
| python scripts/tune_weights.py --objective sanrenpuku | 三連複ROI向け重み探索 |
| python scripts/compare_models.py --skip-tune | 3モデル比較（保存済み重み） |
| python scripts/walkforward_tune.py | ウォークフォワード再チューニング |
| python scripts/backfill_race_meta.py | 脚質・ラップキャッシュ |

---

## 7. 分析メモ（堅 vs 荒）

- 印外勝ち: 堅 10.3% → 荒 12.5%
- 有効: 1番人気>=3.0, head>=12, gap<=0.65, odds_std>=88, 下位クラス, 1700m+
- 無効: top3_prob_sum, odds_spread

---

## 8. 次にやること（優先順）

### 必須（次セッション最初）

1. **脚質を master に反映**
   ```powershell
   .\.venv\Scripts\python.exe scripts/build_features.py
   ```
   脚質キャッシュは 3756 件揃ったが、`horses_master.csv` への反映は未実行の可能性大。

2. **2026/1〜5 バックテスト（初見評価）**
   - 5月だけのチューニング結果に過学習しないため、**通期で判断**
   ```powershell
   .\.venv\Scripts\python.exe scripts/backtest_bets.py --from 20260101 --to 20260531
   ```

3. **style vs sanrenpuku 重みの A/B 比較**
   - 現行: `config/tuned_weights.json`（style）
   - 新: `config/tuned_weights_sanrenpuku.json`（ScoringConfig.load または `--weights` 相当で切替要確認）
   - 5月 sanrenpuku は 61.4% と style 85.7% より劣る → **1〜5月通しで再確認してから採用判断**

### 推奨（過学習チェック）

4. **期間分割バックテスト**
   ```powershell
   .\.venv\Scripts\python.exe scripts/backtest_bets.py --from 20260101 --to 20260331
   .\.venv\Scripts\python.exe scripts/backtest_bets.py --from 20260401 --to 20260531
   ```
   5月だけ突出していないか確認。

5. **2025 通年（真の holdout）**
   ```powershell
   .\.venv\Scripts\python.exe scripts/backtest_bets.py --from 20250101 --to 20251231
   ```

### 採用判断後

6. sanrenpuku 重みを採用するなら `tuned_weights.json` を上書き。採用しないなら現行 style のまま。
7. `docs/PROJECT_STATUS.md` §4 に新ロジックの 1〜5月数値を追記。
8. 次の開催予想: `python scripts/predict.py --date YYYYMMDD`

### 注意

- venv 有効化が PowerShell ポリシーで失敗する PC では `.\.venv\Scripts\python.exe` 直叩き
- 脚質バックフィル中に JSON を読むと一時的に壊れて見える → 完了後は 3756 件で正常
- `payback_cache.json` は .gitignore。GitHub clone だけではバックテスト不可

---

## 9. 直近の変更履歴

1. 堅/荒分岐 + 荒れ三連複 BOX（4+穴2）
2. 荒れ単勝見送り
3. win_profile / exotic_profile 分離
4. walkforward 再チューニング → style 重みをデフォルトに復帰
5. 複勝荒見送り + クラス/距離堅荒 + `--objective sanrenpuku` 追加
6. 脚質キャッシュ 3756 件バックフィル完了（2026-06 会社 PC）
7. `config/tuned_weights_sanrenpuku.json` 生成（採用は未決）

*大きな方針変更があったらこのファイルを更新すること。*
