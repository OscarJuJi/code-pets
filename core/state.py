"""State persistence: load/save ~/.codepet.json with v1 -> v2 migration."""

import json
import os
import shutil
from datetime import date

STATE_FILE = os.path.expanduser("~/.codepet.json")
SCHEMA_VERSION = 2


def default_state():
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "Bit",
        "species": "rottweiler",   # which sprite set the pet wears
        "xp": 0,
        "last_active": None,       # last ISO date with any XP-earning activity
        "last_seen": None,         # last time the app touched the state
        "last_decay_date": None,   # last ISO date idle decay was charged
        "streak": 0,
        "log": [],                 # entries: [iso_date, kind, xp, detail]
        "repos": [],               # manually registered repos (merged with discovered)
        "scanned_commits": {},     # repo path -> ordered list of credited hashes
        "daily_caps": {            # per-day XP attribution bookkeeping
            "date": None,
            "files_counted": [],
            "files_xp": 0,
            "tokens_xp": 0,
            "github_awarded": False,
        },
        "token_cache": {},         # jsonl path -> {"mtime", "size", "days": {date: tokens}}
    }


def load_state(path=STATE_FILE):
    if not os.path.exists(path):
        return default_state()
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        # keep the unreadable file around for inspection, start fresh
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass
        return default_state()
    return migrate(raw)


def canonical_repo_keys(scanned):
    """Merge repo keys that differ only by case (Windows drive letters).

    Two spellings of the same path would otherwise each hold their own credited
    hash list, so the same commits could be paid for twice.
    """
    merged = {}
    for repo, hashes in (scanned or {}).items():
        bucket = merged.setdefault(os.path.normcase(repo), [])
        for commit_hash in hashes:
            if commit_hash not in bucket:
                bucket.append(commit_hash)
    return merged


def migrate(raw):
    state = default_state()
    for key in state:
        if key in raw:
            state[key] = raw[key]
    if raw.get("schema_version", 1) < SCHEMA_VERSION:
        # v1 truncated a set() of hashes in arbitrary order; from now on the list
        # is kept in insertion order so trimming drops the oldest first
        state["scanned_commits"] = {
            repo: list(hashes)
            for repo, hashes in (raw.get("scanned_commits") or {}).items()
        }
        # v1 charged decay on every run, so pending idle days may already have
        # been charged several times; forgive them instead of double-charging
        state["last_decay_date"] = date.today().isoformat()
    state["scanned_commits"] = canonical_repo_keys(state["scanned_commits"])
    state["schema_version"] = SCHEMA_VERSION
    return state


def save_state(state, path=STATE_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
