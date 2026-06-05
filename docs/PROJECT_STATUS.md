# プロジェクト現状メモ（2026-06 時点）

出先 PC や新しい Cursor セッション向け。**会話履歴が無くてもここを読めば続きが分かる**。

**リポジトリ / フォルダ名:** `sonoda-keiba-program`（旧: 園田特化予想プログラム）

| 環境 | パス例 |
|------|--------|
| オリジナル PC | `C:\Users\1180075\Desktop\プログラミング\sonoda-keiba-program` |
| 自宅 PC（2026-06） | `C:\Users\akimi\Desktop\プログラミング\sonoda-keiba-program` |
| その他 | `git clone` 後 `cd sonoda-keiba-program` |

**直近の目標:** **2026/6/3（火）園田** 当日オペ（予想 UI → note/X → 終了後データ更新）。UI・馬柱・`run_today.py` は **2026-06-02 実装済み**。

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

## 5. データファイル

**Git とクラウドの分担 → `docs/DATA_AND_GIT.md`**

| 優先度 | パス | Git | 同期 |
|--------|------|-----|------|
| **必須** | `data/processed/horses_master.csv` | 除外 | iCloud 等 |
| **必須** | `data/processed/payback_cache.json` | 除外 | 任意 / 再取得 |
| 推奨 | `data/raw/*.csv` | 除外 | iCloud 等 |
| **Git 管理** | `data/processed/race_style_cache.json` | **含める** | `git pull` |
| 任意 | `data/processed/race_lap_cache.json` | 除外 | 再取得可 |

---

## 6. 主要スクリプト

| コマンド | 用途 |
|---------|------|
| python scripts/fetch_races.py --date YYYYMMDD --save | レース結果取得（raw CSV のみ） |
| python scripts/build_features.py | 全 raw から特徴量 → master 再生成 |
| **`python scripts/fetch_daily.py --date YYYYMMDD`** | **取得 + master 更新を一括**（開催日の夜向け） |
| **`python run_today.py`** | **今日の日付で `fetch_daily` 実行 + LINE 通知**（ルート） |
| python scripts/predict.py --date YYYYMMDD | 予想 + 馬券案（CLI） |
| `.\.venv\Scripts\python.exe -m streamlit run app/predict_app.py` | **当日予想 UI**（推奨・VS Code タスク可） |
| `scripts/predict_ui.py` | 起動用ラッパーのみ（本体は `src/predictor/predict_ui_app.py`） |
| `python scripts/send_line_completion.py` | 作業完了サマリを LINE 送信（任意） |
| python scripts/backtest_bets.py --from ... --to ... | 馬券バックテスト |
| python scripts/fetch_paybacks.py --from ... --to ... | 払戻キャッシュ拡充 |
| python scripts/analyze_q1_collapse.py | 2026 Q1 三連複崩れ分析 |
| python scripts/tune_exotic_thresholds.py [--apply] | 三連系自信度閾値探索 |
| python scripts/tune_weights.py --objective sanrenpuku | 三連複ROI向け重み探索 |
| python scripts/compare_models.py --skip-tune | 3モデル比較（保存済み重み） |
| python scripts/walkforward_tune.py | ウォークフォワード再チューニング |
| python scripts/backfill_race_meta.py | 脚質・ラップキャッシュ |
| `Rscript r_analysis/scripts/01_run_baseline.R` | **R: 勝率・特徴量デシル等の集計表**（`r_analysis/output/tables/`） |
| `Rscript r_analysis/scripts/02_run_models.R` | **R: 1着ロジスティック試作**（`r_analysis/output/models/`） |
| `Rscript r_analysis/scripts/run_all.R` | 上記 R 分析一括 |
| `python scripts/repair_raw_encoding.py` | raw の文字化け日を netkeiba から再取得 |
| `python scripts/fix_csv_date_format.py` | raw の着差「○月○日」→ `○/○` 修復 |

---

## 7. 分析メモ（堅 vs 荒）

