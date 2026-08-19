# sonoda-keiba-program

園田競馬（netkeiba 地方競馬）のレースデータ取得・CSV保存・予想・馬券戦略を行うプロジェクトです。

## セットアップ

```powershell
# GitHub から取得する場合
git clone https://github.com/AlphaScript-kyoto/sonoda-keiba-program.git
cd sonoda-keiba-program

# 既にローカルにある場合の例
# サーバーPC:  cd "C:\Users\ServerPC\Desktop\programming\sonoda-keiba-program"
# オリジナルPC: cd "C:\Users\1180075\Desktop\プログラミング\sonoda-keiba-program"

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # 中身に LINE / Discord の値を入れる（.env は Git に載せない）
```

## 使い方

```powershell
# 1日分（例: 2026/05/22 園田）
python scripts/fetch_races.py --date 20260522 --save

# 期間指定（config または CLI）
# config/scrape_range.py の DATE_FROM / DATE_TO を編集してから:
python scripts/fetch_races.py --save
python scripts/fetch_races.py --from 20260520 --to 20260522 --save

# 単一レース
python scripts/fetch_races.py --race-id 202650052201 --save

# 予想（CLI）
python scripts/predict.py --date YYYYMMDD

# 当日予想デスクトップ（推奨）
.\.venv\Scripts\python.exe app/predict_desktop.py

# 当日予想 UI（ブラウザ）
.\.venv\Scripts\python.exe -m streamlit run app/predict_app.py

# 当日ウォッチ（T-10 予想 → Discord/LINE）
python scripts/watch_race_day.py

# 夜間取得（結果・master 更新・通知）
python run_today.py

# 2026/7 振り返り（※ scripts\ 配下を指定。直下の analyze_july2026.py ではない）
.\.venv\Scripts\python.exe scripts\analyze_july2026.py --quick
.\.venv\Scripts\python.exe scripts\export_backtest_for_r.py --from 20260101 --to 20260731
# RStudio: source("r_analysis/scripts/10_july2026_review.R", encoding = "UTF-8")
# コマンド一覧: r_analysis/scripts/JULY2026_COMMANDS.txt
```

ログは `data/processed/logs/watch_YYYYMMDD.log` に残ります。DNS など一時的な通信失敗時は、HTTP 側の再試行に加え、発走前まで約60秒おきに T-10 投稿を再挑戦します。

## サーバーPCでの自動運用

詳細は `SERVER_SETUP_GUIDE.md` を参照してください。タスク登録は次のコマンドです。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_server_tasks.ps1
```

| タスク名 | 時刻 | 内容 |
|----------|------|------|
| 園田_当日監視 | 毎日 09:00 | `watch_race_day.py`（T-10 予想など） |
| 心拍チェック(20min) | 09:00〜12時間・15分間隔 | 監視プロセスの生存確認 |
| 園田_夜間取得 | 毎日 21:00 | `run_today.py` |

**重要:** 手元PC側の同名タスクは無効化してください（二重通知防止）。
### 取得期間の設定

`config/scrape_range.py` で開始・終了日（YYYYMMDD）を指定します。将来は最古日～最新日に変更して一括取得できます。

## データと Git

- **コード・設定** → GitHub（`docs/DATA_AND_GIT.md` 参照）
- **master / raw CSV** → iCloud 等（Git には入れない）
- **脚質キャッシュ** → `data/processed/race_style_cache.json` は Git 管理

clone 後は `data/processed/horses_master.csv` をクラウドから置くこと。

## ディレクトリ構成

- `config/` … 会場コード・URL・パス・重み・ゲート設定
- `src/scraper/` … netkeiba からの取得・パース
- `src/storage/` … CSV 保存
- `src/predictor/` … 予想・馬券・当日 UI / デスクトップ
- `app/predict_desktop.py` … 当日予想デスクトップ（Flet）の起動
- `app/predict_app.py` … 当日予想 Web UI（Streamlit）の起動
- `docs/OPS_GATE_SPEC_202607.md` … 2026/7 分析に基づく当日ゲート仕様（Phase1 実装済）
- `config/ops_gates.json` … T-10 買い目ゲート設定（R1/R2/R3）
- `src/predictor/ops_gates.py` … ゲート判定
- `SERVER_SETUP_GUIDE.md` … サーバーPCへの引っ越し・タスク登録
- `data/raw/` … 取得した生 CSV（Git には入れない）
- `scripts/` … 実行用エントリポイント

## netkeiba 利用上の注意

- 個人の学習・研究目的での利用を想定しています
- リクエスト間隔は `config/settings.py` の `REQUEST_INTERVAL_MIN_SEC`～`MAX_SEC`（既定 **7～10 秒**）を守ってください
- 一括取得は数時間かかります。中断しても同日の CSV があれば `--save` 時にスキップされます
- 取得データは必ず主催者発表と照合してください

## 取得期間（園田）

`config/scrape_range.py` で指定。調査時点の最古開催は **2015/02/25** 頃です。

## CSV の主な列

| 列 | 内容 |
|----|------|
| `horse_id` / `horse_url` | netkeiba DB の馬ID・URL（同一馬の蓄積キー） |
| `sex_age` | 性齢（例: 牝8） |
| `race_time` | 走破タイム |
| `popularity` / `odds` | 人気・単勝オッズ |
| `last_3f` / `carried_weight` | 後3F・斤量 |
| `distance` / `track` / `direction` | 距離・馬場状態・右/左 |
| `waku` / `umaban` / `margin` | 枠番・馬番・着差 |
| `weather` / `race_class` / `head_count` | 天候・クラス・頭数 |
| `surface` | ダ/芝（参考） |

### 特徴量（processed）

```powershell
python scripts/build_features.py
```

`data/processed/horses_features.csv` と **`horses_master.csv`**（全列まとめ1ファイル）に出力。

一括更新（raw 再取得 → 特徴量 → マスタ）:

```powershell
python scripts/refresh_all.py
```

ログ: `data/processed/refresh_log.txt`

### 列追加後の raw データ更新

新しい列が無い日付の CSV は、再実行で自動的に再取得されます:

```powershell
python scripts/fetch_races.py --save
```

## 実装ロードマップ

1. [x] 1レース結果の取得・パース
2. [x] 開催日単位の一括取得
3. [x] CSV 保存
4. [x] 過去データによる勝率予想・馬券案・当日 UI / サーバー自動運用

## 開発者向け（出先 PC / 新規 Cursor セッション）

会話履歴は端末間で引き継がれないことがある。**続きから作業するときは以下を読む:**

- [`AGENTS.md`](AGENTS.md) … Cursor Agent 向けクイックスタート
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) … 馬券戦略・重み・バックテスト数値・データ要件・TODO

データ（`horses_master.csv`, `payback_cache.json` 等）は `.gitignore` のため GitHub 以外（iCloud 等）から `data/` を配置すること。
