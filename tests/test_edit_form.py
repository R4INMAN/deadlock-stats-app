"""The Edit Match form must come up holding the match you picked.

It did not, for a while: every box-score field is a keyed widget, and Streamlit ignores the
`value=` / `index=` a script passes a keyed widget once that key has state - so picking a match
to edit refilled the date, length, winner and MVP (no keys) while all 12 players, heroes and
their stats stayed on whatever the Add form had left behind. Fixing a wrong date therefore meant
retyping the entire match, and saving without noticing would have rewritten it as twelve copies
of the alphabetically-first player.

That is invisible in a page-renders test - nothing raises - so it gets its own script.

Run with `python tests/test_edit_form.py`.
"""
import copy
import datetime
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "pages", "8_Add_Match.py")

STAT_FIELDS = [("Kills", "kills"), ("Deaths", "deaths"), ("Assists", "assists"),
               ("Souls (k)", "souls_k"), ("Plyr Dmg (k)", "plr_damage_k"),
               ("Obj Dmg (k)", "obj_damage_k"), ("Healing (k)", "healing_k"),
               ("Draft Slot", "draft_slot")]


def widgets(app, kind, label):
    return [w for w in getattr(app, kind) if w.label == label]


def one(app, kind, label):
    found = widgets(app, kind, label)
    assert len(found) == 1, f"expected one {label!r} {kind}, found {len(found)}"
    return found[0]


def open_edit(match_id):
    """An Add Match page switched to Edit, with `match_id` selected - as a user gets there."""
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(PAGE, default_timeout=120)
    app.session_state["edit_unlocked"] = True  # the page gates on this before rendering
    app.run()
    one(app, "selectbox", "Mode").set_value("Edit Match").run()
    one(app, "selectbox", "Select match to edit").set_value(match_id).run()
    return app


def loaded_matches():
    from utils import data_io
    return data_io.load_matches()


def test_edit_prefills_the_whole_box_score():
    match = loaded_matches()[-1]
    app = open_edit(match["match_id"])

    got_players = [s.value for s in widgets(app, "selectbox", "Player")]
    got_heroes = [s.value for s in widgets(app, "selectbox", "Hero")]
    assert got_players == [p["player"] for p in match["players"]], f"players: {got_players}"
    assert got_heroes == [p["hero"] for p in match["players"]], f"heroes: {got_heroes}"
    for label, field in STAT_FIELDS:
        got = [n.value for n in widgets(app, "number_input", label)]
        want = [p[field] for p in match["players"]]
        assert got == want, f"{label}: {got} != {want}"

    assert str(one(app, "date_input", "Date played").value) == match["date"]
    assert one(app, "text_input", "Game length (MM:SS)").value == match["game_length"]
    assert one(app, "radio", "Winning side").value == next(p["team"] for p in match["players"] if p["win"])
    assert one(app, "selectbox", "MVP").value == next(p["player"] for p in match["players"] if p["mvp"])
    assert sorted(one(app, "multiselect", "Key Players (pick exactly 2)").value) == \
        sorted(p["player"] for p in match["players"] if p["key_player"])


def test_switching_match_repopulates():
    """Widget state is per-match, so the second match must not show the first one's stats."""
    matches = loaded_matches()
    first, second = matches[-1], matches[-2]
    assert [p["hero"] for p in first["players"]] != [p["hero"] for p in second["players"]], \
        "pick two matches that differ, or this proves nothing"

    app = open_edit(first["match_id"])
    one(app, "selectbox", "Select match to edit").set_value(second["match_id"]).run()

    got_heroes = [s.value for s in widgets(app, "selectbox", "Hero")]
    got_kills = [n.value for n in widgets(app, "number_input", "Kills")]
    assert got_heroes == [p["hero"] for p in second["players"]], f"heroes: {got_heroes}"
    assert got_kills == [p["kills"] for p in second["players"]], f"kills: {got_kills}"


def test_fixing_a_date_keeps_everything_else(tmp_matches):
    """The reported case: the date went in wrong, and nothing else should move when it is fixed."""
    before = copy.deepcopy(loaded_matches()[-1])
    new_date = datetime.date.fromisoformat(before["date"]) - datetime.timedelta(days=1)

    app = open_edit(before["match_id"])
    one(app, "date_input", "Date played").set_value(new_date).run()
    one(app, "button", "Save changes").click().run()

    assert not app.exception, app.exception
    after = next(m for m in json.load(open(tmp_matches, encoding="utf-8"))
                 if m["match_id"] == before["match_id"])
    assert after["date"] == str(new_date)
    expected = dict(before, date=str(new_date))
    assert after == expected, "\n".join(f"  {k}: {after[k]!r} != {v!r}"
                                        for k, v in expected.items() if after[k] != v)


def test_stale_data_hides_the_form():
    """A form that cannot save must not be offered - not after twelve players have been typed.

    The failure is faked at the GitHub boundary rather than at `storage_status`, because the
    page has to notice it on the *first* render: a container that comes up to a dead token has
    nothing in the stale map until its own reads have run, so a check made before them would
    hand out a form once per restart.
    """
    from utils import data_io, github_sync

    unconfigured, live_read = github_sync._config, github_sync.read_json

    def dead_token(*_args, **_kwargs):
        raise github_sync.SyncError(
            "GitHub refused the token for R4INMAN/deadlock-stats-app (401). The token needs "
            "'Contents: Read and write' on that repository."
        )

    github_sync._config = lambda: ("token", "R4INMAN/deadlock-stats-app", "data")
    github_sync.read_json = dead_token
    data_io.invalidate_cache()
    try:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(PAGE, default_timeout=120)
        app.session_state["edit_unlocked"] = True
        app.run()
    finally:
        github_sync._config, github_sync.read_json = unconfigured, live_read
        data_io.invalidate_cache()

    assert not app.exception, app.exception
    assert any("401" in e.value for e in app.error), "the reason for the stop should still be on screen"
    assert widgets(app, "button", "Try again"), "a stopped page needs a way back"
    assert not widgets(app, "selectbox", "Mode"), "the edit controls should not render at all"


def main():
    from utils import data_io, github_sync

    # Force the local-files path. A developer checkout usually *does* have secrets.toml, and a
    # test that drives the real save button against a configured app would commit its edits to
    # the live data branch.
    github_sync._config = lambda: None
    data_io.invalidate_cache()

    # And even locally the save writes matches.json, so it writes a throwaway copy instead.
    tmp_dir = tempfile.mkdtemp(prefix="edit_form_test_")
    tmp_matches = os.path.join(tmp_dir, "matches.json")
    shutil.copy(data_io.MATCHES_FILE, tmp_matches)
    data_io.MATCHES_FILE = tmp_matches

    tests = (test_edit_prefills_the_whole_box_score, test_switching_match_repopulates,
             test_fixing_a_date_keeps_everything_else, test_stale_data_hides_the_form)
    total = len(tests)
    failures = 0
    try:
        for test in tests:
            args = (tmp_matches,) if test.__code__.co_argcount else ()
            try:
                test(*args)
            except AssertionError as exc:
                print(f"FAIL   {test.__name__}\n{exc}")
                failures += 1
            else:
                print(f"ok     {test.__name__}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
