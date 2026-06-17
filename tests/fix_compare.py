from pathlib import Path
ROOT = Path(r"c:/Users/akimi/Desktop/programming/sonoda-keiba-program")
# fix compare script if utf16
p = ROOT / "scripts/compare_win_domain_ab.py"
b = p.read_bytes()
if b.count(b"\x00"):
    p.write_text(b.decode("utf-16-le"), encoding="utf-8", newline="\n")
    print("fixed utf16")
else:
    print("script ok")
