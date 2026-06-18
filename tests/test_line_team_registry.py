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
