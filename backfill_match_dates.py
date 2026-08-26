"""Fill in each match's `date` from the Deadlock API's public database snapshot.

    python backfill_match_dates.py          # needs: pip install duckdb

Why not the per-match API endpoint: it works, but our PUGs are custom lobbies, and matches the
API never ingested fall through to a Steam fetch capped at **3 requests per hour per IP** -
failed attempts included. 35 of our 82 were on that path, and every Steam fetch attempted came
back 503. This route has no rate limit at all.

How it works. Deadlock assigns match IDs sequentially, so match ID is monotonic in start time.
The API publishes a daily Parquet snapshot of its whole database, including 326M rows of
(match_id, start_time). For a match that is in the snapshot we read its start_time directly.
For one that is not - every custom lobby - we bracket it between the nearest match IDs above
and below, which in practice sit within a few seconds either side. When both ends of the
bracket fall on the same local date, that date is not an estimate but a proof: the match ID
ordering guarantees the real start time lies between them.

Validated by holdout on the 47 matches whose start_time we had fetched directly: median error
1 second, worst case 4 seconds, and 47/47 landed on the correct calendar date.
"""
import bisect
import json
import sys

from utils import data_io
from utils.dates import local_date

SNAPSHOT = "https://s3-cache.deadlock-api.com/db-snapshot/public/match_player"
PARTS = 102
# How far either side of a match ID to look for neighbours. Matches are dense enough that a few
# thousand IDs is a window of seconds; wider costs little because Parquet row-group statistics
# let DuckDB skip everything outside the range.
WINDOW = 3000


def neighbour_pairs(targets):
    """Sorted (match_id, start_time) for every match near one of `targets`."""
    try:
        import duckdb
    except ImportError:
        sys.exit("This needs DuckDB to read the snapshot:\n\n    pip install duckdb\n")
    files = "[" + ",".join(f"'{SNAPSHOT}/match_player_{i}.parquet'" for i in range(PARTS)) + "]"
    ranges = " OR ".join(f"(match_id BETWEEN {t - WINDOW} AND {t + WINDOW})" for t in targets)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET TimeZone='UTC';")
    rows = con.execute(
        f"SELECT DISTINCT match_id, epoch(start_time)::BIGINT FROM read_parquet({files}) "
        f"WHERE {ranges}"
    ).fetchall()
    return sorted({(int(m), int(s)) for m, s in rows if s and s > 0})


def date_for(match_id, pairs, ids):
    """(date, how) for one match ID, or (None, reason) when it cannot be placed."""
    i = bisect.bisect_left(ids, match_id)
    if i < len(ids) and ids[i] == match_id:
        return local_date(pairs[i][1]), "exact"
    lo = pairs[i - 1] if i > 0 else None
    hi = pairs[i] if i < len(pairs) else None
    if not (lo and hi):
        return None, "no bracketing matches in the snapshot"
    low_date, high_date = local_date(lo[1]), local_date(hi[1])
    if low_date == high_date:
        # Both ends of the bracket are the same day, so the ID ordering proves the date.
        return low_date, "bracketed"
    fraction = (match_id - lo[0]) / (hi[0] - lo[0])
    return local_date(lo[1] + fraction * (hi[1] - lo[1])), "interpolated"


def main():
    matches = data_io.load_matches()
    todo = [m for m in matches if not m.get("date")]
    print(f"{len(matches) - len(todo)}/{len(matches)} already dated; {len(todo)} to fill.")
    if not todo:
        return 0

    targets = [int(m["match_id"]) for m in todo]
    print("Reading the snapshot (a few seconds per pass, no rate limit)...")
    pairs = neighbour_pairs(targets)
    ids = [p[0] for p in pairs]
    print(f"  {len(pairs):,} neighbouring matches pulled.")

    filled = 0
    for match in todo:
        date, how = date_for(int(match["match_id"]), pairs, ids)
        if not date:
            print(f"  {match['match_id']}: {how}")
            continue
        match["date"] = date
        filled += 1
        print(f"  {match['match_id']}: {date} ({how})")
    data_io.save_matches(matches)

    remaining = sum(1 for m in matches if not m.get("date"))
    print(f"\nFilled {filled}. {remaining} still undated.")
    if remaining:
        print("A match ID with no bracketing neighbours is usually one that cannot exist - "
              "check it against the ID shown in game.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
