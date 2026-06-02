# プロジェクト現状メモ（2026-06 時点）

出先 PC や新しい Cursor セッション向け。**会話履歴が無くてもここを読めば続きが分かる**。

**リポジトリ / フォルダ名:** `sonoda-keiba-program`（旧: 園田特化予想プログラム）

| 環境 | パス例 |
|------|--------|
| オリジナル PC | `C:\Users\1180075\Desktop\プログラミング\sonoda-keiba-program` |
| 自宅 PC（2026-06） | `C:\Users\akimi\Desktop\プログラミング\sonoda-keiba-program` |
| その他 | `git clone` 後 `cd sonoda-keiba-program` |

**直近の目標:** **2026/6/3（火）園田** の当日予想を UI から実行できるようにする。

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

- 自信度: exotic_firm（勝率85% & gap70%）
- 三連複: ◎1軸流し6点
- 三連単: ◎→○▲→△☆ 4点
- ワイド: ◎-○▲（2点）。is_volatile_race なら ◎-○▲△（3点）

**荒（BOX、三連単なし）**

- 自信度: exotic_upset（勝率82% & gap50%）
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

### スコアリングの二重化（split scoring・**採用中**）

単勝系と三連系で**別重み**を使う（`BetStrategyConfig.split_scoring=True` 既定）。

| 用途 | 重みファイル | 関数 |
|------|-------------|------|
| 単勝・複勝・自信度（win） | `config/tuned_weights_style.json` | `predict_date` → win race |
| 印・三連複/単・ワイド | `config/tuned_weights_sanrenpuku.json` | `predict_date` → exotic race |

実装: `scoring_config.load_split_scoring_configs()` / `build_race_bet_plan(..., exotic_race=)` / `backtest_period` が自動で二重予想。

---

## 3. スコアリング重み

| ファイル | 説明 |
|---------|------|
| **config/tuned_weights.json** | デフォルト（style 重みのコピー） |
| **config/tuned_weights_style.json** | **単勝系（split 採用中）** |
| **config/tuned_weights_sanrenpuku.json** | **三連系（split 採用中）** |
| config/tuned_weights_walkforward.json | walkforward 版 |
| config/tuned_weights_domain.json | 脚質+園田ドメイン（比較用） |

### style vs sanrenpuku A/B（同一馬券ロジック・単一重みのみ）

| 期間 | style 三連複 | sanrenpuku 三連複 |
|------|-------------|-------------------|
| 2025 通年 | 60.1% | **76.8%** |
| 2026/1-5 | 57.7% | **62.1%** |
| 2026/1-3 | 21.5% | **32.2%** |
| 2026/4-5 | 80.1% | 80.0% |

→ holdout（2025）では sanrenpuku が明確に優位。**split 採用**（単勝=style / 三連=sanrenpuku）で両方の強みを使う。

---

## 4. バックテスト参考値

### split scoring（style 単勝 + sanrenpuku 三連系）— **現行**

複勝荒見送り + クラス/距離堅荒。`split_scoring=True` 既定。

| 期間 | R数 | 単勝(堅) | 複勝 | 三連複 | 三連単 | ワイド |
|------|-----|---------|------|--------|--------|--------|
| 2026/1-5 | 491 | **87.5%** | 79.5% | **73.4%** | 82.5% | 86.6% |
| 2026/1-3 | 168 | 83.4% | 99.2% | **61.7%** | 55.1% | 91.9% |
| 2026/4-5 | 323 | **89.5%** | 94.0% | **80.2%** | 118.5% | 83.6% |
| 2025 通年 | 1663 | 82.8% | 90.9% | **76.8%** | 70.5% | 86.1% |

- 2026/1-5 の三連複は style 単体（57.7%）より **+4.4pt** 改善
- 2025 holdout 三連複 **76.8%** — 2026 通期（62.1%）より高く、2026 は未確定サンプル
- **Q1 2026**: 1-3月 三連複 **61.7%**（168R）。1月 payback 未取得が主因だった（取得後 58.9%→61.7%）。**2月は園田開催なし**（master 0R）
- 三連系閾値（Q1 チューニング・4-5月 validate 維持）: `exotic_firm` gap **0.70** / `exotic_upset` 勝率 **0.82** gap **0.50**（`config/exotic_thresholds.json`）

```powershell
python scripts/backtest_bets.py --from 20260101 --to 20260531
python scripts/analyze_q1_collapse.py   # Q1 要因分析
```

### 旧ロジック（参考・split 前・単一 style 重み）

