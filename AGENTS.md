# Cursor Agent 向けガイド

**作業開始前に必ず `docs/PROJECT_STATUS.md` を読むこと。**

リポジトリ名 / フォルダ名: **sonoda-keiba-program**（旧: 園田特化予想プログラム）

## クイックスタート

```powershell
git clone https://github.com/AlphaScript-kyoto/sonoda-keiba-program.git
cd sonoda-keiba-program
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

既にクローン済みの場合:

```powershell
# サーバーPC
cd "C:\Users\ServerPC\Desktop\programming\sonoda-keiba-program"
# オリジナル PC
# cd "C:\Users\1180075\Desktop\プログラミング\sonoda-keiba-program"
```

iCloud 等から `data/`（**master / raw**）を配置。`race_style_cache.json` は **Git に含まれる**。

```powershell
python scripts/predict.py --date YYYYMMDD
.\.venv\Scripts\python.exe app/predict_desktop.py   # 当日予想デスクトップ（推奨）
.\.venv\Scripts\python.exe -m streamlit run app/predict_app.py   # 当日予想 Web UI（Streamlit）
python scripts/backtest_bets.py --from YYYYMMDD --to YYYYMMDD
```

データ・Git の分担: **`docs/DATA_AND_GIT.md`**

## 変更時の注意

- 馬券ロジックは `src/predictor/bets.py`、バックテストは `src/predictor/backtest.py`
- スコアリング: split scoring（単勝=`tuned_weights_style.json` / 三連=`tuned_weights_sanrenpuku.json`）。詳細は PROJECT_STATUS §2
- walkforward 版は `config/tuned_weights_walkforward.json` に退避済み
- データ CSV / payback キャッシュは再取得に数時間かかる。削除・上書きに注意
- コミットはユーザーが明示したときのみ

## 詳細

設計・バックテスト数値・未完了タスク・データ要件 → **`docs/PROJECT_STATUS.md`**

**当日予想デスクトップ（推奨）:** `app/predict_desktop.py` → `src/predictor/predict_desktop_app.py`（Flet）。デスクトップショートカット: `scripts/create_desktop_shortcut.ps1` / 起動: `scripts/start_predict_desktop.cmd`。

**当日予想 Web UI:** `app/predict_app.py`（薄い起動のみ）→ 本体は `src/predictor/predict_ui_app.py`（**UTF-8 必須**）。`scripts/predict_ui.py` は同じ起動用。**`scripts/predict_ui.py` に日本語を直接書かない**（Windows で UTF-16 化し SyntaxError になる事例あり）。