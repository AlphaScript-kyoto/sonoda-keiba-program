"""P6 payback notify tests."""

from datetime import datetime

import src.predictor.race_day_notify as mod
from src.predictor.p6_payback import P6PaybackEvaluation, build_p6_payback_message


def test_build_p6_payback_message_hit():
    evaluation = P6PaybackEvaluation(
        hit=True,
        return_yen=3280,
        investment=500,
        finish=("5", "1", "4"),
        race_class="C3",
    )
    msg = build_p6_payback_message(
        race_no=5,
        race_name="\u4e09\u89d2\u30a4\u30c3\u30c1",
        evaluation=evaluation,
    )
    assert msg.splitlines()[0] == "5R\u3000\u4e09\u89d2\u30a4\u30c3\u30c1\u3000C3"
    assert "\u7d50\u679c 5-1-4" in msg
    assert "\u6255\u3044\u623b\u3057\uff1a3,280\u5186" in msg
    assert "\u56de\u53ce\u7387\uff1a656\uff05" in msg
    assert "\u8cb7\u3044\u76ee" not in msg
    assert "P6" not in msg


def test_build_p6_payback_message_miss():
    evaluation = P6PaybackEvaluation(
        hit=False,
        return_yen=0,
        investment=500,
        finish=("1", "2", "3"),
        race_class="B2",
    )
    msg = build_p6_payback_message(race_no=3, race_name="", evaluation=evaluation)
    assert msg.splitlines()[0] == "3R\u3000B2"
    assert "\u56de\u53ce\u7387\uff1a0\uff05" in msg


def test_due_p6_payback_jobs(tmp_path, monkeypatch):
    date = "20260701"
    state_path = tmp_path / "p6_payback_state.json"
    filename = "p6_payback_state.json"

    monkeypatch.setattr(mod, "P6_PAYBACK_STATE_FILE", filename)
    import src.predictor.race_payback_notify as rpn

    monkeypatch.setattr(rpn, "_path", lambda _d, _f: state_path)

    mod.register_p6_payback_target(
        date,
        race_id="202650070104",
        race_no=4,
        race_name="test",
        post_time="12:10",
    )

    due = mod.due_p6_payback_jobs(date, now=datetime(2026, 7, 1, 12, 15, 0))
    assert len(due) == 1
    assert due[0]["race_no"] == 4


def test_p6_payback_sent_admin_only(tmp_path, monkeypatch):
    date = "20260703"
    state_path = tmp_path / "p6_payback_state.json"
    filename = "p6_payback_state.json"

    monkeypatch.setattr(mod, "P6_PAYBACK_STATE_FILE", filename)
    import src.predictor.race_payback_notify as rpn

    monkeypatch.setattr(rpn, "_path", lambda _d, _f: state_path)

    mod.register_p6_payback_target(
        date,
        race_id="202650070101",
        race_no=1,
        race_name="test",
        post_time="10:00",
    )

    evaluation = P6PaybackEvaluation(
        hit=False,
        return_yen=0,
        investment=500,
        finish=("1", "2", "3"),
        race_class="C3",
    )
    send_calls: list[str] = []

    class FakeResp:
        status_code = 200
        text = ""

    monkeypatch.setattr(
        "src.predictor.p6_payback.evaluate_p6_payback_for_race",
        lambda *_a, **_k: evaluation,
    )
    monkeypatch.setattr(
        "src.scraper.payback.fetch_paybacks",
        lambda *_a, **_k: {"202650070101": object()},
    )
    monkeypatch.setattr("src.predictor.score.load_master", lambda: None)

    def _capture(msg: str):
        send_calls.append(msg)
        return FakeResp()

    monkeypatch.setattr("tools.line_bot.send_line_message", _capture)

    settled = mod.process_due_p6_payback_notifications(
        date, now=datetime(2026, 7, 3, 10, 5, 0)
    )
    assert settled == [1]
    assert len(send_calls) == 1
    assert "\u6255\u3044\u623b\u3057" in send_calls[0]
    assert "\u8cb7\u3044\u76ee" not in send_calls[0]