"""Remote GitHub contribution check via the authenticated `gh` CLI.

Any failure (gh missing, no auth, no network) degrades to status "offline";
the rest of the app keeps working.
"""

import json
import subprocess
from datetime import date, datetime

GH_TIMEOUT_SECONDS = 10
CONTRIBUTION_EVENTS = {
    "PushEvent", "PullRequestEvent", "IssuesEvent", "CreateEvent",
    "PullRequestReviewEvent", "ReleaseEvent",
}


def scan(today=None):
    """Return {"status": "ok"|"offline", "contributed_today": bool, "login": str|None}."""
    today = today or date.today()
    login = _gh(["api", "user", "--jq", ".login"])
    if not login:
        return {"status": "offline", "contributed_today": False, "login": None}
    login = login.strip()
    out = _gh(["api", f"users/{login}/events?per_page=100"])
    if out is None:
        return {"status": "offline", "contributed_today": False, "login": login}
    try:
        events = json.loads(out)
    except json.JSONDecodeError:
        return {"status": "offline", "contributed_today": False, "login": login}
    contributed = False
    for event in events:
        if event.get("type") not in CONTRIBUTION_EVENTS:
            continue
        created = event.get("created_at", "")
        try:
            local_day = (
                datetime.fromisoformat(created.replace("Z", "+00:00"))
                .astimezone()
                .date()
            )
        except ValueError:
            continue
        if local_day == today:
            contributed = True
            break
    return {"status": "ok", "contributed_today": contributed, "login": login}


def _gh(args):
    try:
        out = subprocess.run(
            ["gh"] + args, capture_output=True, text=True,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout
