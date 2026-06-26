import json, sys
from collections import Counter
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.predictor.backtest import _finish_order
from src.predictor.bets import DEFAULT_STRATEGY, build_race_bet_plan
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.predictor.t10_daily_roi import build_t10_daily_roi_report
from src.scraper.race_snapshots import LABEL_T_MINUS_10, snapshot_path
date = sys.argv[1] if len(sys.argv) > 1 else "20260626"
win_cfg, ex_cfg = load_split_scoring_configs()
master = load_master()
hist = master[master["date"].astype(str) < date]
day = master[master["date"].astype(str) == date]
schedule_rnos = sorted(day["race_no"].astype(int).unique().tolist()) if not day.empty else []
t10_ids = list_snapshot_race_ids(date, label=LABEL_T_MINUS_10)
print("master races", schedule_rnos, "count", len(schedule_rnos))
print("t10 snapshots count", len(t10_ids))
rows = []
for rid in sorted(t10_ids, key=lambda x: int(x.split("_")[-1])):
    snap = json.loads(snapshot_path(date, rid, LABEL_T_MINUS_10).read_text(encoding="utf-8"))
    live = pd.DataFrame(snap.get("entries", []))
    if live.empty:
        rows.append({"rno": int(rid[-2:]), "status": "empty_snap"})
        continue
    sw = score_entries(live, hist, config=win_cfg)
    se = score_entries(live, hist, config=ex_cfg)
    plan = build_race_bet_plan(sw, exotic_race=se, strategy=DEFAULT_STRATEGY, master=hist, before_date=date)
    final = master[master["race_id"].astype(str) == rid]
    finish_ok = len(_finish_order(final)) >= 3 if not final.empty else False
    rows.append({"rno": plan.race_no, "tier": plan.expectation_tier, "score": plan.expectation_score, "ex": plan.exotic_profile + "/" + plan.exotic_confidence[0], "fav": plan.fav_odds, "finish_ok": finish_ok, "in_master": not final.empty})
print()
for r in rows:
    if "status" in r:
        print(r["rno"], r["status"])
    else:
        print(r["rno"], r["tier"], r["score"], r["ex"], r["fav"], r["in_master"], r["finish_ok"])
print("tier counts", dict(Counter(r.get("tier", "?") for r in rows)))
rep = build_t10_daily_roi_report(date, fetch_payback=False)
print("report races", len(rep.races), "skipped_not_s_plus", rep.skipped_not_s_plus, "skipped_no_result", rep.skipped_no_result)
