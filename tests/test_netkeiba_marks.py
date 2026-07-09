"""netkeiba mark link tests."""

from src.predictor.netkeiba_marks import (
    build_shutuba_url_with_marks,
    format_netkeiba_marks_block,
    marks_to_sonoda_param,
)


def test_marks_to_sonoda_param():
    marks = [
        ("\u25ce", "2", "A"),
        ("\u25cb", "8", "B"),
        ("\u25b2", "6", "C"),
        ("\u2606", "9", "D"),
    ]
    assert marks_to_sonoda_param(marks) == "2:1,8:2,6:3,9:5"


def test_build_shutuba_url_with_marks():
    url = build_shutuba_url_with_marks("202607070901", [("\u25ce", "2", "A")])
    assert "race_id=202607070901" in url
    assert "sonoda_marks=2:1" in url


def test_format_netkeiba_marks_block():
    class Plan:
        race_id = "202607070901"
        marks = [("\u25ce", "2", "A")]

    block = format_netkeiba_marks_block(Plan())
    assert "sonoda_marks=2:1" in block
    assert "Tampermonkey" not in block
    assert "[test]" not in block


def test_netkeiba_marks_link_enabled_default(monkeypatch):
    from src.predictor.race_day_notify import netkeiba_marks_link_enabled

    monkeypatch.delenv("NETKEIBA_MARKS_LINK_ENABLED", raising=False)
    assert netkeiba_marks_link_enabled() is True


def test_netkeiba_marks_link_enabled_can_disable(monkeypatch):
    from src.predictor.race_day_notify import netkeiba_marks_link_enabled

    monkeypatch.setenv("NETKEIBA_MARKS_LINK_ENABLED", "0")
    assert netkeiba_marks_link_enabled() is False
