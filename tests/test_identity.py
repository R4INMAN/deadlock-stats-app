"""Tests for keying players on identity rather than on nickname.

The bug this code exists to fix is silent and slow: someone changes their in-game alias, gets
re-entered under the new one, and becomes two players. Their win rate splits, their chemistry
pairs split, and nothing anywhere reports a problem - the leaderboard just quietly shows two
half-careers. So the tests that matter here are the ones that follow a rename all the way
through to what a page would render.

Plain asserts and a main(), matching the other two suites, so this runs with
`python tests/test_identity.py`.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import data_io, ratings, stats  # noqa: E402


def _row(player_key, name, team, hero, win, kills=5, deaths=5, assists=5):
    return {"team": team, "player": name, "player_key": player_key, "hero": hero, "win": win,
            "mvp": False, "key_player": False, "kp_pct": 50.0,
            "kills": kills, "deaths": deaths, "assists": assists,
            "souls_k": 40.0, "plr_damage_k": 20.0, "obj_damage_k": 5.0, "healing_k": 3.0,
            "draft_slot": 1}


def _fixture():
    """A two-match store where one player is recorded under two different nicknames."""
    players = {
        "111": {"display_name": "Mina", "account_ids": ["111"], "aliases": ["Mina", "mina_old"],
                "notes": "", "reported_rank": None},
        "222": {"display_name": "Kobbert", "account_ids": ["222"], "aliases": ["Kobbert"],
                "notes": "", "reported_rank": None},
        "Woof Woof": {"display_name": "Woof Woof", "account_ids": [], "aliases": ["Woof Woof"],
                      "notes": "", "reported_rank": None},
    }
    matches = [
        {"match_id": "2", "date": "2026-01-02", "game_length": "30:00", "players": [
            # Stored under the *old* nickname, as it was typed on the night.
            _row("111", "mina_old", "Hidden King", "Abrams", True),
            _row("222", "Kobbert", "Archmother", "Haze", False),
            _row("Woof Woof", "Woof Woof", "Archmother", "Seven", False)]},
        {"match_id": "1", "date": "2026-01-01", "game_length": "30:00", "players": [
            _row("111", "Mina", "Hidden King", "Vindicta", True),
            _row("222", "Kobbert", "Archmother", "Haze", False),
            _row("Woof Woof", "Woof Woof", "Archmother", "Seven", False)]},
    ]
    ranks = [{"player_key": "111", "player": "mina_old", "rank": "Archon 3", "date": "import"},
             {"player_key": "111", "player": "Mina", "rank": "Ascendant 1", "date": "2026-02-01"}]
    return players, matches, ranks


class _Store:
    """Point data_io at a throwaway directory of JSON files.

    Sync is forced off for the duration. Identity is storage-agnostic - the same code runs
    whether the store is the data branch or a checkout - and a developer with real secrets
    present would otherwise have these tests reach for GitHub.
    """

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        players, matches, ranks = _fixture()
        self.saved_configured = data_io.github_sync.configured
        data_io.github_sync.configured = lambda: False
        self.saved = (data_io.PLAYERS_FILE, data_io.MATCHES_FILE, data_io.RANKS_FILE)
        for attr, name, payload in (("PLAYERS_FILE", "players.json", players),
                                    ("MATCHES_FILE", "matches.json", matches),
                                    ("RANKS_FILE", "ranks.json", ranks)):
            path = os.path.join(self.dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            setattr(data_io, attr, path)
        data_io.invalidate_cache()
        return self

    def __exit__(self, *exc):
        data_io.github_sync.configured = self.saved_configured
        (data_io.PLAYERS_FILE, data_io.MATCHES_FILE, data_io.RANKS_FILE) = self.saved
        data_io.invalidate_cache()
        shutil.rmtree(self.dir, ignore_errors=True)

    def players(self):
        with open(data_io.PLAYERS_FILE, encoding="utf-8") as fh:
            return json.load(fh)


def test_a_stale_nickname_resolves_to_the_current_name():
    """The stored string is what was typed; what comes back is who they are now."""
    with _Store():
        matches = data_io.load_matches()
        names = [r["player"] for m in matches for r in m["players"]]
        assert "mina_old" not in names, f"stale nickname leaked through: {names}"
        assert names.count("Mina") == 2, names


def test_one_rename_moves_a_whole_career():
    """The point of the exercise: rename in one place, every derived view follows."""
    with _Store() as store:
        assert data_io.rename_player("111", "Mina Prime")

        df = stats.matches_to_rows_df(data_io.load_matches())
        summary = stats.player_summary_table(df)
        row = summary[summary["player"] == "Mina Prime"]
        assert len(row) == 1, f"expected one merged career, got {summary['player'].tolist()}"
        assert int(row.iloc[0]["games"]) == 2, "both games must follow the rename"
        assert "Mina" not in summary["player"].tolist(), "the old name must not survive as a player"

        # The name they used to go by stays searchable rather than being erased.
        assert "Mina" in store.players()["111"]["aliases"]


def test_a_rename_does_not_split_a_player_in_the_ratings():
    """Bradley-Terry fits per player name, so a split identity becomes two weaker players."""
    with _Store():
        data_io.rename_player("111", "Mina Prime")
        sides = ratings.sides(data_io.load_matches())
        everyone = {name for a, b, _ in sides for name in a + b}
        assert "mina_old" not in everyone and "Mina" not in everyone, everyone
        assert "Mina Prime" in everyone


def test_an_account_id_finds_its_player_including_alts():
    """What the match importer asks: I have an account id, whose is it?"""
    with _Store():
        assert data_io.key_for_account("111") == "111"
        assert data_io.key_for_account(222) == "222", "ids arrive from the API as ints"
        assert data_io.key_for_account("999") is None

        data_io.link_account("111", "999")
        assert data_io.key_for_account("999") == "111", "an alt must resolve to its owner"


def test_learning_an_account_id_rekeys_and_carries_the_history():
    """A player first seen in a match the API lacks is keyed by nickname until one turns up."""
    with _Store() as store:
        new_key = data_io.link_account("Woof Woof", "777")
        assert new_key == "777", new_key

        players = store.players()
        assert "Woof Woof" not in players, "the placeholder key must be retired"
        assert players["777"]["display_name"] == "Woof Woof", "the name is not the key"

        rows = [r for m in data_io.load_matches() for r in m["players"]
                if r["player"] == "Woof Woof"]
        assert len(rows) == 2, "their games must come with them"
        assert {r["player_key"] for r in rows} == {"777"}, "every row must point at the new key"


def test_rank_history_survives_a_rename():
    with _Store():
        data_io.rename_player("111", "Mina Prime")
        assert data_io.current_rank("111") == "Ascendant 1"
        # Logged against the key, so the entry is theirs no matter what they were called.
        data_io.add_rank_entry("111", "Eternus 2", "2026-03-01", "Mina Prime")
        assert data_io.current_rank("111") == "Eternus 2"


def test_add_player_refuses_a_display_name_already_in_use():
    """Two records sharing a display name is the very split this change removes."""
    with _Store():
        assert data_io.add_player("Newcomer") is True
        assert data_io.add_player("Mina") is False, "an existing display name must not be re-added"
        assert data_io.add_player("Zed", account_id=555) is True
        assert data_io.key_for_account("555") == "555"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - this is the reporter
            failures += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {test.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
