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


def main() -> None:
    today = datetime.now().strftime("%Y%m%d")
    log_run_today(today, "started")
    print(f"本日の日付 {today} でデータを取得します...")

    try:
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
        send_alert(
            f"\u30c7\u30fc\u30bf\u53d6\u5f97\u5b8c\u4e86 ({today})",
            date_yyyymmdd=today,
            alert_key=f"run_today_ok_{today}",
            cooldown_minutes=60 * 12,
            log_channel="run_today",
        )

        report = run_compare(today)
        if report:
            summary = _extract_summary(report)
            send_alert(
                f"\u30aa\u30c3\u30ba\u30bf\u30a4\u30df\u30f3\u30b0\u6bd4\u8f03 ({today})\n{summary}",
                date_yyyymmdd=today,
                alert_key=f"run_today_compare_{today}",
                cooldown_minutes=60 * 12,
                log_channel="run_today",
            )
            print(f"\nReport: data/processed/snapshots/{today}/compare_report.txt")

        from src.predictor.t10_daily_roi import (  # noqa: E402
            build_t10_daily_roi_report,
            format_t10_daily_roi_message,
        )
        from tools.line_bot import send_line_message  # noqa: E402

        roi_report = build_t10_daily_roi_report(today, fetch_payback=True)
        roi_msg = format_t10_daily_roi_message(roi_report)
        log_run_today(today, f"T-10 ROI report: {len(roi_report.races)} race(s)")
        print("\n=== T-10 ROI (S+) ===")
        print(roi_msg)
        send_line_message(roi_msg)

        from src.predictor.upset_high_bet_gate import (  # noqa: E402
            load_state,
            save_state,
            settle_pending_for_date,
        )

        gate_state = settle_pending_for_date(today)
        save_state(gate_state)
        log_run_today(today, "upset-high bet gate settled")

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
