"""Fill in each match's `date` from the Deadlock API's `start_time`.

Run it as many times as you like: it only asks the API about matches whose date is still
missing, and it writes after every success, so an interrupted run keeps what it got.

    python backfill_match_dates.py

Two things worth knowing before you wonder why it is slow.

The API serves a match from its own cache when it has one and falls back to asking Steam when
it does not, and those two paths have very different rate limits - 100 requests per 10s from
cache, but only 3 PER HOUR from Steam, counted per IP. Our older PUGs are custom lobbies that
never made it into the API's database, so they are all on the slow path. Set a key to raise
that to 300/hour and finish in one run:

    DEADLOCK_API_KEY=... python backfill_match_dates.py

The script stops as soon as it is rate limited rather than burning attempts against the quota,
and tells you when the window reopens. Failed attempts count against it too, so retrying in a
tight loop makes things worse, not better.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from utils import data_io
from utils.dates import local_date

API = "https://api.deadlock-api.com/v1/matches/{match_id}/metadata"
USER_AGENT = "deadlock-stats-app/0.1 (+github.com/R4INMAN/deadlock-stats-app)"


def fetch_start_time(match_id, api_key=None):
    """(start_time, None) on success, (None, reason) on failure.

    Reason is the sentinel "rate-limited" when we have run out of quota, which the caller
    treats as "stop", not "skip" - every further request would just be refused.
    """
    request = urllib.request.Request(API.format(match_id=match_id))
    request.add_header("User-Agent", USER_AGENT)
    if api_key:
        request.add_header("X-API-KEY", api_key)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            start_time = json.load(response)["match_info"].get("start_time")
        return (start_time, None) if start_time else (None, "no start_time in response")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return None, "rate-limited"
        # 503 here means the API reached Steam and Steam declined; it is worth retrying later,
        # but the attempt has already cost us quota, so treat it like the limit and back off.
        if exc.code == 503:
            return None, "rate-limited"
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def main():
    api_key = os.environ.get("DEADLOCK_API_KEY")
    matches = data_io.load_matches()
    todo = [m for m in matches if not m.get("date")]
    print(f"{len(matches) - len(todo)}/{len(matches)} matches already dated; {len(todo)} to go.")
    if not todo:
        return 0
    if not api_key:
        print("No DEADLOCK_API_KEY set - uncached matches are capped at 3/hour.")

    filled = 0
    for match in todo:
        match_id = match["match_id"]
        start_time, problem = fetch_start_time(match_id, api_key)
        if problem == "rate-limited":
            print(f"  {match_id}: rate limited - stopping with {filled} filled this run.")
            print("  Re-run later to pick up where this left off.")
            break
        if problem:
            print(f"  {match_id}: {problem}")
            continue
        match["date"] = local_date(start_time)
        # Save per match so a run that dies halfway still banks its progress.
        data_io.save_matches(matches)
        filled += 1
        print(f"  {match_id}: {match['date']}")
        time.sleep(0.4)

    remaining = sum(1 for m in matches if not m.get("date"))
    print(f"\nFilled {filled} this run. {remaining} still undated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
