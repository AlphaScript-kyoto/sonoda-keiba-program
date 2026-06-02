"""note 用のデータ根拠テキスト（脚質・ペース・血統・騎手など）。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.features.utils import parse_distance_m
from src.predictor.bets import RaceBetPlan
from src.predictor.marks_display import filter_race_df, normalize_umaban

STYLE_LABEL = {"逃": "逃げ", "先": "先行", "差": "差し", "追": "追込"}
FRONT_STYLES = frozenset({"逃げ", "先行"})
PACE_LABEL = {"H": "ハイペース", "S": "スローペース", "M": "平均ペース"}


def _num(val, default: float = float("nan")) -> float:
    v = pd.to_numeric(val, errors="coerce")
    return float(v) if pd.notna(v) else default


def _pct(val) -> str:
    v = _num(val)
    if np.isnan(v):
        return ""
    return f"{v:.0%}".replace("%", "％")


def _style_label(row: pd.Series) -> str:
    raw = row.get("entry_running_style", row.get("running_style", ""))
    s = str(raw).strip()
    if s in STYLE_LABEL:
        return STYLE_LABEL[s]
    if s in STYLE_LABEL.values():
        return s
    score = _num(row.get("horse_style_score"))
    if not np.isnan(score):
        if score >= 2.5:
            return "逃げ"
        if score >= 1.5:
            return "先行"
        if score >= 0.5:
            return "差し"
        if score > 0:
            return "追込"
    return ""


def _horse_label(umaban, horse_name: str) -> str:
    u = normalize_umaban(umaban)
    name = str(horse_name).strip() if horse_name else ""
    return f"{u}番{name}" if name else f"{u}番"


def _index_race_by_umaban(race_df: pd.DataFrame) -> dict[str, pd.Series]:
    if race_df.empty or "umaban" not in race_df.columns:
        return {}
    out: dict[str, pd.Series] = {}
    for _, row in race_df.iterrows():
        out[normalize_umaban(row["umaban"])] = row
    return out


def _pick_race_row(
    umaban: str,
    ex_by_u: dict[str, pd.Series],
    win_by_u: dict[str, pd.Series],
) -> Optional[pd.Series]:
    u = normalize_umaban(umaban)
    if u in ex_by_u:
        return ex_by_u[u]
    return win_by_u.get(u)


def _field_median(race_df: pd.DataFrame, col: str) -> float:
    if race_df.empty or col not in race_df.columns:
        return float("nan")
    s = pd.to_numeric(race_df[col], errors="coerce").dropna()
    return float(s.median()) if not s.empty else float("nan")


def build_race_flow_lines(race_df: pd.DataFrame) -> List[str]:
    """レース全体の展開・馬場・距離の短文。"""
    if race_df.empty:
        return []

    lines: List[str] = []
    front: List[str] = []
    for _, row in race_df.iterrows():
        style = _style_label(row)
        if style in FRONT_STYLES:
            front.append(_horse_label(row.get("umaban"), str(row.get("horse_name", ""))))

    if len(front) >= 2:
        joined = "、".join(front[:4])
        if len(front) > 4:
            joined += "ほか"
        lines.append(
            f"逃げ・先行が複数（{joined}）。前が抑え合いやすく、展開はハイペース寄りと見ています。"
        )
    elif len(front) == 1:
        lines.append(f"前を張れるのは{front[0]}中心。ペースはやや速めになりやすいです。")

    pace = str(race_df["race_pace"].iloc[0]).strip().upper() if "race_pace" in race_df.columns else ""
    if pace in PACE_LABEL:
        hint = "（過去の同レース傾向）" if pace in ("H", "S") else ""
        lines.append(f"参考ペース：{PACE_LABEL[pace]}{hint}。")

    dist = str(race_df["distance"].iloc[0]) if "distance" in race_df.columns else ""
    track = str(race_df["track"].iloc[0]).strip() if "track" in race_df.columns else ""
    weather = str(race_df["weather"].iloc[0]).strip() if "weather" in race_df.columns else ""
    parts = [p for p in [dist, f"馬場{track}" if track else "", f"天候{weather}" if weather else ""] if p]
    if parts:
        lines.append(" / ".join(parts) + "。")

    hc_col = race_df["entry_head_count"] if "entry_head_count" in race_df.columns else race_df.get("head_count")
    if hc_col is not None:
        n_s = pd.to_numeric(hc_col, errors="coerce").dropna()
        if not n_s.empty:
            n = int(n_s.iloc[0])
            if n >= 12:
                lines.append(f"頭数{n}頭で枠が割れるため、展開の読みは難しめです。")

    return lines


def _candidate_bullets(
    row: pd.Series,
    race_df: pd.DataFrame,
    *,
    mark: str,
    exotic_profile: str,
) -> List[Tuple[int, str]]:
    """(優先度, 文) の候補。大きいほど採用優先。"""
    cands: List[Tuple[int, str]] = []
    style = _style_label(row)
    dist_m = parse_distance_m(row.get("distance"))

    rank = _num(row.get("rank_pred"))
    if rank == 1 and mark == "◎":
        cands.append((95, "総合評価で本レースの軸（◎）に選んでいます。"))
    elif rank <= 2 and mark in ("○", "▲"):
        cands.append((70, f"総合評価{int(rank)}位で、{('相手筆頭' if mark == '○' else '3番手')}に入れています。"))

    psf = _num(row.get("pace_style_fit"))
    pace = str(row.get("race_pace", "")).strip().upper()
    if psf >= 0.12 and pace in PACE_LABEL:
        cands.append((55, f"想定の{PACE_LABEL[pace]}に脚質（{style or 'データ上の脚質'}）が合う。"))

    swsf = _num(row.get("sonoda_waku_style_fit"))
    waku = _num(row.get("entry_waku", row.get("waku")))
    if swsf >= 0.25:
        if dist_m == 1400 and waku >= 6 and style in FRONT_STYLES:
            cands.append((52, "園田1400mで外枠の先行が有利になりやすい条件に合う。"))
        elif swsf >= 0.35:
            cands.append((48, "枠順・脚質の組み合わせが園田コース向き。"))

    sfb = _num(row.get("sonoda_front_bonus"))
    if sfb >= 0.5 and style in FRONT_STYLES:
        cands.append((45, "園田は先行・逃げが伸びやすい傾向があり、この馬の脚質と合う。"))

    hwd = _num(row.get("horse_win_rate_distance"))
    med = _field_median(race_df, "horse_win_rate_distance")
    if hwd >= 0.18 and (np.isnan(med) or hwd >= med + 0.05):
        cands.append((42, f"この距離帯の勝率が高い（{_pct(hwd)}）。"))

    hwt = _num(row.get("horse_win_rate_track"))
    track = str(row.get("track", "")).strip()
    if hwt >= 0.15 and track:
        cands.append((40, f"馬場{track}での過去成績が良い（勝率{_pct(hwt)}）。"))

    stwr = _num(row.get("style_track_win_rate"))
    if stwr >= 0.2:
        cands.append((38, f"同条件の馬場・脚質での勝率が高い（{_pct(stwr)}）。"))

    jt_wr = _num(row.get("jockey_trainer_win_rate"))
    jt_roi = _num(row.get("jockey_trainer_roi"))
    jockey = str(row.get("jockey", "")).strip()
    trainer = str(row.get("trainer", "")).strip()
    if jt_wr >= 0.08 or jt_roi >= 0.2:
        who = f"{jockey}×{trainer}" if jockey and trainer else "騎手×調教師"
        stat = f"勝率{_pct(jt_wr)}" if jt_wr >= 0.08 else f"回収率{_pct(jt_roi)}"
        cands.append((36, f"{who}の組み合わせが好調（{stat}）。"))

    sire = str(row.get("sire", "")).strip()
    swr = _num(row.get("sire_win_rate"))
    if sire and sire.lower() != "nan" and swr >= 0.1:
        cands.append((34, f"父系{sire}がダート・小回りで実績（勝率{_pct(swr)}）。"))

    dswr = _num(row.get("dam_sire_win_rate"))
    dam = str(row.get("dam_sire", "")).strip()
    if dam and dam.lower() != "nan" and dswr >= 0.1:
        cands.append((30, f"母父{dam}系統も同条件で勝率{_pct(dswr)}。"))

    l3 = _num(row.get("last3_avg_finish"))
    if l3 <= 3.5:
        cands.append((28, f"近3走の平均着順が良い（{l3:.1f}着）。"))

    hwr = _num(row.get("horse_win_rate"))
    if hwr >= 0.2:
        cands.append((25, f"通算勝率{_pct(hwr)}で能力は上位グループ。"))

    if mark == "☆" and exotic_profile == "荒":
        cands.append((60, "波乱時に妙味があり、三連の押さえ・穴として拾っています。"))

    if style and style not in FRONT_STYLES and psf >= 0.1 and pace == "S":
        cands.append((33, "スローペース想定で差し・追込の伸びしろあり。"))

    return cands


def _market_tail(row: pd.Series, fav_u: str, mark: str) -> str:
    o = _num(row.get("odds"))
    pop = _num(row.get("popularity"))
    parts: List[str] = []
    if not np.isnan(o):
        parts.append(f"オッズ{o:.1f}倍")
    if not np.isnan(pop):
        parts.append(f"{int(pop)}番人気")
    u = normalize_umaban(row.get("umaban"))
    if mark == "◎" and fav_u:
        if u == fav_u:
            parts.append("市場も本命評価")
        else:
            parts.append("モデル評価は最上位だが市場1番人気は別")
    return "・".join(parts) if parts else ""


def build_mark_rationale_lines(
    mark: str,
    umaban: str,
    horse_name: str,
    row: Optional[pd.Series],
    race_df: pd.DataFrame,
    *,
    plan: RaceBetPlan,
    fav_u: str,
) -> List[str]:
    """1頭分の根拠行（先頭に印・馬名、続けて箇条書き）。"""
    name = horse_name or "（馬名）"
    header = f"{mark} {normalize_umaban(umaban)}. {name}"
    if row is None:
        role = {"◎": "本命", "○": "相手", "▲": "3番手", "△": "押さえ", "☆": "穴"}.get(mark, "")
        return [header, f"  ・{role}（詳細データ未取得）"]

    bullets: List[str] = []
    for _, text in sorted(
        _candidate_bullets(row, race_df, mark=mark, exotic_profile=plan.exotic_profile),
        key=lambda x: -x[0],
    ):
        if text not in bullets:
            bullets.append(text)
        if len(bullets) >= 3:
            break

    tail = _market_tail(row, fav_u, mark)
    if tail and len(bullets) < 4:
        bullets.append(tail)

    if not bullets:
        style = _style_label(row)
        if style:
            bullets.append(f"脚質は{style}。")
        bullets.append("過去データ・当日条件を総合して印に採用。")

    out = [header]
    out.extend(f"  ・{b}" for b in bullets)
    return out


def build_note_rationale_sections(
    plan: RaceBetPlan,
    win_df: pd.DataFrame,
    exotic_df: Optional[pd.DataFrame],
    marks: Sequence[Tuple[str, str, str]],
) -> Tuple[List[str], List[str]]:
    """
    Returns:
        (race_flow_lines, flat_mark_lines)
    """
    win_race = filter_race_df(win_df, plan.race_no)
    ex_race = filter_race_df(exotic_df, plan.race_no) if exotic_df is not None else pd.DataFrame()
    source = ex_race if not ex_race.empty else win_race
    ex_by_u = _index_race_by_umaban(ex_race)
    win_by_u = _index_race_by_umaban(win_race)

    flow = build_race_flow_lines(source if not source.empty else win_race)
    fav_u = ""
    if not win_race.empty and "popularity" in win_race.columns:
        pop = pd.to_numeric(win_race["popularity"], errors="coerce")
        valid = win_race.loc[pop.notna()]
        if not valid.empty:
            idx = pop.loc[valid.index].idxmin()
            fav_u = normalize_umaban(valid.loc[idx, "umaban"])

    mark_lines: List[str] = []
    for mark, umaban, horse_name in marks:
        row = _pick_race_row(umaban, ex_by_u, win_by_u)
        mark_lines.extend(
            build_mark_rationale_lines(
                mark, umaban, horse_name, row, source, plan=plan, fav_u=fav_u
            )
        )
        mark_lines.append("")

    if mark_lines and mark_lines[-1] == "":
        mark_lines.pop()

    return flow, mark_lines
