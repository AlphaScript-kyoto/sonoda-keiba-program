"""Re-encode r_analysis R files from UTF-16 to UTF-8 if corrupted (Windows Cursor)."""
from __future__ import annotations
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "r_analysis" / "R" / "11_expected_value.R",
    ROOT / "r_analysis" / "R" / "12_jockey_track_bias.R",
    ROOT / "r_analysis" / "R" / "13_skipped_races.R",
    ROOT / "r_analysis" / "scripts" / "07_expected_value.R",
    ROOT / "r_analysis" / "scripts" / "08_jockey_track_bias.R",
    ROOT / "r_analysis" / "scripts" / "09_skipped_races.R",
    ROOT / "r_analysis" / "config" / "settings.R",
]
def fix_file(path: Path) -> bool:
    raw = path.read_bytes()
    if b"\x00" not in raw:
        return False
    text = raw.decode("utf-16-le")
    path.write_text(text, encoding="utf-8", newline="\n")
    return True
def main() -> None:
    for path in TARGETS:
        if not path.exists():
            print("skip missing", path)
            continue
        if fix_file(path):
            print("fixed UTF-16 -> UTF-8:", path)
        else:
            print("ok:", path)
if __name__ == "__main__":
    main()
