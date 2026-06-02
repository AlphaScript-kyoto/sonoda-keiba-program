"""オッズページパーサのテスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.odds import parse_win_odds_map

SAMPLE = """
<table class="RaceOdds_HorseList_Table">
<tr><th></th></tr>
<tr>
<td class="Waku3">3</td><td>3</td><td></td><td></td>
<td class="Odds"><span class="Odds ">80.0</span></td>
</tr>
<tr>
<td class="Waku1">1</td><td>1</td><td></td><td></td>
<td class="Odds"><span class="Odds ">4.8</span></td>
</tr>
</table>
"""


def test_parse_win_odds_map():
    m = parse_win_odds_map(SAMPLE)
    assert m["1"] == "4.8"
    assert m["3"] == "80.0"
