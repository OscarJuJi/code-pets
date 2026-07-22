"""Codepet 2.0 — local web dashboard.

Launch:  python codepet/app.py [--no-browser]
Opens http://127.0.0.1:8420 (first free port in 8420-8429).
"""

import json
import os
import socket
import sys
import threading
import time
import webbrowser
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)  # allow "python codepet/app.py" from anywhere

from flask import Flask, jsonify, render_template, request

from core import habits, pet
from core import state as state_mod
from trackers import claude_tokens, files, git_local, github_remote

WORKSPACE_ROOT = os.path.dirname(BASE_DIR)  # the folder this pet watches

XP_PER_FILE = 2
FILES_DAILY_CAP = 30
XP_PER_COMMIT = 8
GITHUB_DAILY_XP = 10
TOKENS_PER_XP = 10_000
TOKENS_DAILY_CAP = 25
# Seconds between automatic scans. Git matches the dashboard's own poll so a
# fresh commit shows up on the next refresh without touching "Escanear ahora".
TRACKER_INTERVALS = {"files": 180, "git": 60, "tokens": 180, "github": 600}
PORT_RANGE = range(8420, 8430)

# One folder per species under here, each holding <stage-slug>.png plus an
# optional anim/ folder of interaction GIFs. See web/static/sprites/README.md.
SPRITES_DIR = os.path.join(BASE_DIR, "web", "static", "sprites")
SPECIES_LABELS = {
    "rottweiler": "Rottweiler",
    "dog": "Perro robot",
    "blob": "Blob digital",
}
DEFAULT_SPECIES = "rottweiler"
TUNNEL_FILE = os.path.expanduser("~/.codepet-tunnel.json")  # written by tunnel.py

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "web", "templates"),
    static_folder=os.path.join(BASE_DIR, "web", "static"),
)

_lock = threading.Lock()
_last_run = {}   # tracker name -> time.monotonic() of last run
_cached = {}     # tracker name -> last result (shown even while throttled)


def _due(name, force):
    if force:
        return True
    last = _last_run.get(name)
    return last is None or (time.monotonic() - last) >= TRACKER_INTERVALS[name]


def _ensure_daily(state):
    today = date.today().isoformat()
    caps = state.get("daily_caps") or {}
    if caps.get("date") != today:
        state["daily_caps"] = {
            "date": today,
            "files_counted": [],
            "files_xp": 0,
            "tokens_xp": 0,
            "github_awarded": False,
        }


def _accumulate_daily(state, kind, xp_delta, detail):
    """One log entry per kind per day: bump it instead of spamming the feed."""
    today = date.today().isoformat()
    for entry in reversed(state["log"]):
        if entry[0] != today:
            break
        if entry[1] == kind:
            entry[2] += xp_delta
            entry[3] = detail
            state["xp"] += xp_delta
            state["last_active"] = today
            return
    pet.register_activity(state, kind, xp_delta, detail)


