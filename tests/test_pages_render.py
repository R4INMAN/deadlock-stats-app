"""Every page renders without raising, against the real data files.

Cheap insurance for a multi-page app nobody clicks through end to end before pushing: a
rename in `stats.py` or a column dropped from a dataframe shows up here in ten seconds
instead of as a stack trace on the hosted app in front of the group.

This exercises the local-files path deliberately - no github_token is set, so `data_io` falls
back to `data/*.json` and the test needs no network and no credentials. `test_github_sync.py`
covers the remote path with a fake API.

Run with `python tests/test_pages_render.py`.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    from streamlit.testing.v1 import AppTest

    # The pages load art with paths relative to the repo root, and AppTest resolves a relative
    # script path against *this* file rather than the cwd - so chdir for the former and pass
    # absolute paths for the latter.
    os.chdir(ROOT)
    pages = [os.path.join(ROOT, "Home.py")] + sorted(glob.glob(os.path.join(ROOT, "pages", "*.py")))
    failures = 0

    for page in pages:
        name = os.path.relpath(page, ROOT)
        app = AppTest.from_file(page, default_timeout=90)
        # The edit pages gate on this before rendering anything; without it they would all
        # "pass" by stopping at the password prompt.
        app.secrets["edit_password"] = "test"
        try:
            app.run()
        except Exception as exc:  # noqa: BLE001 - this is the reporter
            print(f"CRASH  {name}: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        if app.exception:
            for exception in app.exception:
                print(f"FAIL   {name}: {exception.value}")
            failures += 1
        else:
            print(f"ok     {name}")

    print(f"\n{len(pages) - failures}/{len(pages)} pages render clean")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
