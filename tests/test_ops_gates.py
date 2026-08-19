"""Unit tests for T-10 ops gates (Phase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.predictor.bets import RaceBetPlan
from src.predictor.ops_gates import (
    OpsGateConfig,
    annotate_message_with_notes,
    evaluate_buy_ops_gates,
    load_ops_gate_config,
    odds_std_from_scored,
)


def _plan(
    *,
    exotic_profile: str = "堅",
    is_volatile: bool = False,
    race_id: str = "202650070101",
    race_no: int = 1,
    tier: str = "S",
) -> RaceBetPlan:
    return RaceBetPlan(
        race_id=race_id,
        race_no=race_no,
        race_name="test",
        confidence="高",
        win_prob_top=0.9,
        prob_gap=0.8,
        marks=[],
        exotic_profile=exotic_profile,
        race_profile=exotic_profile,
        exotic_confidence="高",
        is_volatile=is_volatile,
        expectation_tier=tier,
    )


def test_load_ops_gate_config_defaults(tmp_path: Path, monkeypatch):
    path = tmp_path / "ops_gates.json"
    path.write_text(
        json.dumps(
            {
                "profile_flip_skip": True,
                "std_jump_skip": False,
                "std_jump_mode": "observe",
                "firm_volatile_mode": "observe",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPS_PROFILE_FLIP_SKIP", raising=False)
    monkeypatch.delenv("OPS_STD_JUMP_SKIP", raising=False)
    cfg = load_ops_gate_config(path)
    assert cfg.profile_flip_skip is True
    assert cfg.std_jump_skip is False
    assert cfg.std_jump_mode == "observe"


def test_env_overrides(tmp_path: Path, monkeypatch):
    path = tmp_path / "ops_gates.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPS_PROFILE_FLIP_SKIP", "0")
    monkeypatch.setenv("OPS_STD_JUMP_SKIP", "1")
    cfg = load_ops_gate_config(path)
    assert cfg.profile_flip_skip is False
    assert cfg.std_jump_skip is True
    assert cfg.std_jump_mode == "skip"


def test_profile_flip_skips(monkeypatch, tmp_path: Path):
    plan = _plan(exotic_profile="荒")
    master = pd.DataFrame({"date": [], "race_id": []})

    def fake_ref(date, race_id, label, master, **kwargs):
        assert label.startswith("t_minus_30")
        ref = _plan(exotic_profile="堅")
        return ref, 20.0

    monkeypatch.setattr(
        "src.predictor.ops_gates.build_plan_from_snapshot", fake_ref
    )
    cfg = OpsGateConfig(profile_flip_skip=True, std_jump_mode="off", firm_volatile_mode="off")
    # avoid writing into real snapshots during unit test
    monkeypatch.setattr(
        "src.predictor.ops_gates.ops_gate_decisions_path",
        lambda d: tmp_path / "dec.jsonl",
    )
    dec = evaluate_buy_ops_gates(
        "20260701", plan.race_id, plan, master, odds_std_t10=25.0, config=cfg
    )
    assert not dec.allow_buy
    assert any("profile_flip" in r for r in dec.skip_reasons)
    assert any(line.startswith("FLIP_SKIP") for line in dec.log_lines)


def test_profile_match_allows(monkeypatch, tmp_path: Path):
    plan = _plan(exotic_profile="堅")
    master = pd.DataFrame({"date": [], "race_id": []})

    def fake_ref(date, race_id, label, master, **kwargs):
        return _plan(exotic_profile="堅"), 10.0

    monkeypatch.setattr(
        "src.predictor.ops_gates.build_plan_from_snapshot", fake_ref
    )
    monkeypatch.setattr(
        "src.predictor.ops_gates.ops_gate_decisions_path",
        lambda d: tmp_path / "dec.jsonl",
    )
    cfg = OpsGateConfig(profile_flip_skip=True, std_jump_mode="off", firm_volatile_mode="off")
    dec = evaluate_buy_ops_gates(
        "20260701", plan.race_id, plan, master, odds_std_t10=12.0, config=cfg
    )
    assert dec.allow_buy
    assert not dec.skip_reasons


def test_no_t30_allows_by_default(monkeypatch, tmp_path: Path):
    plan = _plan(exotic_profile="堅")
    master = pd.DataFrame({"date": [], "race_id": []})
    monkeypatch.setattr(
        "src.predictor.ops_gates.build_plan_from_snapshot", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "src.predictor.ops_gates.ops_gate_decisions_path",
        lambda d: tmp_path / "dec.jsonl",
    )
    cfg = OpsGateConfig(require_t30_for_buy=False, firm_volatile_mode="off")
    dec = evaluate_buy_ops_gates(
        "20260701", plan.race_id, plan, master, config=cfg
    )
    assert dec.allow_buy
    assert any("FLIP_SKIP_N/A" in line for line in dec.log_lines)


def test_std_jump_watch_and_skip(monkeypatch, tmp_path: Path):
    plan = _plan(exotic_profile="堅")
    master = pd.DataFrame({"date": [], "race_id": []})

    def fake_ref(date, race_id, label, master, **kwargs):
        return _plan(exotic_profile="堅"), 10.0

    monkeypatch.setattr(
        "src.predictor.ops_gates.build_plan_from_snapshot", fake_ref
    )
    monkeypatch.setattr(
        "src.predictor.ops_gates.ops_gate_decisions_path",
        lambda d: tmp_path / "dec.jsonl",
    )
    cfg_watch = OpsGateConfig(
        profile_flip_skip=False,
        std_jump_skip=False,
        std_jump_mode="observe",
        std_jump_threshold=40.0,
        firm_volatile_mode="off",
    )
    dec_w = evaluate_buy_ops_gates(
        "20260701",
        plan.race_id,
        plan,
        master,
        odds_std_t10=55.0,
        config=cfg_watch,
    )
    assert dec_w.allow_buy
    assert any("STD_JUMP_WATCH" in line for line in dec_w.log_lines)

    cfg_skip = OpsGateConfig(
        profile_flip_skip=False,
        std_jump_skip=True,
        std_jump_mode="skip",
        std_jump_threshold=40.0,
        firm_volatile_mode="off",
    )
    dec_s = evaluate_buy_ops_gates(
        "20260701",
        plan.race_id,
        plan,
        master,
        odds_std_t10=55.0,
        config=cfg_skip,
    )
    assert not dec_s.allow_buy
    assert any("STD_JUMP_SKIP" in line for line in dec_s.log_lines)


def test_firm_volatile_observe_and_skip(monkeypatch, tmp_path: Path):
    plan = _plan(exotic_profile="堅", is_volatile=True)
    master = pd.DataFrame({"date": [], "race_id": []})
    monkeypatch.setattr(
        "src.predictor.ops_gates.build_plan_from_snapshot", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "src.predictor.ops_gates.ops_gate_decisions_path",
        lambda d: tmp_path / "dec.jsonl",
    )
    cfg_obs = OpsGateConfig(firm_volatile_mode="observe", profile_flip_skip=False)
    dec = evaluate_buy_ops_gates(
        "20260701", plan.race_id, plan, master, config=cfg_obs
    )
    assert dec.allow_buy
    assert any("堅" in n or "volatile" in n for n in dec.observe_notes)
    assert any("FIRM_VOL_WATCH" in line for line in dec.log_lines)

    cfg_skip = OpsGateConfig(firm_volatile_mode="skip", profile_flip_skip=False)
    dec2 = evaluate_buy_ops_gates(
        "20260701", plan.race_id, plan, master, config=cfg_skip
    )
    assert not dec2.allow_buy


def test_annotate_message():
    msg = annotate_message_with_notes("hello", ["【注意: 堅×volatile】"])
    assert "hello" in msg
    assert "volatile" in msg
    assert annotate_message_with_notes(None, ["x"]) is None


def test_odds_std_from_scored():
    df = pd.DataFrame({"odds": [2.0, 4.0, 6.0, 8.0]})
    assert odds_std_from_scored(df) > 0
    assert odds_std_from_scored(pd.DataFrame()) == 0.0
