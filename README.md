# 園田特化予想プログラム

園田競馬（netkeiba 地方競馬）のレースデータ取得・CSV保存・簡易予想を行うプロジェクトです。

## セットアップ

```powershell
cd "c:\Users\1180075\Desktop\プログラミング\園田特化予想プログラム"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
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

# 予想（CSV が溜まってから）
python scripts/predict.py
```

### 取得期間の設定

`config/scrape_range.py` で開始・終了日（YYYYMMDD）を指定します。将来は最古日～最新日に変更して一括取得できます。

## ディレクトリ構成

- `config/` … 会場コード・URL・パス
- `src/scraper/` … netkeiba からの取得・パース
- `src/storage/` … CSV 保存
- `src/predictor/` … 勝率などの簡易予想
- `data/raw/` … 取得した生 CSV
- `scripts/` … 実行用エントリポイント

## netkeiba 利用上の注意

- 個人の学習・研究目的での利用を想定しています
- リクエスト間隔は `config/settings.py` の `REQUEST_INTERVAL_SEC`（既定 **2.0 秒**）を守ってください
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
4. [ ] 過去データによる勝率予想
