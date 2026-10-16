# Deploying with data steps

This is how we deploy a release that needs data steps on the server, like the 2026-10-16 review
(`scripts/apply_review_2026_10_16.sh`). A release without data steps only needs `flyctl deploy`.

The app runs on one Fly machine (`desert-watch`, shared-cpu-1x, 512 MB, 1 GB swap) with the volume
`dw_data` at /data. The image works from /app/backend and runs as the user `dw`.

## Why we pause the scheduler

The scheduler runs inside the web process. Its jobs are the hourly collection and theme-model scoring
at :07, the 12-week recompute at :45, the six-hourly collection at :17 (it can take 45 minutes), the
nightly jobs from 02:05 and the full recompute at 03:30.

The data steps run as their own `python -m app.cli` processes. Every data command and every scheduled
job takes the job lock (`/data/jobs.lock`, see `backend/app/joblock.py`), so they take turns and never
write at the same time. A command that finds a job running says so and waits for it to finish.

We still pause the scheduler for the data steps. Then no step waits behind a long collection, and no
job the scheduler starts adds its memory to a step's. A full recompute takes about 250 MB and the
hourly scoring child about 200 MB, next to a web process of 100 to 260 MB.

## Steps

1. Take a volume snapshot first: `flyctl volumes list`, then `flyctl volumes snapshots create <volume id>`.

2. Deploy the new image with the scheduler off. The image sets `DW_SCHEDULER=1` and a secret overrides it:

   ```
   flyctl secrets set DW_SCHEDULER=0 --stage
   flyctl deploy
   ```

   `flyctl secrets list` should now list DW_SCHEDULER. On the Sources page no new runs appear after the restart.

3. Upload what the steps need (the steps script, the model bundle, the gold labels, the search rows) to
   /data/imports. From Git Bash, `MSYS_NO_PATHCONV=1` stops it rewriting /data:

   ```
   flyctl ssh console -C "runuser -u dw -- mkdir -p /data/imports"
   MSYS_NO_PATHCONV=1 flyctl ssh sftp put scripts/apply_review_2026_10_16.sh /data/imports/apply_review_2026_10_16.sh
   ```

4. Run the steps as `dw`. Run as root they would leave root-owned SQLite files behind. Start them
   detached so they keep going if the ssh session drops:

   ```
   flyctl ssh console
   cd /app/backend
   IMPORTS=/data/imports MODEL=/data/imports/<bundle>.joblib SEARCH=/data/imports/<search file>.jsonl \
     setsid nohup runuser -u dw -- sh /data/imports/apply_review_2026_10_16.sh > /data/imports/steps.log 2>&1 &
   tail -f /data/imports/steps.log
   ```

   Every step can be run again. After a failure, fix the cause and start again from that step with `STEP=<n>`.
   On the laptop the whole run took 7 to 9 minutes. Expect 20 to 30 on the Fly machine.

5. Turn the scheduler back on. This restarts the machine with the image's `DW_SCHEDULER=1`:

   ```
   flyctl secrets unset DW_SCHEDULER
   ```

6. Check the first hour. At about :08 run `flyctl ssh console -C "free -m"` to see the memory with the
   hourly scoring child running. On the Sources page the hourly collectors and theme_model should
   say ok. The first hourly run after the deploy scores the few articles the steps left unscored.
   The first nightly train-small-model skips when the labels have not changed since the live model was trained.

## The order of the data steps

The script for a release lists its steps in order. These rules decide that order:

- Theme terms change first (apply-theme-terms, or sync-themes), then retag-all.
- retag-all comes before classify-items --all. Once a model is live, run classify-items --all after
  every retag-all or sync-themes. Re-tagging keeps the links the model supports but scores nothing, so
  only classify-items brings the vetoes on gender themes and the scores of new links in line. A theme
  saved in Admin does this by itself.
- After classify-items --reset, run retag-all. The reset gives each model link back to what it was and
  leaves it off, and only the rules can say which of those links they still match.
- After activate-model or rollback-model, run classify-items --all.
- register-model can be run again. With the same file it does nothing.
- The full recompute comes last, so the scores see every change before it. ANALYZE after it helps the
  query planner.

## Commands by hand

The same job lock covers commands run by hand at any time. A data command waits while a scheduled job
runs, and the scheduler's next job waits for the command. So a long command like a backfill holds up
the hourly collection until it ends, and each job that was waiting then runs once.

Quick or read-only commands never wait for the lock: init, create-admin, invite, model-status, review,
alerts-list, train-theme-model (laptop only) and any `--dry-run`. Run every command as `dw` with
`runuser -u dw --`.
