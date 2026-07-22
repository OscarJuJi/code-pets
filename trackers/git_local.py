"""Local git activity: auto-discovered repos, today's commits, 14-day series."""

import os
import subprocess
from datetime import date, timedelta

GIT_TIMEOUT_SECONDS = 15


def normalize(path):
    """Canonical form used as the state key for a repo.

    On Windows the drive letter's case follows how the script was invoked, so
    the same repo could otherwise be stored under two keys and have its commits
    credited twice.
    """
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def discover_repos(root, extra=()):
    """Repos = root itself (if a repo) + direct children with .git + registered extras."""
    repos = []

    def add(path):
        path = normalize(path)
        if path not in repos and os.path.isdir(os.path.join(path, ".git")):
            repos.append(path)

    add(root)
    try:
        for name in sorted(os.listdir(root)):
            add(os.path.join(root, name))
    except OSError:
        pass
    for path in extra:
        add(path)
    return repos


def _git_log(repo, args):
    try:
        out = subprocess.run(
            ["git", "-C", repo, "log"] + args,
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.splitlines()


def commits_today(repo, today=None):
    """Return [(hash, subject), ...] for today's commits, or None if git failed."""
    today = today or date.today()
    since = today.isoformat() + " 00:00"
    lines = _git_log(repo, ["--since", since, "--pretty=format:%H|%s"])
    if lines is None:
        return None
    return [tuple(line.split("|", 1)) for line in lines if "|" in line]


def daily_counts(repo, days=14, today=None):
    """Return {iso_date: commit_count} for the last `days` days, or None."""
    today = today or date.today()
    since = (today - timedelta(days=days - 1)).isoformat() + " 00:00"
    lines = _git_log(repo, ["--since", since, "--date=short", "--pretty=format:%ad"])
    if lines is None:
        return None
    counts = {}
    for line in lines:
        line = line.strip()
        if line:
            counts[line] = counts.get(line, 0) + 1
    return counts


def scan(root, extra_repos=(), days=14):
    """Aggregate over all repos.

    Returns {
        "repos": [paths that answered],
        "today_by_repo": {repo: [(hash, subject), ...]},
        "today_count": total commits today,
        "series": [{"date": iso, "commits": n}, ...]  # oldest -> today
    }
    """
    today = date.today()
    repos_ok = []
    today_by_repo = {}
    totals = {}
    for repo in discover_repos(root, extra_repos):
        commits = commits_today(repo, today)
        if commits is None:
            continue
        repos_ok.append(repo)
        today_by_repo[repo] = commits
        counts = daily_counts(repo, days, today) or {}
        for day, n in counts.items():
            totals[day] = totals.get(day, 0) + n
    series = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        series.append({"date": day, "commits": totals.get(day, 0)})
    return {
        "repos": repos_ok,
        "today_by_repo": today_by_repo,
        "today_count": sum(len(c) for c in today_by_repo.values()),
        "series": series,
    }
