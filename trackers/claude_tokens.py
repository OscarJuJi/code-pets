"""Claude Code token usage read from local session logs (~/.claude/projects/**/*.jsonl).

No API calls: every assistant message line in those JSONL transcripts carries a
`message.usage` block. Tokens counted = input + output + cache_creation
(cache reads excluded — re-reading cached context is not new work).
"""

import glob
import json
import os
from datetime import date, datetime, timedelta

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
CACHE_KEEP_DAYS = 30


def scan(cache, projects_dir=PROJECTS_DIR, days=14, today=None):
    """Update per-file `cache` in place; return {"today": int, "series": [...]}.

    cache: {path: {"mtime": float, "size": int, "days": {iso_date: tokens}}}
    Only files whose mtime/size changed since the last scan are re-parsed.
    """
    today = today or date.today()
    paths = glob.glob(os.path.join(projects_dir, "**", "*.jsonl"), recursive=True)
    seen = set()
    for path in paths:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        seen.add(path)
        entry = cache.get(path)
        if entry and entry.get("mtime") == stat.st_mtime and entry.get("size") == stat.st_size:
            continue
        cache[path] = {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "days": _parse_file(path, today),
        }
    for path in list(cache):
        if path not in seen:
            del cache[path]

    totals = {}
    for entry in cache.values():
        for day, tokens in entry["days"].items():
            totals[day] = totals.get(day, 0) + tokens
    series = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        series.append({"date": day, "tokens": totals.get(day, 0)})
    return {"today": totals.get(today.isoformat(), 0), "series": series}


def _parse_file(path, today):
    """Sum tokens per local calendar day for one JSONL transcript."""
    days = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = record.get("message")
                usage = message.get("usage") if isinstance(message, dict) else None
                timestamp = record.get("timestamp")
                if not isinstance(usage, dict) or not timestamp:
                    continue
                tokens = (
                    usage.get("input_tokens", 0)
                    + usage.get("output_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                )
                try:
                    day = (
                        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        .astimezone()
                        .date()
                        .isoformat()
                    )
                except ValueError:
                    continue
                days[day] = days.get(day, 0) + tokens
    except OSError:
        return days
    cutoff = (today - timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    return {day: tokens for day, tokens in days.items() if day >= cutoff}