- 印外勝ち: 堅 10.3% → 荒 12.5%
- 有効: 1番人気>=3.0, head>=12, gap<=0.65, odds_std>=88, 下位クラス, 1700m+
- 無効: top3_prob_sum, odds_spread

---

## 8. 次にやること（優先順）

### 完了済み（2026-06）

- style vs sanrenpuku A/B → split scoring 採用
- 2026/1-5・期間分割・2025 通年バックテスト（split + 新三連系閾値）
- Q1 崩れ分析・1月 payback 84R 取得
- 三連系閾値 Q1 チューニング → `config/exotic_thresholds.json`
- **5月末まで master にデータあり**（確認済み）
- **当日予想 UI**（Streamlit）: 期待値 SS〜C、note/X コピペ、印表、馬柱、オフライン
- **馬柱**: 印5頭×横並び（馬名 + 前走〜5走）、HTML 静的表（ダブルクリック不要）
- **印表**: モデル確率（T=6・レース内相対）、勝率・連対率（予想日より前の園田成績）
- **`run_today.py`**: 実行日の `fetch_daily` + LINE 成否通知
- UI 本体を `src/predictor/predict_ui_app.py` に移動（UTF-16 化対策）
- **R 分析用 `r_analysis/` 追加**（Python 予想コードは未変更）→ **§11**
- **データ品質（2026-06-04）**: nar.netkeiba UTF-8 対応・6/3 raw 再取得・着差正規化 → **§11.3**

### 6/3 当日 — オペレーション（これで足りる）

| 段階 | 操作 |
|------|------|
| オッズ確定〜1R前 | `streamlit run app/predict_app.py` → 日付 `20260603` → 予想取得 |
| 投稿 | UI「コピー用」→ note（SS/S）/ X（A〜C）を手動公開・予約 |
| 全R終了後 | **`python run_today.py`**（または `fetch_daily.py --date 20260603`） |

