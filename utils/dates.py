"""One definition of what day a PUG happened on.

The group plays evenings US Eastern, which routinely runs past midnight UTC. Anything that
reads a clock in UTC - the API's `start_time`, and `date.today()` on a Streamlit Cloud server -
lands a late Sunday game on Monday. Everything that assigns a match a date goes through here so
the backfill and the Add Match form cannot drift apart.

ZoneInfo rather than a fixed -4: the offset is -4 in summer and -5 in winter, and hardcoding
either one silently shifts games by an hour for half the year.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/New_York")


def local_date(start_time):
    """Unix timestamp -> 'YYYY-MM-DD' on the night the group actually played."""
    return datetime.fromtimestamp(start_time, LOCAL_TZ).strftime("%Y-%m-%d")


def today():
    """Today's date where the group lives, not where the server happens to run."""
    return datetime.now(LOCAL_TZ).date()
