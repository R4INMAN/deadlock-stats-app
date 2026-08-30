"""Tests for the conditional-write path, against a fake contents API.

The bug this code exists to fix lost three logged matches, and the subtle half of it - two
people saving at once - is exactly the case you cannot reproduce by clicking around. So the
fake server here enforces the same sha precondition GitHub does, and the interesting tests
wedge a competing write in between our read and our PUT.

Plain asserts and a main(), so this runs with `python tests/test_github_sync.py` and the app
keeps its three-line requirements.txt.
"""
import base64
import contextlib
import copy
import io
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeGitHub:
    """A contents API that honours sha preconditions, and nothing else."""

    def __init__(self, files=None, branches=("data",)):
        self.files = {}
        self.branches = set(branches)
        self.commits = []
        self.before_put = None
        self.intruder_writes = 0
        self._sha_counter = 0
        self._lock = threading.Lock()
        for path, content in (files or {}).items():
            self._write(path, content)

    def _write(self, path, obj):
        self._sha_counter += 1
        sha = f"sha{self._sha_counter}"
        self.files[path] = (json.dumps(obj, indent=2) + "\n", sha)
        return sha

    def request(self, method, url, headers=None, timeout=None, params=None, data=None):
        if headers.get("Authorization") == "Bearer bad-token":
            return FakeResponse(403, {"message": "Bad credentials"})

        if "/branches/" in url:
            branch = url.rsplit("/", 1)[1]
            return FakeResponse(200 if branch in self.branches else 404)

        path = url.split("/contents/", 1)[1]

        if method == "GET":
            if (params or {}).get("ref") not in self.branches:
                return FakeResponse(404)
            if path not in self.files:
                return FakeResponse(404)
            content, sha = self.files[path]
            return FakeResponse(200, {
                "content": base64.b64encode(content.encode()).decode(),
                "sha": sha,
            })

        if method == "PUT":
            body = json.loads(data)
            if body["branch"] not in self.branches:
                return FakeResponse(404, {"message": "Branch not found"})

            # The hook is how a test simulates somebody else saving in the window between
            # our read and our write. It fires before the precondition is checked.
            if self.before_put:
                hook, self.before_put = self.before_put, None
                hook(self)

            # An "intruder" is a writer this process cannot see - another container, a hand
            # edit on the branch, a script. The in-process lock is no defence against those,
            # so this is what actually exercises the sha precondition and the replay.
            with self._lock:
                if self.intruder_writes > 0:
                    self.intruder_writes -= 1
                    current = json.loads(self.files[path][0]) if path in self.files else []
                    self._write(path, current + [{"match_id": f"intruder-{self.intruder_writes}"}])

            with self._lock:
                existing_sha = self.files[path][1] if path in self.files else None
                if body.get("sha") != existing_sha:
                    return FakeResponse(409, {"message": "sha does not match"})
                incoming = json.loads(base64.b64decode(body["content"]).decode())
                self._write(path, incoming)
                self.commits.append(body["message"])
            return FakeResponse(200, {"content": {}})

        raise AssertionError(f"unexpected {method} {url}")

    def contents(self, path):
        return json.loads(self.files[path][0])


