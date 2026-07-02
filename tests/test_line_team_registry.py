"""Tests for LINE team user ID registry."""

import json

from tools.line_team_registry import (
    process_webhook_payload,
    record_user,
    team_user_ids,
    verify_line_signature,
)


def test_verify_line_signature():
    secret = "testsecret"
    body = b'{"events":[]}'
    import base64
    import hashlib
    import hmac

    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode()
    assert verify_line_signature(body, sig, secret)
    assert not verify_line_signature(body, "bad", secret)


def test_record_user_and_export(tmp_path, monkeypatch):
    import tools.line_team_registry as mod

    monkeypatch.setattr(mod, "REGISTRY_PATH", tmp_path / "line_team_registry.json")
    monkeypatch.setattr(mod, "fetch_display_name", lambda _uid: "TestUser")

    payload = {
        "events": [
            {
                "type": "message",
                "source": {"type": "user", "userId": "Utest123"},
                "message": {"type": "text", "text": "hello"},
            }
        ]
    }
    process_webhook_payload(payload)
    assert team_user_ids() == ["Utest123"]

    data = json.loads((tmp_path / "line_team_registry.json").read_text(encoding="utf-8"))
    assert data["users"][0]["display_name"] == "TestUser"
    assert data["users"][0]["message_count"] == 1

    record_user("Utest123", event_type="message", text="again", fetch_profile=False)
    data2 = json.loads((tmp_path / "line_team_registry.json").read_text(encoding="utf-8"))
    assert data2["users"][0]["message_count"] == 2


def test_send_line_team_messages_uses_push_per_member(monkeypatch):
    from unittest.mock import MagicMock

    import tools.line_bot as line_bot

    calls: list[tuple[str, str]] = []

    def fake_push(user_id: str, text: str):
        calls.append((user_id, text))
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"x-line-request-id": "team-req"}
        return resp

    monkeypatch.setattr(line_bot, "team_user_ids", lambda: ["Uteam1234"])
    monkeypatch.setattr(line_bot, "_post_line_push", fake_push)

    results = line_bot.send_line_team_messages("hello team")

    assert len(results) == 1
    assert results[0].channel == "team_push"
    assert results[0].user_id_suffix == "1234"
    assert calls == [("Uteam1234", "hello team")]


def test_send_line_predict_messages_team_and_admin_separate(monkeypatch):
    from unittest.mock import MagicMock

    import tools.line_bot as line_bot

    calls: list[str] = []

    def fake_push(user_id: str, text: str):
        calls.append(user_id)
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"x-line-request-id": f"req-{user_id}"}
        return resp

    monkeypatch.setenv("LINE_USER_ID", "Uadmin5678")
    monkeypatch.setattr(line_bot, "team_user_ids", lambda: ["Uteam1234"])
    monkeypatch.setattr(line_bot, "_post_line_push", fake_push)

    results = line_bot.send_line_predict_messages("predict body")

    assert len(results) == 2
    assert results[0].channel == "team_push"
    assert results[1].channel == "admin_push"
    assert calls == ["Uteam1234", "Uadmin5678"]


def test_send_line_predict_messages_skips_duplicate_admin_push(monkeypatch):
    from unittest.mock import MagicMock

    import tools.line_bot as line_bot

    monkeypatch.setenv("LINE_USER_ID", "Uadmin5678")
    monkeypatch.setattr(line_bot, "team_user_ids", lambda: ["Uadmin5678"])

    def fake_push(user_id: str, text: str):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"x-line-request-id": "team-req"}
        return resp

    monkeypatch.setattr(line_bot, "_post_line_push", fake_push)

    results = line_bot.send_line_predict_messages("predict body")

    assert len(results) == 1
    assert results[0].channel == "team_push"


def test_format_line_delivery_log():
    from tools.line_bot import LineSendResult, format_line_delivery_log

    rec = LineSendResult(
        channel="team_push",
        user_id_suffix="abcd",
        status_code=200,
        request_id="req-1",
        chunk="1/1",
    )
    line = format_line_delivery_log(rec)
    assert "team_push" in line
    assert "req-1" in line
    assert "...abcd" in line
