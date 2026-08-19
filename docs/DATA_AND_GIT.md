# Data and Git

コードは GitHub（https://github.com/AlphaScript-kyoto/sonoda-keiba-program）で同期します。大きな CSV（master / raw）は iCloud 等で別同期します。

## In Git

- src/, scripts/, app/, tests/, tools/
- config/*.json, config/*.py
- docs/, README.md, AGENTS.md, SERVER_SETUP_GUIDE.md, .cursor/rules/
- requirements.txt, .streamlit/
- .env.example（実トークンは書かない）
- data/processed/race_style_cache.json（脚質キャッシュ）

## Not in Git

- .venv/, .env
- horses_master.csv, horses_features.csv, data/raw/*.csv
- payback_cache.json, race_lap_cache.json, bloodline_cache.json
- line_team_registry.json（LINE の user_id / 表示名）
- data/processed/logs/, data/processed/snapshots/
- marks_fav_exotic pkl dirs
- *.log, *.err, *.rds
- RESTORE_SERVER.txt（手元展開メモ。.env を含む ZIP 向け）

## New PC

```powershell
git clone https://github.com/AlphaScript-kyoto/sonoda-keiba-program.git
cd sonoda-keiba-program
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

その後 `horses_master.csv` を iCloud 等から `data/processed/` へ置く。

## Before git add

git check-ignore -v data/processed/horses_master.csv .env  (must be ignored)
git check-ignore -v data/processed/line_team_registry.json  (must be ignored)
git check-ignore -v data/processed/race_style_cache.json (must NOT be ignored)

git add data/processed/race_style_cache.json if needed
git add .
git status  (no master, payback, .env, line_team_registry)

See PROJECT_STATUS.md section 10.6 for race day.
