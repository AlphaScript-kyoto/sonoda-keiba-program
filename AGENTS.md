# Cursor Agent 向けガイド

**作業開始前に必ず `docs/PROJECT_STATUS.md` を読むこと。**

リポジトリ名 / フォルダ名: **sonoda-keiba-program**（旧: 園田特化予想プログラム）

## クイックスタート

```powershell
git clone <repo-url>
cd sonoda-keiba-program
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

オリジナル PC で既にクローン済みの場合:

```powershell
cd "C:\Users\1180075\Desktop\プログラミング\sonoda-keiba-program"
```

iCloud 等から `data/` をプロジェクト直下に配置（`.gitignore` 対象のため GitHub には無い）。

```powershell
python scripts/predict.py --date YYYYMMDD
python scripts/backtest_bets.py --from YYYYMMDD --to YYYYMMDD
```

## 変更時の注意

- 馬券ロジックは `src/predictor/bets.py`、バックテストは `src/predictor/backtest.py`
- スコアリング重みのデフォルトは `config/tuned_weights.json`（**style 重み**）
- walkforward 版は `config/tuned_weights_walkforward.json` に退避済み
- データ CSV / payback キャッシュは再取得に数時間かかる。削除・上書きに注意
- コミットはユーザーが明示したときのみ

## 詳細

設計・バックテスト数値・未完了タスク・データ要件 → **`docs/PROJECT_STATUS.md`**