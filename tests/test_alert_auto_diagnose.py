"""Tests for alert auto-diagnose gating and formatting."""

from src.predictor.alert_auto_diagnose import (
    format_local_diagnosis,
    should_auto_diagnose,
)


def test_should_auto_diagnose_heartbeat():
    assert should_auto_diagnose("heartbeat_stale_20260710_x", "心臓")
    assert should_auto_diagnose("watch_crash_20260710", "監視異常終了")
    assert not should_auto_diagnose("watch_done_20260710", "監視完了")


def test_format_local_diagnosis_includes_restart_hint():
    evidence = {
        "collected_at": "2026-07-12T10:00:00",
        "date": "20260712",
        "alert_key": "heartbeat_stale_20260712_x",
        "alert_message": "stale",
        "heartbeat": {"status": "started", "updated_at": "2026-07-12T09:00:00"},
        "watch_log_tail": "line1\nline2",
        "watch_processes": ["watch_race_day process: NOT FOUND"],
    }
    text = format_local_diagnosis(evidence)
    assert "自動診断" in text
    assert "再起動" in text
    assert "20260712" in text