**起動:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/predict_app.py
```

オフライン検証: UI で `20260529` + オフラインにチェック。詳細 → **§10**。

**GitHub 公開前チェックリスト**

1. `data/` は .gitignore のまま（master / payback は別途同期）
2. `.env` に `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_USER_ID`（`run_today` 用・リポジトリに含めない）
3. `pip install -r requirements.txt`
4. 出馬表・オッズ確定後に UI で本番日付を試す

### 任意（時間があれば）

- `build_features.py` — 脚質キャッシュ 3756 件を master に未反映なら実行
- `python scripts/backfill_race_meta.py` — 馬柱のペース・通過均が充実（当日必須ではない）
- **R 分析** — `r_analysis/` で特徴量と勝率の関係を確認（§11）。的中率改善の仮説出し用

### R 分析（自宅 PC 向け・2026-06-04 追加）

| 項目 | 内容 |
|------|------|
| フォルダ | `r_analysis/`（Git 管理・データ CSV は従来どおり .gitignore） |
| 入力 | `data/processed/horses_master.csv` |
| 初回 | `install.packages("tidyverse")` |
| 実行 | `Rscript r_analysis/scripts/01_run_baseline.R` → `02_run_models.R` |
| 詳細 | **§11**、`r_analysis/README.md` |

環境変数 `SONODA_KEIBA_ROOT` にリポジトリルートを指定するとパス検出が確実。

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
10. 自宅 PC: 5月末 master 確認済み
11. **当日予想 UI**（Streamlit）: `predict_day.py` + `predict_ui_app.py`
12. **期待値・投稿**: `expectation.py` / `post_format.py` / `rationale.py`（SS/S→note 詳細、A〜C→X）
13. **表示**: モデル確率（`DISPLAY_SOFTMAX_TEMPERATURE=6`）、勝率+連対率（`marks_display._career_rates_raw`）
14. **馬柱**: `horse_form.py` — `build_form_matrix_for_plan` + `form_matrix_html`
15. **UTF-16 対策**: UI 本体 `src/predictor/predict_ui_app.py`、起動は ASCII のみ `app/predict_app.py`
16. **`run_today.py`**: 本日 `fetch_daily` + LINE（`tools/line_bot.py`）
17. **`.editorconfig`**: charset utf-8
18. **データ文字化け修正**: `src/scraper/client.py` — `Content-Type: charset=UTF-8` を優先（旧 EUC-JP 固定を廃止）
19. **着差正規化**: `src/storage/csv_store.py` — `normalize_margin_value`（`3月4日` / ISO 日付 → `3/4`）
20. **6/3 raw 再取得**: `horses_20260603.csv` 修復済み → `build_features.py` で master 反映済み
21. **`r_analysis/`**: R 用探索スクリプト一式（§11）

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

**実装ファイル:**

| 役割 | パス |
|------|------|
| Streamlit 本体（**ここを編集**） | `src/predictor/predict_ui_app.py` |
| 起動（ASCII のみ・日本語禁止） | `app/predict_app.py`, `scripts/predict_ui.py` |
| 予想パイプライン | `src/predictor/predict_day.py` |
| 馬柱 | `src/predictor/horse_form.py` |
| 印表・通算率 | `src/predictor/marks_display.py` |
| 投稿文 | `src/predictor/post_format.py`, `rationale.py` |
| 期待値 | `src/predictor/expectation.py`, `config/expectation_tiers.json` |

### 10.3 MVP 画面要件 — **実装状況（2026-06-02）**

| # | 要件 | 状態 |
|---|------|------|
| 1 | 日付入力（デフォルト今日） | ✅ |
| 2 | 予想取得（出馬表 netkeiba） | ✅ |
| 3 | 進捗「n/12R 取得中…」 | ✅ |
| 4 | レース一覧（期待値ソート・折りたたみ） | ✅ |
| 5 | 印表: 印・馬名・**モデル確率**・**勝率・連対率**・オッズ・人気 | ✅（三連予想順列は削除済み） |
| 6 | 堅荒・自信度バッジ・1番人気・モデル確率 gap | ✅ |
| 7 | **馬柱**（印5頭・前走〜5走・横並び HTML 表） | ✅ |
| 8 | **コピー用** note/X（ティアで文面分岐） | ✅ |
| 9 | フィルタ（三連高のみ・単勝見送り除く・ティア） | ✅ |
| 10 | オフライン（master のみ） | ✅ |

**印表の意味（ユーザー向けキャプション）**

- **モデル確率** — レース内相対（softmax・表示のみ T=6）。馬券内部の `win_prob` は従来 T=1。
- **勝率** — 予想日より前の園田 **1着率**。
- **連対率** — 同条件の **2着以内率**。

**馬柱セル（1走分・改行テキスト）:** 日付・園田 / クラス・着順 / 距離・走破・馬場 / 頭数・馬番・人気 / 騎手・斤量 / 通過均・上がり3F・馬体重・ペース / 着差。ペース・通過は lap/style キャッシュ未投入の古い走は欠けることがある。

**オフライン:** `20260529` 推奨。

### 10.4 実装ステップ（会社 PC でこの順）

| Step | 内容 | 成果物 |
|------|------|--------|
| 1 | `src/predictor/predict_day.py`（新規）に `run_predict_day(date, *, offline=False) -> PredictDayResult` を切り出し。dataclass で `win_df`, `exotic_df`, `plans: List[RaceBetPlan]` を返す | `predict.py` から import してリファクタ |
| 2 | Streamlit MVP: 日付 + ボタン + plans ループ表示 | **完了** `predict_ui_app.py` |
| 3 | 進捗バー（`on_progress` コールバック） | **完了** |
| 4 | スタイル（堅/荒色・三連「高」を上にソート） | **完了**（簡易） |
| 5 | `requirements.txt` に `streamlit`、§6 起動コマンド | **完了** |
| 6 | 期待値 SS〜C + note/X コピペ | **完了** |
| 7 | 馬柱横並び + HTML 表示 | **完了** `horse_form.py` |
| 8 | 勝率・連対率・モデル確率表示 | **完了** `marks_display.py` / `score.py` |

**期待値・投稿**

- スコア: `src/predictor/expectation.py`（三連「高」ベースの暫定100点満点）
- 閾値: `config/expectation_tiers.json`（SS≥85, S≥70, A≥55, B≥40, C=それ未満）
- note: SS/S（展開・根拠あり）· X: A〜C（簡易印）· `post_format.format_race_copy` / `format_note_race_rich`
- 根拠文: `src/predictor/rationale.py`（脚質・ペース・騎手など。血統は出馬表に無く当日は未使用）

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
| オッズ確定後〜1R前 | Streamlit: `20260603` → **予想取得** |
| 投稿 | 各レース「コピー用」→ **note**（SS/S）/ **X**（A〜C）を手動公開・予約（自動投稿 API なし） |
| レース間 | オッズ変動時は UI で再取得可（通信制限に注意） |
| **全R終了後** | **`python run_today.py`**（= 本日の `fetch_daily` + LINE 通知） |

**データ更新の等价コマンド**

```powershell
# 推奨（日付自動 + LINE）
python run_today.py

