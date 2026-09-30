"""Fetching a match from the Deadlock API fills the Add Match form, and saving it links accounts.

Two halves. `to_match` has to turn the API's payload into exactly what we used to type off the
post-game scoreboard - checked here against match 101331625, which was logged by hand before the
importer existed. And the form has to come up holding the import, leave the one account we have
never seen empty rather than guessing, and remember that account once someone fills it in.

The payload is a trimmed copy of the real response in tests/fixtures, so this needs no network.

Run with `python tests/test_import.py`.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "pages", "8_Add_Match.py")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "match_101331625.json")
LOGGED_ID = "101331625"
NEW_ID = "999999999"  # the fixture again, under an ID nobody has logged, so it can be saved
UNLINKED_ACCOUNT = "104463259"  # LittleMenace, keyed by nickname until an import tells us

STAT_FIELDS = [("Kills", "kills"), ("Deaths", "deaths"), ("Assists", "assists"),
               ("Souls (k)", "souls_k"), ("Plyr Dmg (k)", "plr_damage_k"),
               ("Obj Dmg (k)", "obj_damage_k"), ("Healing (k)", "healing_k")]


def payload():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def imported(match_id=LOGGED_ID):
    from utils import data_io, deadlock_api
    info = dict(payload(), match_id=int(match_id))
    return deadlock_api.to_match(info, data_io.load_players(), data_io.load_heroes())


def widgets(app, kind, label):
    return [w for w in getattr(app, kind) if w.label == label]


def one(app, kind, label):
    found = widgets(app, kind, label)
    assert len(found) == 1, f"expected one {label!r} {kind}, found {len(found)}"
    return found[0]


def open_with_import(match):
    """The Add Match page as it looks straight after a successful Fetch."""
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(PAGE, default_timeout=120)
    app.session_state["edit_unlocked"] = True
    app.session_state["imported_match"] = match
    app.run()
    return app


def test_import_reproduces_the_hand_entered_match():
    from utils import data_io

    got = imported()
    ours = next(m for m in data_io.load_matches() if m["match_id"] == LOGGED_ID)
    typed = {r["player"]: r for r in ours["players"]}

    assert got["game_length"] == ours["game_length"], got["game_length"]
    for row in got["players"]:
        if row["player"] is None:
            continue
        want = typed[row["player"]]
        for field in ("team", "hero", "win", "mvp", "key_player", "kills", "deaths", "assists"):
            assert row[field] == want[field], f"{row['player']} {field}: {row[field]!r} != {want[field]!r}"
        # We typed these off the scoreboard to the nearest thousand, give or take.
        for field in ("souls_k", "plr_damage_k", "obj_damage_k"):
            assert abs(row[field] - want[field]) <= 1.0, f"{row['player']} {field}"


def test_healing_counts_barrier():
    """The scoreboard's Healing is healing plus barrier. Rogue shielded 8.4k on top of 11.2k
    healed that night; healing alone would have logged 11.2 against the 20 we typed."""
    rogue = next(r for r in imported()["players"] if r["player"] == "Rogue")
    assert rogue["healing_k"] == 19.6, rogue["healing_k"]


def test_date_is_the_night_it_was_played():
    """Started 02:35 UTC on the 24th - which is the evening of the 23rd in New York."""
    assert imported()["date"] == "2026-08-23", imported()["date"]


def test_unknown_account_is_left_open():
    rows = [r for r in imported()["players"] if r["player"] is None]
    assert [r["account_id"] for r in rows] == [UNLINKED_ACCOUNT], rows


def test_form_opens_on_the_import():
    match = imported(NEW_ID)
    app = open_with_import(match)
    assert not app.exception, app.exception

    assert one(app, "text_input", "Match ID").value == NEW_ID
    assert [s.value for s in widgets(app, "selectbox", "Player")] == [r["player"] for r in match["players"]]
    assert [s.value for s in widgets(app, "selectbox", "Hero")] == [r["hero"] for r in match["players"]]
    for label, field in STAT_FIELDS:
        got = [n.value for n in widgets(app, "number_input", label)]
        assert got == [r[field] for r in match["players"]], f"{label}: {got}"
    assert str(one(app, "date_input", "Date played").value) == match["date"]
    assert one(app, "text_input", "Game length (MM:SS)").value == match["game_length"]
    assert one(app, "selectbox", "MVP").value == next(r["player"] for r in match["players"] if r["mvp"])
    assert sorted(one(app, "multiselect", "Key Players (pick exactly 2)").value) == \
        sorted(r["player"] for r in match["players"] if r["key_player"])


def test_fetch_button():
    """The button itself, with the API stood in for: a new ID fills the form, one we already have
    points at Edit instead, and one the API never saw says so rather than failing quietly."""
    from streamlit.testing.v1 import AppTest
    from utils import deadlock_api

    live = deadlock_api.match_info
    deadlock_api.match_info = lambda mid: dict(payload(), match_id=int(mid)) if mid == NEW_ID else None
    try:
        app = AppTest.from_file(PAGE, default_timeout=120)
        app.session_state["edit_unlocked"] = True
        app.run()

        one(app, "text_input", "Fetch from match ID").set_value(LOGGED_ID)
        one(app, "button", "Fetch").click().run()
        assert any("already logged" in w.value for w in app.warning), [w.value for w in app.warning]

        one(app, "text_input", "Fetch from match ID").set_value("123")
        one(app, "button", "Fetch").click().run()
        assert any("doesn't have match 123" in e.value for e in app.error), [e.value for e in app.error]

        one(app, "text_input", "Fetch from match ID").set_value(NEW_ID)
        one(app, "button", "Fetch").click().run()
        assert not app.exception, app.exception
        assert one(app, "text_input", "Match ID").value == NEW_ID
        assert widgets(app, "selectbox", "Hero")[0].value == imported(NEW_ID)["players"][0]["hero"]
    finally:
        deadlock_api.match_info = live


def test_empty_slot_blocks_the_save(tmp_files):
    app = open_with_import(imported(NEW_ID))
    one(app, "button", "Save match").click().run()

    assert any("Every Player slot" in e.value for e in app.error), [e.value for e in app.error]
    saved = json.load(open(tmp_files["matches"], encoding="utf-8"))
    assert not any(m["match_id"] == NEW_ID for m in saved), "a match with an empty slot was saved"


def test_filling_the_slot_links_the_account(tmp_files):
    match = imported(NEW_ID)
    app = open_with_import(match)
    slot = [r["player"] for r in match["players"]].index(None)
    widgets(app, "selectbox", "Player")[slot].set_value("LittleMenace").run()
    one(app, "button", "Save match").click().run()

    assert not app.exception, app.exception
    assert not app.error, [e.value for e in app.error]

    players = json.load(open(tmp_files["players"], encoding="utf-8"))
    assert "LittleMenace" not in players, "the nickname key should have been retired"
    assert players[UNLINKED_ACCOUNT]["display_name"] == "LittleMenace"
    assert UNLINKED_ACCOUNT in players[UNLINKED_ACCOUNT]["account_ids"]

    saved = json.load(open(tmp_files["matches"], encoding="utf-8"))
    new = next(m for m in saved if m["match_id"] == NEW_ID)
    assert new["players"][slot]["player_key"] == UNLINKED_ACCOUNT, new["players"][slot]
    assert new["bans"] == [] and new["first_picks"] == []
    stale = [m["match_id"] for m in saved for r in m["players"] if r.get("player_key") == "LittleMenace"]
    assert not stale, f"older matches still point at the nickname key: {stale}"


def main():
    from utils import data_io, github_sync

    # Local files only, and throwaway copies of them: the save test writes matches, players
    # and ranks, and against a configured checkout it would write them to the live data branch.
    github_sync._config = lambda: None
    tmp_dir = tempfile.mkdtemp(prefix="import_test_")
    tmp_files = {}
    for name, attr in (("matches", "MATCHES_FILE"), ("players", "PLAYERS_FILE"), ("ranks", "RANKS_FILE")):
        tmp_files[name] = os.path.join(tmp_dir, f"{name}.json")
        shutil.copy(getattr(data_io, attr), tmp_files[name])
        setattr(data_io, attr, tmp_files[name])
    data_io.invalidate_cache()

    tests = (test_import_reproduces_the_hand_entered_match, test_healing_counts_barrier,
             test_date_is_the_night_it_was_played, test_unknown_account_is_left_open,
             test_form_opens_on_the_import, test_fetch_button, test_empty_slot_blocks_the_save,
             test_filling_the_slot_links_the_account)
    failures = 0
    try:
        for test in tests:
            args = (tmp_files,) if test.__code__.co_argcount else ()
            try:
                test(*args)
            except AssertionError as exc:
                print(f"FAIL   {test.__name__}\n{exc}")
                failures += 1
            else:
                print(f"ok     {test.__name__}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
