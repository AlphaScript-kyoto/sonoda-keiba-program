"""Run fetch_daily for today, then compare snapshots vs final odds."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_EXE = BASE_DIR / ".venv" / "Scripts" / "python.exe"
FETCH_SCRIPT = BASE_DIR / "scripts" / "fetch_daily.py"
COMPARE_SCRIPT = BASE_DIR / "scripts" / "compare_odds_timing.py"

sys.path.append(str(BASE_DIR / "tools"))
from line_bot import send_line_message  # noqa: E402


def _notify(message: str) -> None:
    try:
        send_line_message(message)
    except Exception as exc:
        print(f"LINE skip: {exc}")


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
        _notify(f"園田競馬のデータ取得が完了しました ({today})")

        report = run_compare(today)
        if report:
            summary = _extract_summary(report)
            _notify(f"オッズタイミング比較 ({today})\n{summary}")
            print(f"\nReport: data/processed/snapshots/{today}/compare_report.txt")

    except subprocess.CalledProcessError as exc:
        error_message = (exc.stderr or exc.stdout or "").strip() or "詳細なエラーメッセージなし"
        _notify(f"【失敗】園田競馬データ取得エラー ({today})\n理由: {error_message}")
        print(f"エラーが発生しました: {error_message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
