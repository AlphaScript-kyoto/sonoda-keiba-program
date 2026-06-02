from pathlib import Path
import ast

root = Path(__file__).resolve().parent.parent
files = [
    "scripts/fetch_paybacks.py",
    "scripts/analyze_q1_collapse.py",
    "scripts/tune_exotic_thresholds.py",
    "src/predictor/backtest.py",
]
for f in files:
    ast.parse((root / f).read_text(encoding="utf-8"), filename=f)
    print("parse OK", f)

p = root / "scripts/analyze_q1_collapse.py"
t = p.read_text(encoding="utf-8")
start = t.index("def _print_row")
end = t.index("def main")
new_block = '''def _print_row(s: dict) -> None:
    if not s["races"]:
        print(f"  {s['label']}: (no races)")
        return
    hr = s["sp_hit_n"] / s["exotic_bets"] if s["exotic_bets"] else 0.0
    print(
        f"  {s['label']}: {s['races']}R "
        f"\u5805\u5358{s['win_ken']/s['races']:.1%} \u5805\u4e09{s['ex_ken']/s['races']:.1%} "
        f"\u4e09\u9023\u7684\u4e2d{hr:.1%} \u7684\u4e2d\u914d\u5f53\u4e2d\u592e{s['sp_hit_med']:,.0f}\u5186 "
        f"ROI \u5358{s['win_roi']:.1%} \u4e09\u9023{s['sanren_roi']:.1%} \u30ef{s['wide_roi']:.1%}"
    )


'''
t = t[:start] + new_block + t[end:]
p.write_text(t, encoding="utf-8")
ast.parse(t)

tp = root / "scripts/tune_exotic_thresholds.py"
tt = tp.read_text(encoding="utf-8")
tt = tt.replace("from dataclasses import asdict, replace\n", "from dataclasses import asdict\n")
tt = tt.replace("    BetStrategyConfig,\n", "")
tp.write_text(tt, encoding="utf-8")
ast.parse(tt)
print("fixes applied")
