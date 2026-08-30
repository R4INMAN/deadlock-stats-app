# Data branch

The live data store for the Deadlock PUG stats app. **Do not merge this branch into `main`,
and do not delete it** - the hosted app reads and writes these files here.

Every commit is one edit made through the app: a match added, a match corrected, a player
registered. The app writes via the GitHub contents API, conditional on each file's blob sha,
so two people saving at the same moment cannot silently overwrite one another.

It is a deliberately separate branch because pushing to the branch Streamlit Cloud deploys
from triggers a redeploy - logging a match would otherwise reboot the app underneath whoever
was using it.

`main` keeps its own copy of these files. That copy is the seed for local development and the
fallback the app renders if GitHub is unreachable, so it drifts behind this branch over time;
refresh it from here when the gap starts to matter.

Editing a file here by hand is fine - the app picks it up within five minutes.