| 期間 | 単勝(堅) | 三連複 |
|------|---------|--------|
| 2026/1-5 | 87.5% | 57.7% |
| 2026/1-3 | 83.4% | 21.5% |
| 2026/4-5 | 89.5% | 80.1% |
| 2025 通年 | 82.8% | 60.1% |

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
| python scripts/fetch_paybacks.py --from ... --to ... | 払戻キャッシュ拡充 |
| python scripts/analyze_q1_collapse.py | 2026 Q1 三連複崩れ分析 |
| python scripts/tune_exotic_thresholds.py [--apply] | 三連系自信度閾値探索 |
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

### 完了済み（2026-06 自宅 PC）

- style vs sanrenpuku A/B → split scoring 採用
- 2026/1-5・期間分割・2025 通年バックテスト（split + 新三連系閾値）
- Q1 崩れ分析・1月 payback 84R 取得（`scripts/fetch_paybacks.py`）
- 三連系閾値 Q1 チューニング → `bets.py` + `config/exotic_thresholds.json`
- **5月末まで master にデータあり**（ユーザー確認済み 2026-06-02）

### 最優先（会社 PC・次セッション）— **当日予想 UI**

**現状:** UI なし。CLI の `scripts/predict.py` のみ。Web/Streamlit 等は未導入（`requirements.txt` に streamlit 等なし）。

**ゴール（6/3 前）:** ブラウザ or デスクトップから「日付指定 → 予想取得 → レース一覧＋馬券案」を見られること。

詳細仕様 → **§10 当日予想 UI** を実装の設計書として使うこと。

**会社 PC 着手前チェックリスト**

1. `git pull`（コード最新化）
2. iCloud 等から `data/processed/horses_master.csv` を同期（5月末まで入っていること再確認）
3. `pip install -r requirements.txt`（UI 追加時は streamlit 等を追記）
4. 動作確認（CLI）:
   ```powershell
   python scripts/predict.py --date 20260603
   ```
   出馬表未公開なら「予想対象がありません」と出るのは正常。公開後に再実行。
5. オフライン検証（通信なし）:
   ```powershell
   python scripts/predict.py --date 20260529 --offline
   ```

### 任意（時間があれば）

- `build_features.py` — 脚質キャッシュ 3756 件を master に未反映なら実行
- 6/3 終了後: `fetch_races.py --date 20260603 --save` → `build_features.py` で master 更新

### 注意

- venv 有効化が PowerShell ポリシーで失敗する PC では `.\.venv\Scripts\python.exe` 直叩き
- `payback_cache.json` は .gitignore。UI の当日予想には**不要**（出馬表取得のみ）
- 当日 `--retune` は使わない（遅い・過学習リスク）
- netkeiba 通信制限: 1 リクエスト 7〜10 秒。12R で約 2 分。UI には進捗表示必須

---

## 9. 直近の変更履歴

1. 堅/荒分岐 + 荒れ三連複 BOX（4+穴2）
2. 荒れ単勝見送り
3. win_profile / exotic_profile 分離
4. walkforward 再チューニング → style 重みをデフォルトに復帰
5. 複勝荒見送り + クラス/距離堅荒 + `--objective sanrenpuku` 追加
6. 脚質キャッシュ 3756 件バックフィル完了（2026-06 会社 PC）
7. style vs sanrenpuku A/B → **split scoring 採用**（style 単勝 / sanrenpuku 三連系）
8. `scripts/analyze_q1_collapse.py` 追加、2026 Q1 崩れ分析
9. 1月 payback 84R 取得 + 三連系閾値 Q1 チューニング（`exotic_thresholds.json`）
10. 自宅 PC: 5月末 master 確認済み。**次: 6/3 向け当日予想 UI**（§10）

---

## 10. 当日予想 UI — 設計・引き継ぎ（会社 PC 用）

**作成:** 2026-06-02（自宅 PC）  
**目的:** 2026/6/3 園田開催を UI から予想・馬券確認できるようにする。

### 10.1 現状のアーキテクチャ（CLI）

```
predict.py
  ├─ load_master()
  ├─ load_split_scoring_configs()  → style + sanrenpuku
  ├─ predict_date(date, fetch_entries=True)   # netkeiba 出馬表
  ├─ predict_date(date, config=ex_cfg, fetch_entries=False)  # 三連系用（同一 entries を再スコア）
  └─ build_day_bet_plans(win_df, exotic_scored=ex_df) → List[RaceBetPlan]
```

| モジュール | 役割 |
|-----------|------|
| `src/predictor/score.py` | `predict_date`, `score_entries` — 出馬表→特徴量→勝率 |
| `src/predictor/bets.py` | `build_day_bet_plans`, `RaceBetPlan` — 印・馬券案 |
| `src/predictor/scoring_config.py` | split 重みパス |
| `src/scraper/shutuba.py` | 出馬表 HTML 取得・パース |
| `scripts/predict.py` | 上記を繋ぐ CLI（`_print_predictions` が表示ロジック） |

