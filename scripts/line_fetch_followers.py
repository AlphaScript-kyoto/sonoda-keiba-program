"""Import follower user IDs from LINE API (no webhook required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.line_team_registry import fetch_followers_from_api  # noqa: E402


def main() -> None:
    try:
        ids = fetch_followers_from_api()
    except Exception as exc:
        print(f"Failed: {exc}")
        print("If API is unavailable, use line_webhook_server.py instead.")
        sys.exit(1)

    print(f"Imported {len(ids)} follower(s).")
    print("Run: python scripts/line_export_team_ids.py")


if __name__ == "__main__":
    main()
