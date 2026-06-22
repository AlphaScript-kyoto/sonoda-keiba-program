"""Tests for intraday upset-high settlement at next-race T-20."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.race_day_notify import process_due_upset_high_settlements
from src.predictor.upset_high_bet_gate import (
    UPSET_HIGH_SETTLE_OFFSET,
    UpsetHighBetState,
    _race_id_for_no,
    _race_results_ready,
    record_signaled_bet,
    settle_pending_before_race,
)
from src.scraper.race_snapshots import CaptureJob


def _mock_rec(*, race_no: int = 1, hit: bool = False):
    return SimpleNamespace(
        date="20260619",
        race_no=race_no,
        exotic_profile="\u8352",
        exotic_prob_top=0.99,
        exotic_prob_gap=0.95,
        sanrenpuku_formation_points=5,
        sanrenpuku_formation_hit=hit,
        fuku3_yen=860 if hit else 0,
    )


def test_race_results_ready():
    master = pd.DataFrame(
        {
            "race_id": ["r1", "r1", "r1"],
            "finish": ["1", "2", "3"],
        }
    )
    assert _race_results_ready(master, "r1")
    assert not _race_results_ready(master, "r9")


def test_race_id_for_no():
    schedule = {
        "races": [
            {"race_no": 1, "race_id": "202650061901"},
            {"race_no": 2, "race_id": "202650061902"},
        ]
    }
    assert _race_id_for_no(schedule, 2) == "202650061902"


def test_settle_pending_before_race_miss_increments_streak():
    st = UpsetHighBetState(consecutive_misses=2)
    record_signaled_bet(st, "20260619", 1, 500)
    rec_map = {("20260619", 1): _mock_rec(hit=False)}

    with patch(
        "src.predictor.upset_high_bet_gate._build_rec_map", return_value=rec_map
    ):
        st, settled = settle_pending_before_race(
            "20260619",
            2,
            state=st,
            schedule={"races": []},
            fetch_if_missing=False,
        )

    assert settled == [1]
    assert st.consecutive_misses == 3
    assert len(st.pending_signals) == 0
    assert len(st.recent_bets) == 1
    assert not st.recent_bets[0].hit


def test_settle_pending_before_race_hit_resets_streak():
    st = UpsetHighBetState(consecutive_misses=3)
    record_signaled_bet(st, "20260619", 1, 500)
    rec_map = {("20260619", 1): _mock_rec(hit=True)}

    with patch(
        "src.predictor.upset_high_bet_gate._build_rec_map", return_value=rec_map
    ):
        st, settled = settle_pending_before_race(
            "20260619",
            2,
            state=st,
            schedule={"races": []},
            fetch_if_missing=False,
        )

    assert settled == [1]
    assert st.consecutive_misses == 0
    assert st.recent_bets[0].return_yen == 860


def test_settle_pending_skips_same_or_later_race():
    st = UpsetHighBetState()
    record_signaled_bet(st, "20260619", 3, 500)

    with patch("src.predictor.upset_high_bet_gate._build_rec_map", return_value={}):
        st, settled = settle_pending_before_race(
            "20260619",
            3,
            state=st,
            schedule={"races": []},
            fetch_if_missing=False,
        )

    assert settled == []
    assert len(st.pending_signals) == 1


def test_process_due_upset_high_settlements_at_t20():
    job = CaptureJob(
        race_id="202650061902",
        race_no=2,
        post_time="14:50",
        race_name="C3",
        minutes_before=UPSET_HIGH_SETTLE_OFFSET,
        label="t_minus_20",
    )
    schedule = {"races": [{"race_no": 2, "race_id": "202650061902", "post_time": "14:50"}]}
    updated = UpsetHighBetState(consecutive_misses=1)

    with patch(
        "src.scraper.race_snapshots.due_capture_jobs", return_value=[job]
    ):
        with patch(
            "src.predictor.upset_high_bet_gate.load_state",
            return_value=UpsetHighBetState(),
        ):
            with patch(
                "src.predictor.upset_high_bet_gate.settle_pending_before_race",
                return_value=(updated, [1]),
            ) as settle_mock:
                with patch("src.predictor.upset_high_bet_gate.save_state") as save_mock:
                    settled = process_due_upset_high_settlements(
                        "20260619",
                        schedule,
                        now=datetime(2026, 6, 19, 14, 30),
                    )

    assert settled == [1]
    settle_mock.assert_called_once()
    assert settle_mock.call_args[0] == ("20260619", 2)
    save_mock.assert_called_once()
