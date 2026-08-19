"""T-10 buy ops gates (profile flip / std jump / firm×volatile).

Phase 1 of docs/OPS_GATE_SPEC_202607.md — does not change offline bet defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

import pandas as pd

from config.settings import DATA_PROCESSED_DIR, PROJECT_ROOT
from src.predictor.bets import DEFAULT_STRATEGY, RaceBetPlan, build_race_bet_plan
from src.predictor.score import score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.scraper.race_snapshots import LABEL_T_MINUS_10, label_for_offset, snapshot_path

OPS_GATES_CONFIG_PATH = PROJECT_ROOT / "config" / "ops_gates.json"
FIRM = "\u5805"
UPSET = "\u8352"
REF_SNAPSHOT_LABEL = label_for_offset(30)  # t_minus_30


@dataclass(frozen=True)
class OpsGateConfig:
    profile_flip_skip: bool = True
    std_jump_skip: bool = False
    std_jump_threshold: float = 40.0
    std_jump_mode: str = "observe"  # observe | skip | off
    firm_volatile_mode: str = "observe"  # observe | skip | off
    require_t30_for_buy: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "OpsGateConfig":
        return cls(
            profile_flip_skip=bool(data.get("profile_flip_skip", True)),
            std_jump_skip=bool(data.get("std_jump_skip", False)),
            std_jump_threshold=float(data.get("std_jump_threshold", 40.0)),
            std_jump_mode=str(data.get("std_jump_mode", "observe")).lower(),
            firm_volatile_mode=str(data.get("firm_volatile_mode", "observe")).lower(),
            require_t30_for_buy=bool(data.get("require_t30_for_buy", False)),
        )


@dataclass
class OpsGateDecision:
    allow_s_plus: bool = True
    allow_p6: bool = True
    skip_reasons: List[str] = field(default_factory=list)
    log_lines: List[str] = field(default_factory=list)
    observe_notes: List[str] = field(default_factory=list)
    t30_available: bool = False
    exotic_profile_t30: str = ""
    exotic_profile_t10: str = ""
    odds_std_t30: Optional[float] = None
    odds_std_t10: Optional[float] = None
    std_delta: Optional[float] = None

    @property
    def allow_buy(self) -> bool:
        """Any buy channel blocked when either is False (same rules for S+ and P6)."""
        return self.allow_s_plus and self.allow_p6


def _env_bool(name: str) -> Optional[bool]:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def load_ops_gate_config(
    path: Optional[Path] = None,
) -> OpsGateConfig:
    cfg_path = path or OPS_GATES_CONFIG_PATH
    data: dict = {}
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg = OpsGateConfig.from_dict(data)

    flip = _env_bool("OPS_PROFILE_FLIP_SKIP")
    if flip is not None:
        cfg = OpsGateConfig(
            profile_flip_skip=flip,
            std_jump_skip=cfg.std_jump_skip,
            std_jump_threshold=cfg.std_jump_threshold,
            std_jump_mode=cfg.std_jump_mode,
            firm_volatile_mode=cfg.firm_volatile_mode,
            require_t30_for_buy=cfg.require_t30_for_buy,
        )
    jump = _env_bool("OPS_STD_JUMP_SKIP")
    if jump is not None:
        cfg = OpsGateConfig(
            profile_flip_skip=cfg.profile_flip_skip,
            std_jump_skip=jump,
            std_jump_threshold=cfg.std_jump_threshold,
            std_jump_mode=("skip" if jump else cfg.std_jump_mode),
            firm_volatile_mode=cfg.firm_volatile_mode,
            require_t30_for_buy=cfg.require_t30_for_buy,
        )
    return cfg


def odds_std_from_scored(scored: Optional[pd.DataFrame]) -> float:
    if scored is None or scored.empty or "odds" not in scored.columns:
        return 0.0
    odds = pd.to_numeric(scored["odds"], errors="coerce").dropna()
    odds = odds[odds > 0]
    if len(odds) < 2:
        return 0.0
    return float(odds.std())


def odds_std_from_entries(entries: list) -> float:
    if not entries:
        return 0.0
    return odds_std_from_scored(pd.DataFrame(entries))


def _load_snapshot_dict(
    date_yyyymmdd: str, race_id: str, label: str
) -> Optional[dict]:
    path = snapshot_path(date_yyyymmdd, race_id, label)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_plan_from_snapshot(
    date_yyyymmdd: str,
    race_id: str,
    label: str,
    master: pd.DataFrame,
    *,
    win_cfg=None,
    ex_cfg=None,
) -> Optional[tuple[RaceBetPlan, float]]:
    """Score snapshot entries → plan + odds_std. None if snapshot missing."""
    snap = _load_snapshot_dict(date_yyyymmdd, race_id, label)
    if snap is None:
        return None
    entries = pd.DataFrame(snap.get("entries") or [])
    if entries.empty:
        return None
    if win_cfg is None or ex_cfg is None:
        win_cfg, ex_cfg = load_split_scoring_configs()
    hist = master[master["date"].astype(str) < str(date_yyyymmdd)]
    scored_win = score_entries(entries, hist, config=win_cfg)
    scored_ex = score_entries(entries, hist, config=ex_cfg)
    if scored_win.empty:
        return None
    plan = build_race_bet_plan(
        scored_win,
        exotic_race=scored_ex,
        strategy=DEFAULT_STRATEGY,
        master=hist,
        before_date=date_yyyymmdd,
    )
    return plan, odds_std_from_scored(scored_ex)


def evaluate_buy_ops_gates(
    date_yyyymmdd: str,
    race_id: str,
    plan_t10: Optional[RaceBetPlan],
    master: pd.DataFrame,
    *,
    odds_std_t10: Optional[float] = None,
    config: Optional[OpsGateConfig] = None,
) -> OpsGateDecision:
    """Decide whether S+ / P6 buy messages may be sent for this T-10 plan."""
    cfg = config or load_ops_gate_config()
    decision = OpsGateDecision()
    if plan_t10 is None:
        decision.allow_s_plus = False
        decision.allow_p6 = False
        decision.skip_reasons.append("no_plan")
        decision.log_lines.append("OPS_GATE skip no_plan")
        return decision

    decision.exotic_profile_t10 = str(plan_t10.exotic_profile or "")
    if odds_std_t10 is not None:
        decision.odds_std_t10 = float(odds_std_t10)
    else:
        # Prefer T-10 snapshot std if capture already wrote it
        snap10 = _load_snapshot_dict(date_yyyymmdd, race_id, LABEL_T_MINUS_10)
        if snap10 is not None:
            decision.odds_std_t10 = odds_std_from_entries(snap10.get("entries") or [])

    ref = build_plan_from_snapshot(
        date_yyyymmdd, race_id, REF_SNAPSHOT_LABEL, master
    )
    if ref is None:
        decision.t30_available = False
        decision.log_lines.append(
            f"FLIP_SKIP_N/A no_t30 race_id={race_id}"
        )
        if cfg.require_t30_for_buy:
            decision.allow_s_plus = False
            decision.allow_p6 = False
            decision.skip_reasons.append("require_t30")
            decision.log_lines.append(
                f"OPS_GATE skip require_t30 R{plan_t10.race_no} {race_id}"
            )
            _append_decision_jsonl(date_yyyymmdd, race_id, plan_t10, decision, cfg)
            return decision
    else:
        plan_t30, std_t30 = ref
        decision.t30_available = True
        decision.exotic_profile_t30 = str(plan_t30.exotic_profile or "")
        decision.odds_std_t30 = float(std_t30)

        # --- R1 profile flip ---
        if cfg.profile_flip_skip and decision.exotic_profile_t30 != decision.exotic_profile_t10:
            decision.allow_s_plus = False
            decision.allow_p6 = False
            reason = (
                f"profile_flip T30={decision.exotic_profile_t30} "
                f"T10={decision.exotic_profile_t10}"
            )
            decision.skip_reasons.append(reason)
            decision.log_lines.append(
                f"FLIP_SKIP race_id={race_id} "
                f"T30={decision.exotic_profile_t30} T10={decision.exotic_profile_t10}"
            )

        # --- R2 std jump ---
        if (
            decision.odds_std_t10 is not None
            and decision.odds_std_t30 is not None
            and cfg.std_jump_mode != "off"
        ):
            delta = abs(decision.odds_std_t10 - decision.odds_std_t30)
            decision.std_delta = delta
            if delta >= cfg.std_jump_threshold:
                do_skip = cfg.std_jump_skip or cfg.std_jump_mode == "skip"
                if do_skip:
                    decision.allow_s_plus = False
                    decision.allow_p6 = False
                    decision.skip_reasons.append(f"std_jump delta={delta:.1f}")
                    decision.log_lines.append(
                        f"STD_JUMP_SKIP delta={delta:.1f} thr={cfg.std_jump_threshold:g} "
                        f"race_id={race_id}"
                    )
                else:
                    decision.log_lines.append(
                        f"STD_JUMP_WATCH delta={delta:.1f} thr={cfg.std_jump_threshold:g} "
                        f"race_id={race_id}"
                    )

    # --- R3 firm x volatile ---
    if cfg.firm_volatile_mode != "off":
        firm_vol = (
            decision.exotic_profile_t10 == FIRM and bool(plan_t10.is_volatile)
        )
        if firm_vol:
            if cfg.firm_volatile_mode == "skip":
                decision.allow_s_plus = False
                decision.allow_p6 = False
                decision.skip_reasons.append("firm_volatile")
                decision.log_lines.append(
                    f"FIRM_VOL_SKIP race_id={race_id}"
                )
            else:
                note = "\u3010\u6ce8\u610f: \u5805\u00d7volatile\u3011"
                decision.observe_notes.append(note)
                decision.log_lines.append(
                    f"FIRM_VOL_WATCH race_id={race_id}"
                )

    if decision.allow_buy and not decision.skip_reasons:
        decision.log_lines.append(
            f"OPS_GATE ok R{plan_t10.race_no} {race_id} "
            f"ex={decision.exotic_profile_t10}"
        )

    _append_decision_jsonl(date_yyyymmdd, race_id, plan_t10, decision, cfg)
    return decision


def annotate_message_with_notes(text: Optional[str], notes: List[str]) -> Optional[str]:
    if not text:
        return text
    if not notes:
        return text
    return text.rstrip() + "\n" + "\n".join(notes)


def ops_gate_decisions_path(date_yyyymmdd: str) -> Path:
    return (
        DATA_PROCESSED_DIR
        / "snapshots"
        / str(date_yyyymmdd)
        / "ops_gate_decisions.jsonl"
    )


def _append_decision_jsonl(
    date_yyyymmdd: str,
    race_id: str,
    plan: RaceBetPlan,
    decision: OpsGateDecision,
    cfg: OpsGateConfig,
) -> None:
    path = ops_gate_decisions_path(date_yyyymmdd)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "date": date_yyyymmdd,
        "race_id": race_id,
        "race_no": int(plan.race_no),
        "allow_s_plus": decision.allow_s_plus,
        "allow_p6": decision.allow_p6,
        "skip_reasons": decision.skip_reasons,
        "exotic_profile_t10": decision.exotic_profile_t10,
        "exotic_profile_t30": decision.exotic_profile_t30,
        "t30_available": decision.t30_available,
        "odds_std_t10": decision.odds_std_t10,
        "odds_std_t30": decision.odds_std_t30,
        "std_delta": decision.std_delta,
        "is_volatile": bool(plan.is_volatile),
        "expectation_tier": plan.expectation_tier,
        "config": asdict(cfg),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
