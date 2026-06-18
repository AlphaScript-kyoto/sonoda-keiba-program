"""Print registered LINE team user IDs for .env."""



from __future__ import annotations



import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))



from tools.line_team_registry import (  # noqa: E402

    REGISTRY_PATH,

    export_team_ids_line,

    load_registry,

    team_user_ids,

)





def main() -> None:

    if hasattr(sys.stdout, "reconfigure"):

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")



    data = load_registry()

    users = data.get("users") or []

    active = team_user_ids()



    print(f"Registry: {REGISTRY_PATH}")

    print(f"Active users: {len(active)}")

    print()



    if not users:

        print("No users yet.")

        print("Start line_webhook_server.py + ngrok, then ask members to message the bot.")

        return



    for user in users:

        uid = user.get("user_id", "?")

        name = user.get("display_name") or "(name unknown)"

        seen = user.get("first_seen", "?")

        unfollowed = " [unfollowed]" if user.get("unfollowed") else ""

        print(f"  {uid}  {name}  first={seen}{unfollowed}")



    print()

    if active:

        print("Add to .env:")

        print(f"LINE_TEAM_USER_IDS={export_team_ids_line()}")

    else:

        print("No active user IDs to export.")





if __name__ == "__main__":

    main()

