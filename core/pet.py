"""Pet mechanics: XP, stages, mood, streak, and idle decay."""

from datetime import date

DECAY_PER_DAY = 15
GRACE_DAYS = 1
LOG_MAX_ENTRIES = 200

# (xp threshold, stage name shown in UI, ASCII art)
STAGES = [
    (0,    "cachorro",   ["  ^ ^  ", " (o.o) ", " > w < ", "  u u  "]),
    (50,   "cría",       ["  ^ ^  ", " (o.o) ", " (   ) ", "  \" \"  "]),
    (150,  "juvenil",    ["  ^_^  ", " (o o) ", "<(   )>", "  d b  "]),
    (350,  "adulto",     [" \\^o^/ ", " (O O) ", "<(   )>", " _/ \\_ "]),
    (700,  "veterano",   [" \\*O*/ ", " {O O} ", "<{###}>", " _/=\\_ "]),
    (1200, "leyenda",    ["\\\\*Ω*//", " {◉ ◉} ", "<{███}>", "_/===\\_"]),
]


# ASCII-safe slug per stage, used to look up sprite files on disk
STAGE_SLUGS = {
    "cachorro": "puppy",
    "cría": "hatchling",
    "juvenil": "juvenile",
    "adulto": "adult",
    "veterano": "veteran",
    "leyenda": "legend",
}


def current_stage(xp):
    stage = STAGES[0]
    for threshold, name, art in STAGES:
        if xp >= threshold:
            stage = (threshold, name, art)
    return stage


def next_stage(xp):
    for threshold, name, _ in STAGES:
        if xp < threshold:
            return threshold, name
    return None


def register_activity(state, kind, xp, detail="", today=None):
    """Add XP, update streak/last_active, and append a log entry."""
    today = today or date.today().isoformat()
    if state["last_active"]:
        gap = (date.fromisoformat(today) - date.fromisoformat(state["last_active"])).days
        if gap == 1:
            state["streak"] += 1
        elif gap > 1:
            state["streak"] = 1
    else:
        state["streak"] = 1
    state["last_active"] = today
    state["xp"] += xp
    state["log"].append([today, kind, xp, detail])
    state["log"] = state["log"][-LOG_MAX_ENTRIES:]


def apply_decay(state, today=None):
    """Charge idle decay for days not yet charged; return XP lost.

    Unlike v1 (which re-charged the whole idle period on every run),
    `last_decay_date` records how far decay has been settled, so repeated
    calls on the same day charge nothing extra.
    """
    today = date.fromisoformat(today) if today else date.today()
    if not state["last_active"]:
        return 0
    last_active = date.fromisoformat(state["last_active"])
    total_idle = (today - last_active).days - GRACE_DAYS
    if total_idle <= 0:
        return 0
    charged_idle = 0
    if state.get("last_decay_date"):
        prev = date.fromisoformat(state["last_decay_date"])
        if prev > last_active:
            charged_idle = max(0, (prev - last_active).days - GRACE_DAYS)
    new_idle = total_idle - charged_idle
    if new_idle <= 0:
        return 0
    lost = min(state["xp"], new_idle * DECAY_PER_DAY)
    state["xp"] -= lost
    state["last_decay_date"] = today.isoformat()
    return lost


def mood(state, today=None):
    """Return (css_key, spanish_text) describing how the pet feels."""
    today = date.fromisoformat(today) if today else date.today()
    if not state["last_active"]:
        return "waiting", "esperando nacer..."
    idle = (today - date.fromisoformat(state["last_active"])).days
    if idle == 0:
        if state["streak"] >= 3:
            return "happy", "feliz y con energía"
        return "content", "contento"
    if idle == 1:
        return "bored", "un poco aburrido"
    if idle <= 3:
        return "sad", "triste, te extraña"
    return "hungry", "hambriento de código..."
