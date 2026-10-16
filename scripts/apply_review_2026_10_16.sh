#!/bin/sh
# One-off data steps after deploying the 2026-10-16 review changes. Run from the backend
# directory as the app user. Idempotent: every step can be re-run.
#   PY        python to use (default: python)
#   IMPORTS   folder holding gold_labels_2026-10-16.jsonl, the model bundle and the search JSONL
#   MODEL     the theme model bundle (.joblib) trained locally on a snapshot after the re-tag
#   SEARCH    the Google Trends rows (JSONL from backend/scripts/fetch_gtrends.py)
#   STEP      start from this step number (default 1), to resume after a failure
# Each step prints its result. Stop on the first error (set -e).
set -e
PY=${PY:-python}
STEP=${STEP:-1}
run() { n=$1; shift; if [ "$n" -ge "$STEP" ]; then echo "== step $n: $*"; date -u +%H:%M:%S; "$@"; fi; }

# 1-2: the theme term changes, then every article re-tagged under the new rules
run 1 $PY -m app.cli apply-theme-terms security migration health services governance gender_migrant_detained_women gender_legal_status
run 2 $PY -m app.cli retag-all
# 3-4: scope for the Facebook register pages, Wikipedia days for themes that share a title
run 3 $PY -m app.cli label-register-pages
run 4 $PY -m app.cli repair-wiki-themes
# 5-7: the review's blind labels, the theme model, and every article scored with it
run 5 $PY -m app.cli import-gold-labels "$IMPORTS/gold_labels_2026-10-16.jsonl"
run 6 $PY -m app.cli register-model "$MODEL" --activate --note "trained on the 2026-10-16 snapshot after the re-tag"
run 7 $PY -m app.cli classify-items --all
# 8: Google searches for the search lens
run 8 $PY -m app.cli import-search "$SEARCH"
# 9: duplicates, scores, network and labels over the full history
run 9 $PY -m app.cli recompute
# 10: query planner statistics (recent-window queries then use the published_at index)
run 10 $PY -c "from app.db import engine; c = engine.raw_connection(); c.execute('ANALYZE'); c.commit(); c.close(); print('analyzed')"
echo "== done"; date -u +%H:%M:%S
