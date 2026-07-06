from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import sys
ROOT = Path(r"c:\Users\akimi\Desktop\programming\sonoda-keiba-program")
sys.path.insert(0, str(ROOT))
from src.predictor.backtest import BET_UNIT, _finish_order, _load_paybacks_for_races
from src.predictor.bets import DEFAULT_STRATEGY, assign_marks, build_race_bet_plan, build_sanrenpuku_formation_firm, check_sanrenpuku_formation_firm_hit
from src.predictor.score import load_master, predict_date
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.t10_daily_roi import is_tier_s_plus, build_t10_daily_roi_report, S_PLUS_BUY_LABEL
from src.predictor.snapshot_compare import list_snapshot_race_ids

@dataclass
class Stats:
    races=0; hits=0; investment=0; return_yen=0; ss=0; s=0; no_pb=0
    def roi(self):
        return self.return_yen/self.investment*100 if self.investment else 0

master=load_master(); win_cfg,ex_cfg=load_split_scoring_configs()
dates=sorted(d for d in master["date"].astype(str).unique() if d[:4] in ("2024","2025","2026"))
rids=sorted(master.loc[master["date"].astype(str).isin(dates),"race_id"].astype(str).unique())
pb=_load_paybacks_for_races(rids, fetch_missing=False)
total=Stats(); byy=defaultdict(Stats); byt=defaultdict(Stats)
for i,date in enumerate(dates,1):
    if i%25==0: print(f"progress {i}/{len(dates)} {date}", flush=True)
    y=date[:4]; day=master[master["date"].astype(str)==date]
    dw=predict_date(date, master=master, fetch_entries=False, config=win_cfg)
    de=predict_date(date, master=master, fetch_entries=False, config=ex_cfg)
    ex={str(r):g for r,g in de.groupby("race_id", sort=False)}
    hist=master[master["date"].astype(str)<date]
    for rid in sorted(day["race_id"].astype(str).unique()):
        wg=dw[dw["race_id"].astype(str)==rid]
        if wg.empty: continue
        fr=master[master["race_id"].astype(str)==rid]; fin=_finish_order(fr)
        if len(fin)<3: continue
        eg=ex.get(rid, wg)
        plan=build_race_bet_plan(wg, exotic_race=eg, strategy=DEFAULT_STRATEGY, master=hist, before_date=date)
        if not is_tier_s_plus(plan.expectation_tier): continue
        form=build_sanrenpuku_formation_firm(assign_marks(eg))
        if not form or form.points<=0: continue
        inv=form.points*BET_UNIT; hit=check_sanrenpuku_formation_firm_hit(form, fin); ret=0
        if hit:
            p=pb.get(rid)
            if p: ret=p.fuku3_yen
            else: total.no_pb+=1; byy[y].no_pb+=1
        for b in (total, byy[y], byt[plan.expectation_tier]):
            b.races+=1; b.investment+=inv; b.return_yen+=ret
            if hit: b.hits+=1
        if plan.expectation_tier=="SS": byy[y].ss+=1
        else: byy[y].s+=1

lines=[]
lines.append("Sonoda S+ ROI 2024-2026 (final odds)")
lines.append(S_PLUS_BUY_LABEL)
for y in ("2024","2025","2026"):
    s=byy[y]; p=s.return_yen-s.investment; sg="+" if p>0 else ""
    lines.append(f"{y}: {s.races}R SS{s.ss}/S{s.s} invest={s.investment:,} return={s.return_yen:,} P/L={sg}{p:,} ROI={s.roi():.1f}% hits={s.hits}/{s.races}")
p=total.return_yen-total.investment; sg="+" if p>0 else ""
lines.append(f"TOTAL: {total.races}R invest={total.investment:,} return={total.return_yen:,} P/L={sg}{p:,} ROI={total.roi():.1f}% hits={total.hits}/{total.races}")
for t in ("SS","S"):
    s=byt[t]
    if s.races: lines.append(f" tier {t}: {s.races}R ROI={s.roi():.1f}% hits={s.hits}/{s.races}")

t10=Stats(); t10y=defaultdict(Stats)
for date in dates:
    if not list_snapshot_race_ids(date, label="t_minus_10"): continue
    rep=build_t10_daily_roi_report(date, master=master, fetch_payback=False)
    y=date[:4]
    for row in rep.races:
        for b in (t10, t10y[y]):
            b.races+=1; b.investment+=row.investment; b.return_yen+=row.return_yen
            if row.sanren_hit: b.hits+=1
lines.append("")
lines.append("T-10 snapshot days only")
for y in sorted(t10y): lines.append(f" {y}: {t10y[y].races}R ROI={t10y[y].roi():.1f}% hits={t10y[y].hits}/{t10y[y].races}")
lines.append(f" T10 TOTAL: {t10.races}R ROI={t10.roi():.1f}% hits={t10.hits}/{t10.races}")
out=ROOT/"data"/"processed"/"logs"/"s_plus_roi_2024_2026.txt"
out.parent.mkdir(parents=True, exist_ok=True)
text="\n".join(lines)
out.write_text(text, encoding="utf-8")
print(text)
print(f"\nWrote {out}")
