# Desert Watch

Finds **information deserts**: topics and places where there is evidence of need
(events, humanitarian reporting, audience interest, journalists' own flags) but little
monitored media coverage. Built for journalists deciding what to cover. Libya first;
countries and themes are config.

Plan and rationale: `C:\Users\paler\.claude\plans\i-want-to-create-atomic-lamport.md`.

## How it works

| Step | Where | Notes |
|---|---|---|
| Collect coverage | `backend/app/collectors/` | Google News RSS (Arabic + English), outlet RSS, GDELT (English translations only). No keys needed. |
| Collect need | same | Wikipedia pageviews now; ACLED / UCDP / ReliefWeb switch on when keys are set (`ACLED_EMAIL`+`ACLED_PASSWORD`, `UCDP_TOKEN`, `RELIEFWEB_APPNAME`). |
| Tag | `classify.py`, `ingest.py` | Arabic-normalised keyword rules per theme; place-name tagging to 22 districts and 3 regions; relevance guard (must name Libya / a Libyan place or come from a Libyan outlet). |
| Score | `scoring.py` | Per theme × region × week × lens, 4-week window: `gap = ln(reference ratio / shrunk coverage ratio)`. Insufficient evidence, cold start and partial windows are never scored. |
| Network | `network.py` | Outlet→district and outlet→theme edges per week, outlet similarity on theme specialisation (Louvain clusters), reprint detection on headlines. |
| Engagement | `engagement.py`, `resolve.py`, `reach.py`, `collectors/fb_engagement.py` | Story pickup (outlets per story) on every network run. Nightly: outlet URLs for Google News links (`resolve-links`). Facebook link engagement at ~48 h and ~7 days once `DW_FB_APP_ID`+`DW_FB_APP_SECRET` are set. Monthly: Tranco web rank per outlet (`reach-snapshot`). Never compared raw across outlets. |
| Learn | `learning.py` | Behaviour log (pseudonymous; no opt-out since 2026-10-13, users are told at first login) + explicit actions → `label` table. Models switch on above label thresholds (Phase 5). |
| UI | `frontend/` | React + D3. Map/network ("who covers where"), heatmap, trends, outlets network, gap/item/outlet panels with votes, comments, corrections, assessments. |

LLM use: none yet. The weekly digest (Phase 6) is the only planned use.

## Run locally

```bash
cd backend && uv sync --python 3.13 && .venv/Scripts/python -m app.cli init
.venv/Scripts/python -m app.cli create-admin you@example.org "Your Name"
.venv/Scripts/python -m app.cli backfill 12      # ~15 min: Google News, Wikipedia, GDELT history, RSS
.venv/Scripts/python -m app.cli recompute
cd ../frontend && npm install && npm run build
cd ../backend && .venv/Scripts/python -m uvicorn app.main:app --port 8090
```

Search lens (Google Trends): fetch on your own machine about once a week, never on the server. Each run
writes a new file that holds the whole 5-year series, so only the newest one is needed. Upload that file
where the app runs (like the backfill JSON), load it and recompute. Older files can be deleted.

```bash
cd backend && .venv/Scripts/python scripts/fetch_gtrends.py   # 5 requests, 10 s apart -> ../data/imports/gtrends/gtrends-<UTC time>.jsonl
.venv/Scripts/python -m app.cli import-search ../data/imports/gtrends   # a folder loads its newest file
.venv/Scripts/python -m app.cli recompute --weeks 12
```

If Google turns the fetcher away twice it stops and will not run again for 24 hours (`--force` overrides).

Dev frontend with hot reload: `npm run dev` (port 5190, proxies `/api` to 8090).
Tests: `cd backend && .venv/Scripts/python -m pytest -q`.

## Known limits (by design, shown in the UI)

- Coverage = **monitored** coverage. Facebook/Telegram-only reporting is invisible; journalists add it with "Add article" / "Already covered".
- Google News returns ≤100 results per query; windows are split down to one day when capped, and remaining capped days are reported in the source health strip.
- GDELT throttles aggressively (1 request / 5 s, and sometimes blocks); the app runs without it.
- Outlet base locations and political alignment are not seeded: they are contested and must be added with evidence.
- The audience lens is national-only; regional gaps need the events / humanitarian lenses (keys pending).
- The search lens is national-only and measures economy, services, health and governance. Migration, security and the gender themes fall below Google's privacy threshold or follow foreign news (see `gtrends` in `config/countries/libya.yaml`).
