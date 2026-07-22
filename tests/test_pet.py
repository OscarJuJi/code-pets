import os
from datetime import date

from core import pet
from core import state as state_mod


def make_state(**overrides):
    state = state_mod.default_state()
    state.update(overrides)
    return state


def test_stage_thresholds():
    assert pet.current_stage(0)[1] == "cachorro"
    assert pet.current_stage(49)[1] == "cachorro"
    assert pet.current_stage(50)[1] == "cría"
    assert pet.current_stage(1199)[1] == "veterano"
    assert pet.current_stage(1200)[1] == "leyenda"
    assert pet.next_stage(0) == (50, "cría")
    assert pet.next_stage(1200) is None


def test_streak_transitions():
    state = make_state()
    pet.register_activity(state, "test", 10, today="2026-07-01")
    assert state["streak"] == 1
    pet.register_activity(state, "test", 10, today="2026-07-01")  # gap 0
    assert state["streak"] == 1
    pet.register_activity(state, "test", 10, today="2026-07-02")  # gap 1
    assert state["streak"] == 2
    pet.register_activity(state, "test", 10, today="2026-07-05")  # gap > 1
    assert state["streak"] == 1
    assert state["xp"] == 40


def test_decay_charged_once_per_day():
    state = make_state(xp=100, last_active="2026-07-01")
    assert pet.apply_decay(state, today="2026-07-04") == 30  # 2 idle days past grace
    assert state["xp"] == 70
    assert pet.apply_decay(state, today="2026-07-04") == 0   # same day: nothing new
    assert state["xp"] == 70
    assert pet.apply_decay(state, today="2026-07-05") == 15  # one more idle day
    assert state["xp"] == 55


def test_decay_grace_day_and_xp_floor():
    state = make_state(xp=10, last_active="2026-07-01")
    assert pet.apply_decay(state, today="2026-07-02") == 0   # grace day
    assert pet.apply_decay(state, today="2026-07-10") == 10  # capped at current xp
    assert state["xp"] == 0


def test_decay_resets_after_new_activity():
    state = make_state(xp=100, last_active="2026-07-01")
    pet.apply_decay(state, today="2026-07-04")
    pet.register_activity(state, "test", 10, today="2026-07-04")
    assert pet.apply_decay(state, today="2026-07-05") == 0  # grace day again


def test_migration_v1_to_v2():
    raw = {
        "name": "Bit", "xp": 120, "last_active": "2026-07-10", "streak": 4,
        "log": [["2026-07-10", "commit", 10, ""]],
        "repos": ["C:/x"],
        "scanned_commits": {"C:/x": ["aaa", "bbb"]},
    }
    state = state_mod.migrate(raw)
    assert state["schema_version"] == 2
    assert state["name"] == "Bit"
    assert state["xp"] == 120
    assert state["scanned_commits"][os.path.normcase("C:/x")] == ["aaa", "bbb"]
    assert state["last_decay_date"] == date.today().isoformat()  # idle forgiven once
    assert state["daily_caps"]["date"] is None
    assert state["token_cache"] == {}


def test_case_variant_repo_keys_are_merged():
    raw = {
        "schema_version": 2,
        "scanned_commits": {
            "E:\\Workspace": ["aaa", "bbb"],
            "e:\\Workspace": ["bbb", "ccc"],
        },
    }
    state = state_mod.migrate(raw)
    assert len(state["scanned_commits"]) == 1
    hashes = next(iter(state["scanned_commits"].values()))
    assert sorted(hashes) == ["aaa", "bbb", "ccc"]  # union, no duplicates


def test_species_defaults_and_survives_migration():
    assert state_mod.default_state()["species"] == "rottweiler"
    # a v1 state predates species entirely and must still load
    migrated = state_mod.migrate({"name": "Bit", "xp": 10})
    assert migrated["species"] == "rottweiler"
    # an explicit choice is preserved
    assert state_mod.migrate({"schema_version": 2, "species": "blob"})["species"] == "blob"


def test_mood_keys():
    assert pet.mood(make_state())[0] == "waiting"
    happy = make_state(last_active="2026-07-19", streak=5)
    assert pet.mood(happy, today="2026-07-19")[0] == "happy"
    assert pet.mood(happy, today="2026-07-20")[0] == "bored"
    assert pet.mood(happy, today="2026-07-22")[0] == "sad"
    assert pet.mood(happy, today="2026-07-30")[0] == "hungry"
