# Data and Git

Code syncs via GitHub. Large CSV (master / raw) sync via iCloud (or similar).

## In Git

- src/, scripts/, app/, tests/, tools/
- config/*.json, config/*.py
- docs/, README.md, AGENTS.md, .cursor/rules/
- requirements.txt, .streamlit/
- .env.example (no real tokens)
- data/processed/race_style_cache.json (footwork cache)

## Not in Git

- .venv/, .env
- horses_master.csv, horses_features.csv, data/raw/*.csv
- payback_cache.json, race_lap_cache.json, bloodline_cache.json
- marks_fav_exotic pkl dirs
- *.log, *.err

## New PC

git clone, pip install, copy .env.example to .env, place horses_master from iCloud.

## Before git add

git check-ignore -v data/processed/horses_master.csv .env  (must be ignored)
git check-ignore -v data/processed/race_style_cache.json (must NOT be ignored)

git add data/processed/race_style_cache.json if needed
git add .
git status  (no master, payback, .env)

See PROJECT_STATUS.md section 10.6 for race day.