def refresh(force=False):
    """Run due trackers, attribute XP under daily caps, persist, build UI payload."""
    with _lock:
        state = state_mod.load_state()
        _ensure_daily(state)
        decay_lost = pet.apply_decay(state)
        caps = state["daily_caps"]

        if _due("files", force):
            result = files.scan(WORKSPACE_ROOT)
            _cached["files"] = result
            _last_run["files"] = time.monotonic()
            counted = set(caps["files_counted"])
            new = [f for f in result["files"] if f not in counted]
            budget = max(0, FILES_DAILY_CAP - caps["files_xp"])
            award = min(len(new) * XP_PER_FILE, budget)
            if award > 0:
                _accumulate_daily(
                    state, "files", award,
                    f"{len(caps['files_counted']) + len(new)} archivo(s) tocados hoy",
                )
                caps["files_xp"] += award
            caps["files_counted"] = (caps["files_counted"] + new)[-2000:]

        if _due("git", force):
            result = git_local.scan(WORKSPACE_ROOT, state["repos"])
            _cached["git"] = result
            _last_run["git"] = time.monotonic()
            for repo, commits in result["today_by_repo"].items():
                credited = state["scanned_commits"].get(repo, [])
                credited_set = set(credited)
                for commit_hash, subject in commits:
                    if commit_hash in credited_set:
                        continue
                    pet.register_activity(state, "git-commit", XP_PER_COMMIT, subject[:50])
                    credited.append(commit_hash)
                state["scanned_commits"][repo] = credited[-500:]

        if _due("tokens", force):
            result = claude_tokens.scan(state["token_cache"])
            _cached["tokens"] = result
            _last_run["tokens"] = time.monotonic()
            target = min(result["today"] // TOKENS_PER_XP, TOKENS_DAILY_CAP)
            delta = target - caps["tokens_xp"]
            if delta > 0:
                _accumulate_daily(
                    state, "claude-tokens", delta,
                    f"{result['today']:,} tokens con Claude hoy",
                )
                caps["tokens_xp"] = target

        if _due("github", force):
            result = github_remote.scan()
            _cached["github"] = result
            _last_run["github"] = time.monotonic()
            if result["contributed_today"] and not caps["github_awarded"]:
                pet.register_activity(
                    state, "github", GITHUB_DAILY_XP, "contribución en GitHub"
                )
                caps["github_awarded"] = True

        state["last_seen"] = date.today().isoformat()
        payload = _payload(state, decay_lost)
        state_mod.save_state(state)
    return payload


def sprite_url(stage_name, species):
    """URL of this stage's sprite for a species, or None to fall back to ASCII."""
    slug = pet.STAGE_SLUGS.get(stage_name)
    if not slug:
        return None
    if not os.path.exists(os.path.join(SPRITES_DIR, species, f"{slug}.png")):
        return None
    return f"/static/sprites/{species}/{slug}.png"


def animation_urls(species, stage_name=None):
    """Interaction GIFs for a species, narrowed to one stage when given.

    Files are named <stage-slug>_<action>.gif so each stage animates its own
    sprite; passing no stage answers whether the species has any at all.
    """
    anim_dir = os.path.join(SPRITES_DIR, species, "anim")
    try:
        names = sorted(f for f in os.listdir(anim_dir) if f.endswith(".gif"))
    except OSError:
        return []
    slug = pet.STAGE_SLUGS.get(stage_name) if stage_name else None
    if slug:
        names = [n for n in names if n.startswith(f"{slug}_")]
    return [f"/static/sprites/{species}/anim/{name}" for name in names]


def tunnel_url():
    """Public URL published by tunnel.py, if a tunnel is currently up."""
    try:
        with open(TUNNEL_FILE, encoding="utf-8") as f:
            return (json.load(f) or {}).get("url")
    except (OSError, json.JSONDecodeError):
        return None


def species_catalog():
    """Every species folder that ships at least one stage sprite."""
    catalog = []
    for key, label in SPECIES_LABELS.items():
        folder = os.path.join(SPRITES_DIR, key)
        has_sprites = os.path.isdir(folder) and any(
            f.endswith(".png") for f in os.listdir(folder)
        )
        catalog.append({
            "key": key,
            "label": label,
            "available": has_sprites,
            "animated": bool(animation_urls(key)),
        })
    return catalog


def _payload(state, decay_lost=0):
    species = state.get("species") or DEFAULT_SPECIES
    threshold, stage_name, art = pet.current_stage(state["xp"])
    upcoming = pet.next_stage(state["xp"])
    mood_key, mood_text = pet.mood(state)
    files_result = _cached.get("files") or {"files": [], "by_language": {}}
    git_result = _cached.get("git") or {"today_count": 0, "series": [], "repos": []}
    tokens_result = _cached.get("tokens") or {"today": 0, "series": []}
    github_result = _cached.get("github") or {
        "status": "offline", "contributed_today": False, "login": None,
    }
    next_stage = None
    if upcoming:
        span = upcoming[0] - threshold
        next_stage = {
            "name": upcoming[1],
            "xp_needed": upcoming[0] - state["xp"],
            "progress": round((state["xp"] - threshold) / span, 3) if span else 1.0,
        }
    return {
        "name": state["name"],
        "xp": state["xp"],
        "streak": state["streak"],
        "stage": stage_name,
        "art": art,
        "species": species,
        "species_options": species_catalog(),
        "sprite": sprite_url(stage_name, species),
        "animations": animation_urls(species, stage_name),
        "mood": {"key": mood_key, "text": mood_text},
        "next_stage": next_stage,
        "decay_lost": decay_lost,
        "today": {
            "tokens": tokens_result["today"],
            "commits": git_result["today_count"],
            "files": len(files_result["files"]),
            "github": {
                "status": github_result["status"],
                "contributed": github_result["contributed_today"],
            },
        },
        "series": {
            "tokens": tokens_result["series"],
            "commits": git_result["series"],
            "languages": files_result["by_language"],
        },
        "habits": [
            {"key": key, "xp": xp, "desc": desc}
            for key, (xp, desc) in habits.HABITS.items()
        ],
        "log": list(reversed(state["log"][-12:])),
        "repos_watched": len(git_result["repos"]),
        "tunnel": tunnel_url(),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(refresh(force=False))


@app.route("/api/scan", methods=["POST"])
def api_scan():
    return jsonify(refresh(force=True))


@app.route("/api/habit/<name>", methods=["POST"])
def api_habit(name):
    if name not in habits.HABITS:
        return jsonify({"error": f"hábito desconocido: {name}"}), 404
    with _lock:
        state = state_mod.load_state()
        _ensure_daily(state)
        xp, _desc = habits.HABITS[name]
        pet.register_activity(state, name, xp)
        state_mod.save_state(state)
        payload = _payload(state)
    return jsonify(payload)


@app.route("/api/species", methods=["POST"])
def api_species():
    key = ((request.get_json(silent=True) or {}).get("species") or "").strip()
    if key not in SPECIES_LABELS:
        return jsonify({"error": f"especie desconocida: {key}"}), 404
    with _lock:
        state = state_mod.load_state()
        state["species"] = key
        state_mod.save_state(state)
        payload = _payload(state)
    return jsonify(payload)


@app.route("/api/rename", methods=["POST"])
def api_rename():
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()[:30]
    if not name:
        return jsonify({"error": "nombre vacío"}), 400
    with _lock:
        state = state_mod.load_state()
        state["name"] = name
        state_mod.save_state(state)
        payload = _payload(state)
    return jsonify(payload)


def pick_port():
    for port in PORT_RANGE:
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit(
        f"Sin puerto libre en {PORT_RANGE.start}-{PORT_RANGE.stop - 1}."
    )


def main():
    port = pick_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Codepet vive en {url}  (Ctrl+C para dormir)")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
