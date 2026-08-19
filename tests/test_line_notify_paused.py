"""Tests for LINE_NOTIFY_PAUSED gate in line_bot."""

import tools.line_bot as line_bot


def test_is_line_notify_paused_truthy_values(monkeypatch):
    for value in ("1", "true", "yes", "on", "ON", " True "):
        monkeypatch.setenv("LINE_NOTIFY_PAUSED", value)
        assert line_bot.is_line_notify_paused() is True


def test_is_line_notify_paused_off(monkeypatch):
    for value in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("LINE_NOTIFY_PAUSED", value)
        assert line_bot.is_line_notify_paused() is False


def test_send_line_messages_skips_api_when_paused(monkeypatch):
    monkeypatch.setenv("LINE_NOTIFY_PAUSED", "1")

    def _boom(*_args, **_kwargs):
        raise AssertionError("LINE API must not be called when paused")

    monkeypatch.setattr(line_bot, "_post_line_push", _boom)
    resp = line_bot.send_line_messages("hello")
    assert resp.status_code == 200


def test_send_line_predict_messages_skips_api_when_paused(monkeypatch):
    monkeypatch.setenv("LINE_NOTIFY_PAUSED", "1")
    monkeypatch.delenv("LINE_TEAM_USER_IDS", raising=False)
    monkeypatch.delenv("LINE_USER_ID", raising=False)

    def _boom(*_args, **_kwargs):
        raise AssertionError("LINE API must not be called when paused")

    monkeypatch.setattr(line_bot, "_post_line_push", _boom)
    results = line_bot.send_line_predict_messages("predict body")
    assert len(results) == 1
    assert results[0].status_code == line_bot.PAUSED_STATUS_CODE
    assert "skipped" in line_bot.format_line_delivery_log(results[0])