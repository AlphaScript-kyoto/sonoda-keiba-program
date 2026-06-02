from pathlib import Path
import re
t=Path("src/predictor/backtest.py").read_text(encoding="utf-8")
for line in t.splitlines():
    if "exotic_profile" in line and "==" in line:
        for m in re.findall('"([^"]+)"', line):
            print(m, [hex(ord(c)) for c in m])
t2=Path("src/predictor/bets.py").read_text(encoding="utf-8")
for fn in ("detect_win_profile", "detect_exotic_profile"):
    i=t2.index("def "+fn)
    chunk=t2[i:i+1200]
    for m in re.findall('return "([^"]+)"', chunk):
        print(fn, m, [hex(ord(c)) for c in m])