class FakeSecrets(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def install(monkey_target, server, secrets=None):
    """Point a module's `requests` and `st` at the fake server."""
    monkey_target.requests = type("R", (), {
        "request": staticmethod(server.request),
        "RequestException": Exception,
    })
    monkey_target.st = type("S", (), {"secrets": secrets if secrets is not None else FakeSecrets(
        github_token="good-token", github_repo="owner/repo", github_branch="data",
    )})


# ------------------------------------------------------------------ tests

def test_missing_file_is_not_an_error():
    import utils.github_sync as gs
    server = FakeGitHub()
    install(gs, server)

    data, sha = gs.read_json("data/matches.json", default=[])
    assert data == [], data
    assert sha is None, sha


def test_missing_branch_is_an_error():
    import utils.github_sync as gs
    server = FakeGitHub(branches=("main",))
    install(gs, server)

    try:
        gs.read_json("data/matches.json", default=[])
    except gs.SyncError as exc:
        assert "does not exist" in str(exc), exc
    else:
        raise AssertionError("a missing branch should raise, not create")


def test_write_creates_then_appends():
    import utils.github_sync as gs
    server = FakeGitHub()
    install(gs, server)

    gs.mutate("data/matches.json", lambda ms: ms + [{"match_id": "1"}], "Add 1", [])
    gs.mutate("data/matches.json", lambda ms: ms + [{"match_id": "2"}], "Add 2", [])

    assert server.contents("data/matches.json") == [{"match_id": "1"}, {"match_id": "2"}]
    assert server.commits == ["Add 1", "Add 2"], server.commits


def test_concurrent_write_is_replayed_not_clobbered():
    """The whole point: a competing save lands first, and BOTH matches survive."""
    import utils.github_sync as gs
    server = FakeGitHub(files={"data/matches.json": [{"match_id": "1"}]})
    install(gs, server)

    def someone_else_saves(srv):
        current = srv.contents("data/matches.json")
        srv._write("data/matches.json", current + [{"match_id": "99"}])

    server.before_put = someone_else_saves
    gs.mutate("data/matches.json", lambda ms: ms + [{"match_id": "2"}], "Add 2", [])

    ids = [m["match_id"] for m in server.contents("data/matches.json")]
    assert ids == ["1", "99", "2"], f"lost a write: {ids}"


def test_op_raising_commits_nothing():
    import utils.github_sync as gs
    server = FakeGitHub(files={"data/matches.json": [{"match_id": "1"}]})
    install(gs, server)

    def reject(matches):
        raise ValueError("Match 1 already exists.")

    try:
        gs.mutate("data/matches.json", reject, "Add 1", [])
    except ValueError:
        pass
    else:
        raise AssertionError("op raising should abort the write")

    assert server.commits == [], server.commits
    assert server.contents("data/matches.json") == [{"match_id": "1"}]


def test_bad_token_explains_the_fix():
    import utils.github_sync as gs
    server = FakeGitHub()
    install(gs, server, FakeSecrets(
        github_token="bad-token", github_repo="owner/repo", github_branch="data",
    ))

    try:
        gs.read_json("data/matches.json", default=[])
    except gs.SyncError as exc:
        assert "Contents: Read and write" in str(exc), exc
    else:
        raise AssertionError("a refused token must raise, not return empty data")


def test_unconfigured_raises_rather_than_pretending():
    import utils.github_sync as gs
    server = FakeGitHub()
    install(gs, server, FakeSecrets())

    assert gs.configured() is False
    try:
        gs.mutate("data/matches.json", lambda ms: ms, "noop", [])
    except gs.SyncNotConfigured:
        pass
    else:
        raise AssertionError("an unconfigured write must not report success")


def test_gives_up_loudly_under_sustained_contention():
    """A writer that conflicts on every single attempt must raise, not lose data quietly.

    Five retries is sized for a handful of people occasionally saving a match, not for an
    adversary. When that budget runs out the contract is that the caller hears about it and
    the stored data is untouched - the one outcome that must never happen is a green
    "Match saved!" over a write that never landed.
    """
    import utils.github_sync as gs
    server = FakeGitHub(files={"data/matches.json": [{"match_id": "1"}]})
    server.intruder_writes = 10_000  # conflicts on every attempt, forever
    install(gs, server)

    try:
        gs.mutate("data/matches.json", lambda ms: ms + [{"match_id": "mine"}], "Add mine", [])
    except gs.SyncError as exc:
        assert "Nothing was lost" in str(exc), exc
    else:
        raise AssertionError("exhausting the retry budget must raise")

    stored = [m["match_id"] for m in server.contents("data/matches.json")]
    assert "mine" not in stored, f"a failed write must not appear: {stored}"
    assert server.commits == [], server.commits


def test_branch_defaults_away_from_the_deployed_one():
    """A missing github_branch must not fall back to the branch the app is served from.

    This is the setting that made a heartbeat commit land on main and reboot the app on
    8/30. Defaulting in code rather than in a dashboard means the repo predicts the app's
    behaviour, and a wiped secret degrades to the safe option.
    """
    import utils.github_sync as gs
    server = FakeGitHub()
    install(gs, server, FakeSecrets(github_token="good-token", github_repo="owner/repo"))

    assert gs.target() == f"owner/repo@{gs.DEFAULT_BRANCH}", gs.target()
    assert gs.DEFAULT_BRANCH not in gs.DEPLOY_BRANCH_NAMES
    assert gs.writes_to_deploy_branch() is False


def test_deploy_branch_is_detected():
    import utils.github_sync as gs
    server = FakeGitHub(branches=("main", "master", "data"))

    for branch in ("main", "master"):
        install(gs, server, FakeSecrets(
            github_token="good-token", github_repo="owner/repo", github_branch=branch,
        ))
        assert gs.writes_to_deploy_branch() is True, branch

    install(gs, server, FakeSecrets(
        github_token="good-token", github_repo="owner/repo", github_branch="data",
    ))
    assert gs.writes_to_deploy_branch() is False


def test_check_sync_refuses_to_write_to_a_deploy_branch():
    """The setup script must stop, not warn - a warning already failed to prevent this once."""
    import utils.github_sync as gs
    import scripts.check_sync as cs
    server = FakeGitHub(files={"data/matches.json": []}, branches=("main",))
    install(gs, server, FakeSecrets(
        github_token="good-token", github_repo="owner/repo", github_branch="main",
    ))

    saved_argv = sys.argv
    sys.argv = ["check_sync.py", "--write"]
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            exit_code = cs.main()
        assert exit_code == 1, "should exit non-zero"
        assert "refuses to" in out.getvalue(), out.getvalue()
    finally:
        sys.argv = saved_argv
    assert server.commits == [], f"refused check still wrote: {server.commits}"


def test_parallel_saves_all_land():
    """Ten threads racing three unseen outside writers - all thirteen writes land.

    The in-process lock alone would pass this with the retry removed, because it serialises
    the threads and no conflict ever occurs. The intruder writes are what make it a real test
    of the precondition: they come from outside this process, exactly like a second container
    or a hand edit on the data branch, and only the read-replay-retry cycle survives them.
    """
    import utils.github_sync as gs
    server = FakeGitHub(files={"data/matches.json": []})
    server.intruder_writes = 3
    install(gs, server)

    errors = []

    def save(n):
        try:
            gs.mutate("data/matches.json",
                      lambda ms, n=n: ms + [{"match_id": str(n)}], f"Add {n}", [])
        except Exception as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=save, args=(n,)) for n in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    contents = server.contents("data/matches.json")
    ours = sorted(int(m["match_id"]) for m in contents if not m["match_id"].startswith("intruder"))
    theirs = [m for m in contents if m["match_id"].startswith("intruder")]
    assert ours == list(range(10)), f"lost our writes: {ours}"
    assert len(theirs) == 3, f"lost outside writes: {len(theirs)}"


