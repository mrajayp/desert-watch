#!/bin/sh
# Data steps after deploying A-R2.9 (English plural variants in the theme rules). Run from the backend
# directory as the app user, with the scheduler paused (docs/DEPLOY.md). Idempotent: every step can be re-run.
#   PY    python to use (default: python)
#   STEP  start from this step number (default 1), to resume after a failure
# Each step prints its result. Stop on the first error (set -e).
set -e
PY=${PY:-python}
STEP=${STEP:-1}
run() { n=$1; shift; if [ "$n" -ge "$STEP" ]; then echo "== step $n: $*"; date -u +%H:%M:%S; "$@"; fi; }

# 1: every article re-tagged under the rules with plural variants (prints the before/after link counts)
run 1 $PY -m app.cli retag-all
# 2: the live theme model scores the links the re-tag added or changed (gender vetoes, new links' scores)
run 2 $PY -m app.cli classify-items --all
# 3: duplicates, scores, network and labels over the full history
run 3 $PY -m app.cli recompute
# 4: query planner statistics
run 4 $PY -c "from app.db import engine; c = engine.raw_connection(); c.execute('ANALYZE'); c.commit(); c.close(); print('analyzed')"
echo "== done"; date -u +%H:%M:%S
