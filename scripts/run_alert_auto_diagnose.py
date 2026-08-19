"""Manual / scheduler helper: run alert auto-diagnose once."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.alert_auto_diagnose import run_auto_diagnose


def main() -> int:
    parser = argparse.ArgumentParser(description="Run watch alert auto-diagnose once")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--key", default="heartbeat_manual_test")
    parser.add_argument("--message", default="manual auto-diagnose")
    args = parser.parse_args()
    report = run_auto_diagnose(
        args.date,
        alert_key=args.key,
        alert_message=args.message,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())