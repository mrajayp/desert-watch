# Deploying, data steps, backups and restores

This is how we deploy a release that needs data steps on the server, like the 2026-10-16 review
(`scripts/apply_review_2026_10_16.sh`). A release without data steps only needs `flyctl deploy`.

The app runs on one Fly machine (`desert-watch`, shared-cpu-1x, 512 MB, 1 GB swap) with the volume
`dw_data` at /data. The image works from /app/backend and runs as the user `dw`.

## Why we pause the scheduler

The scheduler runs inside the web process. Its jobs are the hourly collection and theme-model scoring
at :07, the 12-week recompute at :45, the six-hourly collection at :17 (it can take 45 minutes), the
backup at 01:15, the nightly jobs from 02:05 and the full recompute at 03:30. The two recomputes run as
child processes (`python -m app.cli recompute --weeks 12`), so their memory goes back to the system
when they end.

The data steps run as their own `python -m app.cli` processes. Every data command and every scheduled
job takes the job lock (`/data/jobs.lock`, see `backend/app/joblock.py`), so they take turns and never
write at the same time. A command that finds a job running says so and waits for it to finish. The
six-hourly collection takes the lock once per collector, so a waiting command gets in between two
collectors instead of after the whole run. Who holds the lock, and since when, is on the Admin page
under Service health (`/api/admin/health`).

We still pause the scheduler for the data steps. Then no step waits behind a long collection, and no
job the scheduler starts adds its memory to a step's. A full recompute takes about 250 MB and the
hourly scoring child about 200 MB, next to a web process of 100 to 260 MB.

## Steps

1. Take a volume snapshot first: `flyctl volumes list`, then `flyctl volumes snapshots create <volume id>`.
   The nightly off-site backup (below) is the second copy. Run it by hand before a risky step with
   `runuser -u dw -- python -m app.cli backup`.

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

6. Check the first hour. `/health` should say `{"ok": true, "scheduler": true}`. On the Admin page,
   Service health shows the next runs, the lock holder, memory and swap. At about :46 the lock holder
   should be `recompute_child` and the memory line should show the child's share going back to the
   system when it ends. On the Sources page the hourly collectors and theme_model should say ok. The
   first hourly run after the deploy scores the few articles the steps left unscored. The first nightly
   train-small-model skips when the labels have not changed since the live model was trained.

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
alerts-list, train-theme-model (laptop only) and any `--dry-run`. ai-audit does not hold the lock for
its whole run either (the assistant calls take minutes), each answer's write takes it on its own.
Run every command as `dw` with `runuser -u dw --`.

## Backups

Every night at 01:15 UTC the app writes a compact copy of the database with `VACUUM INTO`, checks it
with `PRAGMA quick_check`, gzips it and uploads it to an S3-compatible bucket as
`backups/desert_watch_<day>.db.gz` (`backend/app/backup.py`, `s3put.py`). After a successful upload
it prunes older copies to 7 daily, 4 weekly and 3 monthly. The strip on the Sources page has a
`backup` line that turns stale after 30 hours, and Service health shows the last backup.

The bucket is Tigris, created once with Fly's integration. It writes the four secrets the app reads
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `BUCKET_NAME`) and restarts the
machine:

```
flyctl storage create
```

Until those secrets exist the backup line says awaiting key and nothing is uploaded. Set the volume's
own snapshot retention as well, it is free: `flyctl volumes update <volume id> --snapshot-retention 14`.

Restore drill: once a quarter, restore the newest backup on the laptop (below, without the upload
step) and open it. Log the date and the result at the end of this file.

## Restore

The boot hook in `backend/app/db.py` swaps in `/data/incoming.db.gz` before anything connects, then
deletes the upload. To restore a backup:

1. Fetch the copy from the bucket. From the laptop with the bucket's credentials in the environment:

   ```
   cd backend
   .venv/Scripts/python -c "from app.s3put import S3
   for o in S3.from_settings().list('backups/'): print(o['key'])"
   ```

   then download the one you want with any S3 client, or from the Tigris console. Check it before
   uploading: `gunzip -k desert_watch_<day>.db.gz` and `sqlite3 desert_watch_<day>.db "PRAGMA quick_check"`.

2. Pause the scheduler (`flyctl secrets set DW_SCHEDULER=0`), which restarts the machine with no jobs.

3. Upload the gzip as the incoming file. From Git Bash, `MSYS_NO_PATHCONV=1` again:

   ```
   MSYS_NO_PATHCONV=1 flyctl ssh sftp put desert_watch_<day>.db.gz /data/incoming.db.gz
   flyctl ssh console -C "chown dw /data/incoming.db.gz"
   ```

4. Restart the machine: `flyctl machine restart <machine id>`. The log says
   `Loaded uploaded database from /data/incoming.db.gz`. `/health` answers, and the Sources page shows
   the runs up to the backup's day.

5. Turn the scheduler back on: `flyctl secrets unset DW_SCHEDULER`. The first hourly run collects
   what was published since the backup. Articles added by hand after the backup's day are gone and
   have to be added again.

## Local copies of production

`data/prod`, `data/snapshot` and `data/e2e` on the laptop hold copies of the production database,
with its user and behaviour rows. They are for rehearsing a data step on the `Desert Watch Rehearsal`
launch config. Delete a copy when the rehearsal is over, and never commit one.

## Restore drills

(none yet)
