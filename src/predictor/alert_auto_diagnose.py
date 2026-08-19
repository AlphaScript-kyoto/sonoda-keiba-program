"""Auto-diagnose watch/heartbeat alerts and report to Discord.

Default: local evidence collection (heartbeat, log tail, process scan).
Optional: Cursor local Agent when CURSOR_API_KEY + ALERT_CURSOR_AGENT=1.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.automation_log import (
    heartbeat_path,
    load_heartbeat,
    log_watch,
    watch_log_path,
)

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_DIAGNOSE_KEY_RES = (
    re.compile(r"heartbeat", re.I),
    re.compile(r"watch_crash", re.I),
    re.compile(r"watch_script_crash", re.I),
    re.compile(r"netkeiba_block", re.I),
)


def alert_auto_diagnose_enabled() -> bool:
    raw = os.getenv("ALERT_AUTO_DIAGNOSE", "1").strip().lower()
    return raw in _TRUTHY


def alert_cursor_agent_enabled() -> bool:
    raw = os.getenv("ALERT_CURSOR_AGENT", "0").strip().lower()
    return raw in _TRUTHY and bool(os.getenv("CURSOR_API_KEY", "").strip())


def should_auto_diagnose(alert_key: Optional[str], message: str) -> bool:
    blob = f"{alert_key or ''}\n{message}"
    return any(rx.search(blob) for rx in _DIAGNOSE_KEY_RES)


def _tail_text(path: Path, max_lines: int = 40) -> str:
    if not path.exists():
        return f"(missing) {path}"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"(read failed) {path}: {exc}"
    if not lines:
        return f"(empty) {path}"
    return "\n".join(lines[-max_lines:])


def _watch_process_lines() -> list[str]:
    """Best-effort Windows process scan for watch_race_day."""
    if sys.platform != "win32":
        return ["(process scan skipped: non-Windows)"]
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe' "
                    "OR Name='pythonw.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'watch_race_day' } | "
                    "Select-Object ProcessId, CommandLine | "
                    "ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"(process scan failed: {exc})"]
    raw = (proc.stdout or "").strip()
    if not raw:
        return ["watch_race_day process: NOT FOUND"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [raw[:500]]
    if isinstance(data, dict):
        data = [data]
    out: list[str] = []
    for row in data:
        pid = row.get("ProcessId", "?")
        cmd = str(row.get("CommandLine", ""))[:180]
        out.append(f"pid={pid} {cmd}")
    return out or ["watch_race_day process: NOT FOUND"]


def collect_local_evidence(
    date_yyyymmdd: str,
    *,
    alert_key: Optional[str] = None,
    alert_message: str = "",
) -> dict[str, Any]:
    hb = load_heartbeat(date_yyyymmdd)
    log_path = watch_log_path(date_yyyymmdd)
    return {
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "date": date_yyyymmdd,
        "alert_key": alert_key,
        "alert_message": alert_message[:500],
        "heartbeat_path": str(heartbeat_path(date_yyyymmdd)),
        "heartbeat": hb,
        "watch_log_path": str(log_path),
        "watch_log_tail": _tail_text(log_path, 40),
        "watch_processes": _watch_process_lines(),
    }


def format_local_diagnosis(evidence: dict[str, Any]) -> str:
    hb = evidence.get("heartbeat") or {}
    procs = evidence.get("watch_processes") or []
    lines = [
        "【自動診断】監視アラートの現地確認",
        f"日時: {evidence.get('collected_at')}",
        f"日付: {evidence.get('date')}",
        f"alert_key: {evidence.get('alert_key') or '-'}",
        "",
        "■ ハートビート",
    ]
    if not hb:
        lines.append("  (ファイルなし / 読めない)")
    else:
        lines.append(f"  status={hb.get('status')}")
        lines.append(f"  updated_at={hb.get('updated_at')}")
        if hb.get("next_wake_at"):
            lines.append(f"  next_wake_at={hb.get('next_wake_at')}")
        if hb.get("error"):
            lines.append(f"  error={hb.get('error')}")

    lines.extend(["", "■ watch プロセス"])
    for row in procs:
        lines.append(f"  {row}")

    lines.extend(["", "■ watch ログ末尾"])
    tail = str(evidence.get("watch_log_tail") or "")
    for ln in tail.splitlines()[-15:]:
        lines.append(f"  {ln}")

    status = str((hb or {}).get("status", ""))
    proc_blob = "\n".join(str(x) for x in procs)
    lines.extend(["", "■ 推定"])
    if "NOT FOUND" in proc_blob and status in {"started", "running", "sleeping", "error"}:
        lines.append("  watch プロセスが見つかりません。再起動が必要です。")
        lines.append(
            f"  例: python scripts/watch_race_day.py --date {evidence.get('date')}"
        )
    elif status == "started" and "NOT FOUND" in proc_blob:
        lines.append("  開始直後に落ちた可能性（LINE 429 等）。")
    elif status == "done":
        lines.append("  監視は完了 status=done。心拍アラートは誤検知の可能性。")
    elif "NOT FOUND" not in proc_blob:
        lines.append("  プロセスは生きています。ログ末尾を優先確認してください。")
    else:
        lines.append("  詳細はログ末尾を確認してください。")

    return "\n".join(lines)


def _run_cursor_agent(evidence: dict[str, Any]) -> str:
    """Optional local Cursor Agent summary. Returns text or empty on skip/fail."""
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except ImportError:
        return "(Cursor SDK 未インストール: pip install cursor-sdk)"

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    model = os.getenv("CURSOR_AGENT_MODEL", "composer-2.5").strip() or "composer-2.5"
    prompt = (
        "あなたは園田競馬監視の障害一次対応です。以下の現地エビデンスだけを使って、"
        "原因候補を2〜4個、今すぐやる操作を日本語で短くまとめてください。"
        "コード変更や破壊的コマンドは提案しないでください。再起動コマンド例は可。\n\n"
        f"```json\n{json.dumps(evidence, ensure_ascii=False, indent=2)[:12000]}\n```"
    )
    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=str(ROOT)),
            ),
        )
        status = getattr(result, "status", None)
        text = getattr(result, "result", None) or getattr(result, "text", None) or ""
        if status and str(status) == "error":
            return f"(Cursor Agent run error: {status})"
        return str(text).strip() or "(Cursor Agent: empty result)"
    except Exception as exc:
        return f"(Cursor Agent failed: {exc})"


def _post_discord(text: str) -> None:
    from tools.discord_bot import send_discord_message

    send_discord_message(text, category="watch_alert")


def run_auto_diagnose(
    date_yyyymmdd: str,
    *,
    alert_key: Optional[str] = None,
    alert_message: str = "",
) -> str:
    evidence = collect_local_evidence(
        date_yyyymmdd,
        alert_key=alert_key,
        alert_message=alert_message,
    )
    report = format_local_diagnosis(evidence)
    if alert_cursor_agent_enabled():
        agent_text = _run_cursor_agent(evidence)
        report = (
            report
            + "\n\n■ Cursor Agent 所見\n"
            + "\n".join(f"  {ln}" for ln in agent_text.splitlines()[:40])
        )
    try:
        _post_discord(report)
    except Exception as exc:
        log_watch(date_yyyymmdd, f"WARN auto-diagnose Discord failed: {exc}")
    log_watch(date_yyyymmdd, "auto-diagnose report sent")
    return report


def schedule_auto_diagnose(
    date_yyyymmdd: str,
    *,
    alert_key: Optional[str] = None,
    alert_message: str = "",
) -> None:
    """Fire-and-forget background diagnose (does not block alert send)."""
    if not alert_auto_diagnose_enabled():
        return
    if not should_auto_diagnose(alert_key, alert_message):
        return
    if not date_yyyymmdd:
        return

    def _worker():
        try:
            run_auto_diagnose(
                date_yyyymmdd,
                alert_key=alert_key,
                alert_message=alert_message,
            )
        except Exception as exc:
            try:
                log_watch(date_yyyymmdd, f"WARN auto-diagnose failed: {exc}")
            except Exception:
                pass

    threading.Thread(target=_worker, name="alert-auto-diagnose", daemon=True).start()