# 同等（手動日付）
python scripts/fetch_daily.py --date 20260603

# 2段階でも可
python scripts/fetch_races.py --date 20260603 --save
python scripts/build_features.py
```

`fetch_daily` / `run_today` は **結果ページ**の取得。当日朝の予想は **出馬表**（UI の予想取得）で別ルート。当日は **`refresh_all.py` 禁止**（全期間スクレイプ・重い）。

**CLI フォールバック**

```powershell
python scripts/predict.py --date 20260603
```

### 10.9 Windows / エンコーディング注意（重要）

`scripts/predict_ui.py` や `app/predict_app.py` に **日本語を直接保存すると UTF-16 化**し、`SyntaxError: source code string cannot contain null bytes` になる事例あり（Cursor / Windows）。

- **UI ロジックは必ず** `src/predictor/predict_ui_app.py`（UTF-8）に書く
- 起動ファイルは ASCII ラッパーのみ
- 壊れたら: `predict_ui_app.py` を UTF-8 で復元、または PowerShell で UTF-8 書き直し
- ルート `.editorconfig` で `charset = utf-8`

### 10.10 `run_today.py`（ルート）

```python
# 本日 YYYYMMDD で scripts/fetch_daily.py を subprocess 実行
# 成功 / 失敗を tools/line_bot.send_line_message で通知
# .env: LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID
```

プロジェクトルートで `python run_today.py` を実行する前提（相対パス `.\.venv\Scripts\python.exe`）。

### 10.7 触らないもの（6/3 前）

- 馬券ロジック本体（`bets.py`）の大変更
- `--retune` / walkforward の当日実行
- sanrenpuku 重みの再チューニング（split 構成は固定）

### 10.8 参考ファイル

- 出馬表 HTML サンプル: `tests/fixtures/shutuba_202650052901.html`（6/3 が「次開催」リンク）
- 表示ロジック参考: `scripts/predict.py` の `_print_predictions`
- Agent 共通: ルート `AGENTS.md`

---

## 11. R 分析（`r_analysis/`）— 的中率探索・引き継ぎ

**作成:** 2026-06-04（会社 / OneDrive PC）  
**目的:** Python の馬券ロジック（`bets.py` 等）は**触らず**、`horses_master.csv` を R で読み、単勝率・3着内率と特徴量の関係を探索する。的中率改善の仮説 → 必要なら Python 側重み・閾値へ反映、という流れ用。

### 11.1 `horses_master.csv` と `horses_features.csv`

| ファイル | 内容 |
|----------|------|
| `data/raw/horses_YYYYMMDD.csv` | netkeiba 生データ（日本語ヘッダー・着差は `="3/4"` 形式で Excel 日付化を防止） |
| **`horses_master.csv`** | 全 raw 結合 + **特徴量列付与**（`build_features.py`）。**R 分析・予想の本体** |
| `horses_features.csv` | **中身は master と同一**（歴史的に2ファイル出力しているだけ） |

特徴量は「そのレースより前」の成績のみ（リーク防止）。列名は英語（`horse_win_rate`, `last3_avg_finish` 等）。

### 11.2 フォルダ構成

```
r_analysis/
  README.md              … 実行方法（英語）
  README_ja.md           … 日本語メモ（あれば）
  config/settings.R      … ANALYSIS_DATE_FROM 等（既定 20240101〜）
  R/                     … load / 集計 / glm 関数
  scripts/
    bootstrap.R          … パス解決 + source 一式
    01_run_baseline.R    … 集計 CSV
    02_run_models.R      … ロジスティック
    run_all.R            … 一括
  output/                … 結果（.gitignore）