**UI 化の方針:** ロジックは `src/` に残し、UI は薄いラッパーにする。`predict.py` の `main()` をコピーせず、共通化関数を切り出す。

### 10.2 推奨スタック

| 案 | メリット | 備考 |
|----|---------|------|
| **Streamlit**（推奨） | Python のみ・実装が早い・表表示が楽 | `pip install streamlit` を requirements に追加 |
| FastAPI + 静的 HTML | 将来モバイル対応しやすい | 6/3 までの工数は増 |
| CLI 強化のみ | 追加依存なし | ユーザー要望は「UI」 |

**推奨:** `app/streamlit_app.py` または `scripts/predict_ui.py`（Streamlit 1 ファイル MVP）。

### 10.3 MVP 画面要件（6/3 最低限）

1. **日付入力** — デフォルト今日（`20260603`）。カレンダー or テキスト `YYYYMMDD`
2. **「予想取得」ボタン** — `fetch_entries=True` で netkeiba 取得
3. **進捗表示** — 「3/12R 取得中…」（`predict_date` 内ループをコールバック化するか、UI 側で race_ids を先に list して 1R ずつ取得）
4. **レース一覧** — R 番・レース名・距離
5. **レース詳細（折りたたみ or タブ）**
   - 印 ◎○▲△☆ + 馬名 + 勝率 + オッズ（上位5頭）
   - バッジ: 単勝自信度 / 三連自信度 / 単勝プロファイル（堅・荒）/ 三連プロファイル
   - 1番人気オッズ、1位勝率、1-2位差
   - 馬券案（自信度「高」の三連系のみ）: 三連複流し or BOX、三連単、ワイドの label 文字列
   - 単勝・複勝「見送り」時は理由表示（`confidence` に「荒れ・単勝見送り」等）
6. **フィルタ** — 「三連系 自信度「高」のみ」「単勝見送り除く」
7. **エラー** — `NetkeibaBlockedError` → 「通信制限。しばらく待って再試行」

**オフライン開発用:** `--offline` 相当のトグル（master 上の過去日で UI テスト）。fixture 日: `20260529`。

### 10.4 実装ステップ（会社 PC でこの順）

| Step | 内容 | 成果物 |
|------|------|--------|
| 1 | `src/predictor/predict_day.py`（新規）に `run_predict_day(date, *, offline=False) -> PredictDayResult` を切り出し。dataclass で `win_df`, `exotic_df`, `plans: List[RaceBetPlan]` を返す | `predict.py` から import してリファクタ |
| 2 | Streamlit MVP: 日付 + ボタン + plans ループ表示 | `app/predict_app.py` |
| 3 | 進捗バー（race_ids ループを predict_day 側で generator/callback 対応） | UX 改善 |
| 4 | スタイル（堅/荒で色分け、三連「買い」レースを上部にピン） | 任意 |
| 5 | `requirements.txt` に `streamlit` 追加、README / §6 に起動コマンド追記 | `streamlit run app/predict_app.py` |

**起動コマンド（想定）**

```powershell
cd sonoda-keiba-program
.\.venv\Scripts\python.exe -m streamlit run app/predict_app.py
```

### 10.5 `RaceBetPlan` 表示に使うフィールド

```python
# src/predictor/bets.py — RaceBetPlan
race_no, race_name
confidence          # 単勝側「高」「通常（荒れ・単勝見送り）」等
exotic_confidence   # 三連系「高」「通常」
win_profile, exotic_profile  # 「堅」「荒」
fav_odds, win_prob_top, prob_gap
marks               # [(印, 馬番, 馬名), ...]
sanrenpuku, sanrenpuku_box, sanrentan, wide  # .label 文字列で表示
```

### 10.6 6/3 当日オペレーション

| タイミング | 操作 |
|-----------|------|
| 前日〜当日朝 | 出馬表・オッズ未確定なら空。焦らず待つ |
| オッズ確定後 | UI で `20260603` → 予想取得 |
| レース間 | オッズ変動時は再取得可（通信制限に注意） |
| 終了後 | `fetch_races.py --date 20260603 --save` → `build_features.py` |

**CLI フォールバック（UI 未完成時）**

```powershell
python scripts/predict.py --date 20260603
```

### 10.7 触らないもの（6/3 前）

- 馬券ロジック本体（`bets.py`）の大変更
- `--retune` / walkforward の当日実行
- sanrenpuku 重みの再チューニング（split 構成は固定）

### 10.8 参考ファイル

- 出馬表 HTML サンプル: `tests/fixtures/shutuba_202650052901.html`（6/3 が「次開催」リンク）
- 表示ロジック参考: `scripts/predict.py` の `_print_predictions`
- Agent 共通: ルート `AGENTS.md`

*UI 実装が進んだら §6 スクリプト表と §9 履歴を更新すること。*

*大きな方針変更があったらこのファイルを更新すること。*
