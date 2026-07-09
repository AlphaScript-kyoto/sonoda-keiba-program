import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.scraper.shutuba import fetch_shutuba_html
html = fetch_shutuba_html("202650070901")
for s in ["id=\"tr_1\"", "HorseList", "CheckMark"]:
    print(s, html.count(s))
