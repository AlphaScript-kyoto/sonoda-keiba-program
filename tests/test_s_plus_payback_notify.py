from __future__ import annotations

from datetime import datetime

import src.predictor.race_day_notify as mod
from src.predictor.t10_daily_roi import SPlusPaybackEvaluation


def test_build_s_plus_payback_message_miss_when_race_has_payout():
    evaluation = SPlusPaybackEvaluation(
        hit=False,
        return_yen=0,
        finish=("1", "2", "3"),
        buy_line="5-1,4,3,2,6",
    )
    msg = mod.build_s_plus_payback_message(
        "20260703",
        race_no=1,
        race_name="",
        evaluation=evaluation,
    )
    assert "的中" not in msg
    assert "払戻 0円" in msg
    assert "結果 1-2-3" in msg
    assert "買い目 5-1,4,3,2,6" in msg


def test_build_s_plus_payback_message_hit():
    evaluation = SPlusPaybackEvaluation(
        hit=True,
        return_yen=3280,
        finish=("5", "1", "4"),
        buy_line="5-1,4,3,2,6",
    )
    msg = mod.build_s_plus_payback_message(
        "20260703",
        race_no=1,
        race_name="",
        evaluation=evaluation,
    )
    assert "【期待値S+ 三連複結果 的中】" in msg
    assert "払戻 3,280円" in msg


def test_due_s_plus_payback_jobs_and_next_wake(tmp_path, monkeypatch):
    date = "20260701"
    state_path = tmp_path / "s_plus_payback_state.json"
    monkeypatch.setattr(mod, "s_plus_payback_state_path", lambda _d: state_path)

    mod.register_s_plus_payback_target(
        date,
        race_id="202650070104",
        race_no=4,
        race_name="test",
        post_time="12:10",
    )

    due_early = mod.due_s_plus_payback_jobs(
        date,
        now=datetime(2026, 7, 1, 12, 14, 59),
    )
    assert due_early == []

    due = mod.due_s_plus_payback_jobs(
        date,
        now=datetime(2026, 7, 1, 12, 15, 0),
    )
    assert len(due) == 1
    assert due[0]["race_no"] == 4

    state = mod.load_s_plus_payback_state(date)
    state["races"][0]["last_checked_at"] = "2026-07-01T12:15:00"
    mod.save_s_plus_payback_state(date, state)
    due_too_soon = mod.due_s_plus_payback_jobs(
        date,
        now=datetime(2026, 7, 1, 12, 19, 59),
    )
    assert due_too_soon == []
    due_next = mod.due_s_plus_payback_jobs(
        date,
        now=datetime(2026, 7, 1, 12, 20, 0),
    )
    assert len(due_next) == 1

    wake = mod.next_s_plus_payback_wake(
        date,
        now=datetime(2026, 7, 1, 12, 16, 0),
    )
    assert wake is not None
    assert wake.strftime("%H:%M:%S") == "12:20:00"


def test_s_plus_payback_sent_only_once(tmp_path, monkeypatch):
    date = "20260703"
    state_path = tmp_path / "s_plus_payback_state.json"
    monkeypatch.setattr(mod, "s_plus_payback_state_path", lambda _d: state_path)

    mod.register_s_plus_payback_target(
        date,
        race_id="202650070101",
        race_no=1,
        race_name="test",
        post_time="10:00",
    )

    evaluation = SPlusPaybackEvaluation(
        hit=False,
        return_yen=0,
        finish=("1", "2", "3"),
        buy_line="5-1,4,3,2,6",
    )
    fake_pb = object()
    send_calls: list[str] = []

    monkeypatch.setattr(
        "src.predictor.t10_daily_roi.evaluate_s_plus_payback_for_race",
        lambda *_a, **_k: evaluation,
    )
    monkeypatch.setattr(
        "src.scraper.payback.fetch_paybacks",
        lambda *_a, **_k: {"202650070101": fake_pb},
    )
    monkeypatch.setattr(
        "src.predictor.score.load_master",
        lambda: None,
    )

    def _capture_send(msg: str):
        send_calls.append(msg)
        from tools.line_bot import LineSendResult

        return [
            LineSendResult(
                channel="team_push",
                user_id_suffix="1234",
                status_code=200,
                request_id="req",
                chunk="1/1",
            )
        ]

    monkeypatch.setattr("tools.line_bot.team_user_ids", lambda: ["Uteam1234"])
    monkeypatch.setattr(
        "tools.line_bot.send_line_team_messages",
        _capture_send,
    )

    t1 = datetime(2026, 7, 3, 10, 5, 0)
    settled = mod.process_due_s_plus_payback_notifications(date, now=t1)
    assert settled == [1]
    assert len(send_calls) == 1

    state = mod.load_s_plus_payback_state(date)
    assert state["races"][0]["status"] == "done"

    t2 = datetime(2026, 7, 3, 10, 10, 0)
    settled_again = mod.process_due_s_plus_payback_notifications(date, now=t2)
    assert settled_again == []
    assert len(send_calls) == 1


def test_sync_payback_post_times_from_schedule(tmp_path, monkeypatch):
    date = "20260703"
    state_path = tmp_path / "s_plus_payback_state.json"
    monkeypatch.setattr(mod, "s_plus_payback_state_path", lambda _d: state_path)

    mod.register_s_plus_payback_target(
        date,
        race_id="202650070307",
        race_no=7,
        race_name="C1",
        post_time="17:20",
    )
    schedule = {
        "races": [
            {
                "race_id": "202650070307",
                "race_no": 7,
                "post_time": "17:30",
                "race_name": "C1",
            }
        ]
    }
    mod.sync_payback_post_times_from_schedule(date, schedule)
    state = mod.load_s_plus_payback_state(date)
    assert state["races"][0]["post_time"] == "17:30"
