from datetime import datetime
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scraper.race_snapshots import load_schedule
from src.predictor.race_day_notify import (
    build_watch_start_line_message,
    build_race_line_messages,
    build_upset_high_admin_line_message,
    build_s_plus_payback_message,
)
from src.predictor.t10_daily_roi import (
    evaluate_s_plus_payback_for_race,
    build_t10_daily_roi_report,
    format_t10_daily_roi_message,
)
from src.predictor.p6_payback import evaluate_p6_payback_for_race, build_p6_payback_message
from src.predictor.upset_high_daily_roi import (
    build_upset_high_daily_roi_report,
    format_upset_high_daily_roi_message,
)
from src.predictor.score import load_master
from src.scraper.payback import fetch_paybacks
from tools.discord_bot import send_discord_message

DATE = "20260708"
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
master = load_master()
schedule = load_schedule(DATE)
if not schedule or not schedule.get("races"):
    raise SystemExit(f"schedule not found for {DATE}")

sent = []

def push(cat, text):
    if not text or not str(text).strip():
        return
    body = f"【リプレイ送信テスト {DATE}】\ntime={now}\n\n" + text
    send_discord_message(body, category=cat)
    sent.append(cat)

print("send: watch_broadcast start")
push("watch_broadcast", build_watch_start_line_message(DATE, schedule))

races = sorted(schedule.get("races", []), key=lambda r: int(r.get("race_no", 0)))
for race in races:
    rno = int(race.get("race_no", 0))
    plan, t10_text, buy_text = build_race_line_messages(DATE, rno)
    push("t10_predict", t10_text)
    if buy_text:
        push("s_plus_buy", buy_text)
    p6buy = build_upset_high_admin_line_message(DATE, rno, plan)
    if p6buy:
        push("p6_buy", p6buy)

print("send: payback samples")
race_ids = [str(r.get("race_id", "")) for r in races if r.get("race_id")]
pb_map = fetch_paybacks(race_ids, use_cache=True, stop_on_block=False)
for race in races:
    rid = str(race.get("race_id", ""))
    if not rid:
        continue
    pb = pb_map.get(rid)
    if pb is None:
        continue
    rno = int(race.get("race_no", 0))
    ev = evaluate_s_plus_payback_for_race(DATE, rid, pb, master=master)
    if ev is not None:
        msg = build_s_plus_payback_message(DATE, race_no=rno, race_name=str(race.get("race_name", "")), evaluation=ev)
        push("s_plus_payback", msg)
        break

for race in races:
    rid = str(race.get("race_id", ""))
    if not rid:
        continue
    pb = pb_map.get(rid)
    if pb is None:
        continue
    rno = int(race.get("race_no", 0))
    p6ev = evaluate_p6_payback_for_race(DATE, rid, pb, master=master)
    if p6ev is not None:
        p6msg = build_p6_payback_message(race_no=rno, race_name=str(race.get("race_name", "")), evaluation=p6ev)
        push("p6_payback", p6msg)
        break

print("send: nightly")
t10_report = build_t10_daily_roi_report(DATE, master=master, fetch_payback=False)
push("watch_broadcast", format_t10_daily_roi_message(t10_report))
uh_report = build_upset_high_daily_roi_report(DATE, master=master, fetch_payback=False)
push("watch_broadcast", format_upset_high_daily_roi_message(uh_report))

print(f"replay sent count={len(sent)}")
print(dict(Counter(sent)))