def test_data_io_ops_survive_replay():
    """data_io's ops get re-run against newer data, so their bookkeeping must reset."""
    import utils.github_sync as gs
    import utils.data_io as dio
    server = FakeGitHub(files={
        "data/matches.json": [{"match_id": "1"}, {"match_id": "2"}],
    })
    install(gs, server)
    dio.invalidate_cache()

    def someone_else_saves(srv):
        srv._write("data/matches.json", srv.contents("data/matches.json") + [{"match_id": "3"}])

    server.before_put = someone_else_saves
    assert dio.update_match("2", {"match_id": "2", "note": "edited"}) is True

    contents = server.contents("data/matches.json")
    assert [m["match_id"] for m in contents] == ["1", "2", "3"], contents
    assert contents[1]["note"] == "edited", contents

    # And a delete of something that isn't there reports False rather than raising.
    assert dio.delete_match("nope") is False


def test_data_io_rejects_duplicate_match_id():
    import utils.github_sync as gs
    import utils.data_io as dio
    server = FakeGitHub(files={"data/matches.json": [{"match_id": "1"}]})
    install(gs, server)
    dio.invalidate_cache()

    try:
        dio.add_match({"match_id": "1"})
    except ValueError as exc:
        assert "already exists" in str(exc), exc
    else:
        raise AssertionError("a duplicate match id must be rejected against fresh data")


def test_one_stale_file_is_not_cleared_by_another_succeeding():
    """A page loads four files. One failing must keep warning after the others succeed."""
    import utils.github_sync as gs
    import utils.data_io as dio
    server = FakeGitHub(files={
        "data/matches.json": [{"match_id": "1"}],
        "data/players.json": {"Zack": {}},
    })
    install(gs, server)
    dio.invalidate_cache()

    # matches.json is unreadable; players.json is fine.
    real_request = server.request

    def only_matches_fails(method, url, **kw):
        if "matches.json" in url and method == "GET":
            return FakeResponse(500, {"message": "boom"})
        return real_request(method, url, **kw)

    gs.requests = type("R", (), {"request": staticmethod(only_matches_fails),
                                 "RequestException": Exception})

    dio.load_matches()
    assert dio.storage_status()[0] == "degraded", dio.storage_status()

    dio.load_players()  # succeeds - must NOT clear the matches warning
    mode, detail = dio.storage_status()
    assert mode == "degraded", f"a success wiped the stale warning: {mode} {detail}"
    assert "matches.json" in detail, detail
    assert "players.json" not in detail, detail


def test_an_outage_does_not_refetch_on_every_render():
    """Negative caching: four files x a re-run per click x a 15s timeout would hang a page."""
    import utils.github_sync as gs
    import utils.data_io as dio
    server = FakeGitHub(files={"data/matches.json": [{"match_id": "1"}]})
    install(gs, server)
    dio.invalidate_cache()

    attempts = []

    def always_down(method, url, **kw):
        attempts.append(url)
        raise Exception("network is down")

    gs.requests = type("R", (), {"request": staticmethod(always_down),
                                 "RequestException": Exception})

    for _ in range(10):
        assert dio.load_matches(), "must still serve the committed fallback"
    assert len(attempts) == 1, f"retried the network {len(attempts)} times during an outage"
    assert dio.storage_status()[0] == "degraded"

    # ...and it recovers once the TTL lapses.
    with dio._cache_lock:
        path, (msg, _) = next(iter(dio._stale.items()))
        dio._stale[path] = (msg, 0)
    gs.requests = type("R", (), {"request": staticmethod(server.request),
                                 "RequestException": Exception})
    dio.load_matches()
    assert dio.storage_status()[0] == "remote", dio.storage_status()


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