```

**既存 Python ファイルは書き換えていない**（追加のみ: `r_analysis/`, `scripts/repair_raw_encoding.py`, データ修復用スクリプトの整理）。

### 11.3 データ品質（R 分析前に実施済み・2026-06-04）

| 問題 | 原因 | 対応 |
|------|------|------|
| 6/3 馬名・騎手が文字化け | nar.netkeiba が **UTF-8** 化したのに取得が **EUC-JP 固定** | `src/scraper/client.py` で `Content-Type` / meta charset 優先 |
| 着差が「3月4日」等 | Excel が `3/4` を日付化 | `normalize_margin_value` in `csv_store.py` + `fix_csv_date_format.py` |
| master に 6/3 未反映 | 上記の壊れた raw | `repair_raw_encoding.py` / `fetch_races.py --date 20260603 --save` → `build_features.py` |

**注意:** `horses_master.csv` を Excel で開いて保存しない（再文字化け・着差崩れ）。

### 11.4 RStudio セットアップ

1. **`sonoda-keiba-program.Rproj`** を開く（ルートの `.Rprofile` がパスを自動設定）
2. R コンソール: `install.packages(c("tidyverse", "jsonlite"))`
3. `source("r_analysis/scripts/00_setup.R")` でデータ・パッケージ確認
4. `source("r_analysis/scripts/run_all.R")` で一括実行

詳細: **`r_analysis/README_ja.md`**

```powershell
# ターミナルからも可
Rscript r_analysis/scripts/run_all.R
```

`data/processed/horses_master.csv` は Git 外（iCloud 等で同期）。回収率分析には `payback_cache.json` も使用（`03_roi_baseline.R`）。

### 11.5 出力と見方

| 出力 | 意味 |
|------|------|
| `output/tables/baseline_overall.csv` | 全体 `win_rate` / `top3_rate` |
| `output/tables/winrate_by_race_class.csv` | クラス別 |
| `output/tables/winrate_by_popularity_bin.csv` | 人気帯別 |
| `output/tables/winrate_by_odds_bin.csv` | オッズ帯別 |
| `output/tables/decile_winrate_*.csv` | 特徴量デシル別（どの水準で勝ちやすいか） |
| `output/models/logistic_win_coefficients.csv` | 1着 glm の係数・`odds_ratio` |

R 側で追加した列:

- `is_win` … 1着（単勝の当たり率分析用）
- `is_top3` … 3着以内（複勝・三連系の材料）
- `margin_lengths` … 着差の馬身相当（`3/4`, `ハナ` 等を数値化）

期間変更: `r_analysis/config/settings.R` の `ANALYSIS_DATE_FROM` / `ANALYSIS_DATE_TO`。

### 11.6 今後の R 作業案

- **着手済み:** `payback_cache.json` 結合の **ROI 帯分析**（`R/07_payback_roi.R`, `03_roi_baseline.R`）
- **未着手:**
- 堅/荒ラベル（Python `detect_win_profile` 相当）を R で再現しセグメント別勝率
- 特徴量重要度 → `tuned_weights_style.json` / `sanrenpuku` への反映は**手動判断**（自動書き込みはしない）
- 予想印・実着順のキャリブレーション（UI ログがあれば）

### 11.7 関連テスト

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_client.py tests/test_csv_store.py -q
```

*最終更新: 2026-06-04（R 分析 `r_analysis/`・データ UTF-8/着差修復を反映）。*

*大きな方針変更があったらこのファイルを更新すること。*
