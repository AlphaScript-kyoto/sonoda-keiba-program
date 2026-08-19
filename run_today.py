"""Run fetch_daily for today, then compare snapshots vs final odds."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_EXE = BASE_DIR / ".venv" / "Scripts" / "python.exe"
FETCH_SCRIPT = BASE_DIR / "scripts" / "fetch_daily.py"
COMPARE_SCRIPT = BASE_DIR / "scripts" / "compare_odds_timing.py"

sys.path.insert(0, str(BASE_DIR))
from src.predictor.automation_log import log_run_today, send_alert  # noqa: E402
from src.scraper.sonoda_history import find_next_sonoda_race_date_after  # noqa: E402


def _format_ja_month_day(date_yyyymmdd: str) -> str:
    return f"{int(date_yyyymmdd[4:6])}\u6708{int(date_yyyymmdd[6:8])}\u65e5"


def build_run_today_off_day_message(
    date_yyyymmdd: str,
    next_date_yyyymmdd: str | None,
) -> str:
    lines = [
        "\u3010\u591c\u9593\u51e6\u7406\u3011",
        (
            f"{_format_ja_month_day(date_yyyymmdd)}\u306f\u4f11\u5834\u306e\u305f\u3081\u3001"
            f"\u30c7\u30fc\u30bf\u53d6\u5f97\u30fb\u5b9f\u7e3e\u96c6\u8a08\u306f\u884c\u3044\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
        ),
    ]
    if next_date_yyyymmdd:
        lines.append(
            f"\u6b21\u56de\u958b\u50ac\u306f{_format_ja_month_day(next_date_yyyymmdd)}\u3067\u3059\u3002"
        )
    else:
        lines.append(
            "\u6b21\u56de\u958b\u50ac\u65e5\u306f\u73fe\u5728\u78ba\u5b9a\u3067\u304d\u3066\u304a\u308a\u307e\u305b\u3093\u3002"
        )
    return "\n".join(lines)


def _is_sonoda_race_day(date_yyyymmdd: str) -> bool:
    from src.scraper.race_list import list_race_ids_for_date

    return bool(list_race_ids_for_date(date_yyyymmdd))


def _handle_off_day(date_yyyymmdd: str) -> None:
    from src.predictor.off_day_notify import send_off_day_admin_alert

    next_date = find_next_sonoda_race_date_after(date_yyyymmdd)
    msg = build_run_today_off_day_message(date_yyyymmdd, next_date)
    log_run_today(date_yyyymmdd, "no Sonoda races; nightly skipped")
    print(msg)
    send_off_day_admin_alert(msg, date_yyyymmdd, next_date)


def _has_snapshots(date_yyyymmdd: str) -> bool:
    snap_dir = BASE_DIR / "data" / "processed" / "snapshots" / date_yyyymmdd
    if not snap_dir.is_dir():
        return False
    for path in snap_dir.glob("*.json"):
        if path.name == "schedule.json":
            continue
        if "_t_minus_" in path.name:
            return True
    return False


def _extract_summary(report_text: str) -> str:
    if "--- Summary ---" not in report_text:
        return report_text[:500]
    part = report_text.split("--- Summary ---", 1)[1].strip()
    lines = [ln for ln in part.splitlines() if ln.strip()][:8]
    return "\n".join(lines)


def _send_odds_compare_alert(date_yyyymmdd: str) -> None:
    """Send T-10 odds timing summary (race days with snapshots only)."""
    from src.predictor.score import load_master
    from src.predictor.snapshot_compare import compare_day, format_compare_summary_ja

    rows = compare_day(date_yyyymmdd, load_master(), label="t_minus_10")
    if not rows:
        log_run_today(date_yyyymmdd, "odds compare skipped (no T-10 snapshots)")
        return

    msg = format_compare_summary_ja(rows, date_yyyymmdd=date_yyyymmdd, label="t_minus_10")
    send_alert(
        msg,
        date_yyyymmdd=date_yyyymmdd,
        alert_key=f"run_today_compare_{date_yyyymmdd}",
        cooldown_minutes=60 * 12,
        log_channel="run_today",
    )


def run_compare(date_yyyymmdd: str) -> str:
    if not _has_snapshots(date_yyyymmdd):
        print(f"No snapshots for {date_yyyymmdd}; skip compare.")
        return ""

    report_path = (
        BASE_DIR / "data" / "processed" / "snapshots" / date_yyyymmdd / "compare_report.txt"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Timing compare: {date_yyyymmdd} ===")
    proc = subprocess.run(
        [
            str(PYTHON_EXE),
            str(COMPARE_SCRIPT),
            "--date",
            date_yyyymmdd,
            "--out",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(BASE_DIR),
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if report_path.is_file():
        return report_path.read_text(encoding="utf-8")
    return proc.stdout


def send_nightly_roi_reports(date_yyyymmdd: str, gate_state) -> None:
    """T-10 / 荒×High の夜間回収率LINE。払戻取得失敗時はキャッシュで続行。"""
    from src.predictor.t10_daily_roi import (  # noqa: E402
        build_t10_daily_roi_report,
        format_t10_daily_roi_message,
    )
    from src.predictor.upset_high_daily_roi import (  # noqa: E402
        build_upset_high_daily_roi_report,
        format_upset_high_daily_roi_message,
    )
    from tools.discord_bot import send_discord_message  # noqa: E402
    from tools.line_bot import (  # noqa: E402
        format_line_delivery_log,
        is_line_notify_paused,
        line_notify_pause_log_line,
        send_line_message,
        send_line_predict_messages,
    )

    try:
        roi_report = build_t10_daily_roi_report(date_yyyymmdd, fetch_payback=True)
    except Exception as exc:
        log_run_today(
            date_yyyymmdd,
            f"T-10 ROI fetch_payback failed ({exc}); retry cache-only",
        )
        roi_report = build_t10_daily_roi_report(date_yyyymmdd, fetch_payback=False)

    roi_msg = format_t10_daily_roi_message(roi_report)
    log_run_today(date_yyyymmdd, f"T-10 ROI report: {len(roi_report.races)} race(s)")
    print("\n=== T-10 ROI (S+) ===")
    print(roi_msg)
    if is_line_notify_paused():
        log_run_today(date_yyyymmdd, line_notify_pause_log_line("nightly_t10_roi"))
    else:
        roi_deliveries = send_line_predict_messages(roi_msg)
        for rec in roi_deliveries:
            log_run_today(date_yyyymmdd, format_line_delivery_log(rec))
        log_run_today(date_yyyymmdd, "T-10 ROI LINE sent (team + admin)")
    try:
        send_discord_message(roi_msg, category="nightly_t10_roi")
        log_run_today(date_yyyymmdd, "T-10 ROI Discord sent")
    except Exception as exc:
        log_run_today(date_yyyymmdd, f"WARN T-10 ROI Discord failed: {exc}")

    try:
        uh_report = build_upset_high_daily_roi_report(
            date_yyyymmdd,
            state=gate_state,
            fetch_payback=False,
        )
        uh_msg = format_upset_high_daily_roi_message(uh_report)
        log_run_today(date_yyyymmdd, f"P6 ROI report: {len(uh_report.bets)} bet(s)")
        print("\n=== P6 nightly ROI ===")
        print(uh_msg)
        if is_line_notify_paused():
            log_run_today(date_yyyymmdd, line_notify_pause_log_line("nightly_p6_roi"))
        else:
            send_line_message(uh_msg)
            log_run_today(date_yyyymmdd, "P6 nightly ROI LINE sent (admin)")
        try:
            send_discord_message(uh_msg, category="nightly_p6_roi")
            log_run_today(date_yyyymmdd, "P6 nightly ROI Discord sent")
        except Exception as exc:
            log_run_today(date_yyyymmdd, f"WARN P6 ROI Discord failed: {exc}")
    except Exception as exc:
        log_run_today(date_yyyymmdd, f"upset-high ROI FAILED: {exc}")
        send_alert(
            f"\u591c\u9593\u56de\u53ce\u7387\uff08\u8352\u00d7High\uff09\u306e\u914d\u4fe1\u306b\u5931\u6557 ({date_yyyymmdd})\n"
            f"\u7406\u7531: {exc}",
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"run_today_uh_roi_fail_{date_yyyymmdd}",
            cooldown_minutes=60,
            log_channel="run_today",
        )
        raise


def _validate_fetch_completeness(date_yyyymmdd: str) -> None:
    """schedule がある日は raw CSV のレース数を突合し、不足ならアラート。"""
    from src.scraper.race_snapshots import load_schedule
    from src.storage.csv_store import horses_csv_path, read_horses_csv

    schedule = load_schedule(date_yyyymmdd)
    if not schedule:
        return

    expected_ids = {
        str(r["race_id"])
        for r in schedule.get("races", [])
        if r.get("race_id")
    }
    if not expected_ids:
        return

    csv_path = horses_csv_path(date_yyyymmdd)
    if not csv_path.exists():
        msg = f"データ取得後も CSV がありません ({date_yyyymmdd})"
        log_run_today(date_yyyymmdd, msg)
        send_alert(
            msg,
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"run_today_fetch_incomplete_{date_yyyymmdd}",
            cooldown_minutes=60,
            log_channel="run_today",
        )
        return

    df = read_horses_csv(csv_path)
    got_ids = set(df["race_id"].astype(str).unique())

    missing = sorted(expected_ids - got_ids)
    if missing:
        msg = (
            f"\u30c7\u30fc\u30bf\u53d6\u5f97\u4e0d\u5341 ({date_yyyymmdd})\n"
            f"\u4e88\u5b9a {len(expected_ids)}R / \u53d6\u5f97 {len(got_ids)}R\n"
            f"\u672a\u53d6\u5f97: {', '.join(missing)}"
        )
        log_run_today(date_yyyymmdd, msg)
        send_alert(
            msg,
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"run_today_fetch_incomplete_{date_yyyymmdd}",
            cooldown_minutes=60,
            log_channel="run_today",
        )
    else:
        log_run_today(
            date_yyyymmdd,
            f"fetch completeness OK ({len(got_ids)}/{len(expected_ids)}R)",
        )


def main() -> None:
    today = datetime.now().strftime("%Y%m%d")
    log_run_today(today, "started")

    try:
        if not _is_sonoda_race_day(today):
            _handle_off_day(today)
            return

        print(f"\u672c\u65e5\u306e\u65e5\u4ed8 {today} \u3067\u30c7\u30fc\u30bf\u3092\u53d6\u5f97\u3057\u307e\u3059...")
        proc = subprocess.run(
            [str(PYTHON_EXE), str(FETCH_SCRIPT), "--date", today],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(BASE_DIR),
        )
        if proc.stdout:
            print(proc.stdout)
        log_run_today(today, "fetch_daily completed")
        _validate_fetch_completeness(today)
        send_alert(
            f"\u30c7\u30fc\u30bf\u53d6\u5f97\u5b8c\u4e86 ({today})",
            date_yyyymmdd=today,
            alert_key=f"run_today_ok_{today}",
            cooldown_minutes=60 * 12,
            log_channel="run_today",
        )

        from src.predictor.upset_high_bet_gate import (  # noqa: E402
            save_state,
            settle_pending_for_date,
        )

        gate_state = settle_pending_for_date(today)
        save_state(gate_state)
        log_run_today(today, "upset-high bet gate settled")

        report = run_compare(today)
        if report:
            print(f"\nReport: data/processed/snapshots/{today}/compare_report.txt")
        _send_odds_compare_alert(today)

        send_nightly_roi_reports(today, gate_state)

    except subprocess.CalledProcessError as exc:
        error_message = (exc.stderr or exc.stdout or "").strip() or "詳細なエラーメッセージなし"
        log_run_today(today, f"FAILED: {error_message}")
        send_alert(
            f"\u30c7\u30fc\u30bf\u53d6\u5f97\u5931\u6557 ({today})\n\u7406\u7531: {error_message}",
            date_yyyymmdd=today,
            alert_key=f"run_today_fail_{today}",
            cooldown_minutes=60,
            log_channel="run_today",
        )
        print(f"エラーが発生しました: {error_message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
