import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.predictor.backtest import BET_UNIT, _finish_order, _load_paybacks_for_races
from src.predictor.bets import DEFAULT_STRATEGY, assign_marks, build_race_bet_plan, build_sanrenpuku_formation_firm, check_sanrenpuku_formation_firm_hit
from src.predictor.score import load_master, predict_date
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.t10_daily_roi import is_tier_s_plus, build_t10_daily_roi_report, S_PLUS_BUY_LABEL
from src.predictor.snapshot_compare import list_snapshot_race_ids

@dataclass
class Stats:
    races=0; hits=0; investment=0; return_yen=0; ss=0; s=0
    def roi(self):
        return self.return_yen/self.investment*100 if self.investment else 0

def main(year: str):
    master=load_master(); w,e=load_split_scoring_configs()
    dates=sorted(d for d in master["date"].astype(str).unique() if d.startswith(year))
    rids=sorted(master.loc[master["date"].astype(str).isin(dates),"race_id"].astype(str).unique())
    pb=_load_paybacks_for_races(rids, fetch_missing=False)
    s=Stats(); bt=defaultdict(Stats); t10=Stats()
    for i,date in enumerate(dates,1):
        if i%20==0: print(f"progress {i}/{len(dates)}", flush=True)
        day=master[master["date"].astype(str)==date]
        dw=predict_date(date,master=master,fetch_entries=False,config=w)
        de=predict_date(date,master=master,fetch_entries=False,config=e)
        ex={str(r):g for r,g in de.groupby("race_id",sort=False)}
        hist=master[master["date"].astype(str)<date]
        for rid in sorted(day["race_id"].astype(str).unique()):
            wg=dw[dw["race_id"].astype(str)==rid]
            if wg.empty: continue
            fin=_finish_order(master[master["race_id"].astype(str)==rid])
            if len(fin)<3: continue
            plan=build_race_bet_plan(wg,exotic_race=ex.get(rid,wg),strategy=DEFAULT_STRATEGY,master=hist,before_date=date)
            if not is_tier_s_plus(plan.expectation_tier): continue
            form=build_sanrenpuku_formation_firm(assign_marks(ex.get(rid,wg)))
            if not form or form.points<=0: continue
            inv=form.points*BET_UNIT; hit=check_sanrenpuku_formation_firm_hit(form,fin)
            ret=pb.get(rid).fuku3_yen if hit and pb.get(rid) else 0
            s.races+=1; s.investment+=inv; s.return_yen+=ret
            if hit: s.hits+=1
            bt[plan.expectation_tier].races+=1; bt[plan.expectation_tier].investment+=inv; bt[plan.expectation_tier].return_yen+=ret
            if hit: bt[plan.expectation_tier].hits+=1
            if plan.expectation_tier=="SS": s.ss+=1
            else: s.s+=1
        if list_snapshot_race_ids(date,label="t_minus_10"):
            rep=build_t10_daily_roi_report(date,master=master,fetch_payback=False)
            for row in rep.races:
                t10.races+=1; t10.investment+=row.investment; t10.return_yen+=row.return_yen
                if row.sanren_hit: t10.hits+=1
    p=s.return_yen-s.investment; sg="+" if p>0 else ""
    lines=[f"year={year}", S_PLUS_BUY_LABEL, f"races={s.races} SS={s.ss} S={s.s} invest={s.investment} return={s.return_yen} pl={sg}{p} roi={s.roi():.1f} hits={s.hits}/{s.races}"]
    for t in ("SS","S"):
        b=bt.get(t)
        if b and b.races: lines.append(f"tier {t}: {b.races}R roi={b.roi():.1f}% hits={b.hits}/{b.races}")
    if t10.races: lines.append(f"T10: {t10.races}R roi={t10.roi():.1f}% hits={t10.hits}/{t10.races}")
    out=ROOT/"data"/"processed"/"logs"/f"s_plus_roi_{year}.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines), flush=True)

if __name__ == "__main__":
    main(sys.argv[1])
