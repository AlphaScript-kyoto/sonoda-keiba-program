"""Tests for T-10 clipboard helper."""

import tools.clipboard_util as clip


def test_t10_clipboard_enabled_default(monkeypatch):
    monkeypatch.delenv("T10_CLIPBOARD", raising=False)
    assert clip.t10_clipboard_enabled() is True


def test_t10_clipboard_disabled(monkeypatch):
    monkeypatch.setenv("T10_CLIPBOARD", "0")
    assert clip.t10_clipboard_enabled() is False


def test_copy_to_clipboard_windows(monkeypatch):
    monkeypatch.setattr(clip.sys, "platform", "win32")
    calls: list[bytes] = []

    def fake_run(argv, input, check, timeout):
        calls.append(input)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(clip.subprocess, "run", fake_run)
    assert clip.copy_to_clipboard("hello\nworld") is True
    assert calls[0] == "hello\nworld".encode("utf-16le")


def test_copy_to_clipboard_empty():
    assert clip.copy_to_clipboard("") is False
    assert clip.copy_to_clipboard("   ") is False