"""python -m app.cli <command>

  init                      create tables + seed config
  create-admin EMAIL NAME   prompts for a password (or DW_ADMIN_PASSWORD)
  invite EMAIL [ROLE]       prints an invite path
  collect KEY [--weeks N] [--themes a,b]  run one collector (rss, gnews, gdelt, gdelt_timeline, wikipedia, ...)
  backfill [WEEKS]          gnews + wikipedia + gdelt history + rss
  recompute [--weeks N]     duplicates + scores + network + labels (the scheduler runs it as a child process)
  backup                    the nightly off-site database backup now (VACUUM INTO, quick_check, gzip, upload, prune)
  dedupe                    mark every duplicate copy of a story (full pass)
  mark-recurring [--days 30] [--min 3] [--since YYYY-MM-DD]  flag recurring posts (daily rates, weather...) so no count
                            treats them as stories: the same headline minus digits and weekdays, 3+ times within 30 days at
                            one outlet family. Judges the last 30 days; --since judges everything from that day (the rebuild)
  apply-theme-terms SLUG... copy only the term fields (terms, exclude, cooc, veto, mask) of these themes
                            from themes.yaml. Admin edits to names and other fields stay (sync-themes overwrites them)
  retag-all [--dry-run]     re-run the theme + place rules over every article, then the relevance guard
                            (--dry-run writes nothing and reports the same numbers)
  import-alignment-sources  alignment labels for Libyan TV channels from published studies (idempotent)
  alerts-list [DIR]         write the Google Alerts list (Markdown + CSV) to DIR (default: docs/)
  backfill-history SINCE [--themes a,b] [--step DAYS] [--until DATE]
                            Google News date-range backfill + paged outlet feeds + Wikipedia pageviews
  review [DIR] [--themes a,b]  data-quality summary + labelling sample (default DIR: docs/review)
  digest [--force]          generate the weekly AI digest (needs ANTHROPIC_API_KEY)
  import-backfill PATH [--max-ratio 0.2] [--limit N]  fetch + store cited article links from under-collected outlets
  reassign-social           move posts filed under a whole platform (facebook.com ...) to their page
  import-social-scrape PATH load the converted social-media scrape JSON (outlets, Facebook register, labels)
  label-register-pages      scope=libyan for the Facebook register pages (real scope for the few that are not Libyan)
  sync-themes               overwrite DB theme terms from config/themes.yaml (bumps versions, re-tags)
  import-search PATH        load Google Trends search rows (JSONL from scripts/fetch_gtrends.py, or a folder: its newest file)
  collect-search [--provider serpapi|official] [--daily]  fetch search rows with a keyed provider and load them
  repair-wiki-themes        file existing Wikipedia pageview days under every theme that lists the title
  wiki-reading [--since YYYY-MM-DD] [--until YYYY-MM-DD]  pages read in Libya on Wikipedia + page indicators
  fx-rates [--history] [--cbl-since YYYY-MM-DD]  dinar rates: parallel (Al-Mashhad) and official (central bank)
  import-fx-archive PATH    Libya Observer's rate box over time (Internet Archive JSONL), fills days with no value only
                            (Wikimedia's daily privacy-protected files, about 20 MB a day, days already stored are skipped)
  resolve-links [--days N] [--limit N] [--minutes N]  find the outlet's own link for Google News items
                            (default 14 days, at most 400 site searches and 15 minutes. Probes and post dates come on top of the searches)
  reach-snapshot [--limit N]            Tranco web rank for Libyan outlets + the 100 busiest (outlet.external['reach'])
  ai-audit [--provider anthropic|openai] [--force] [--dry-run [--json]] [--limit N] [--cap USD]
                            the weekly AI answers audit (config/ai_audit.yaml). --dry-run lists the planned answers
                            and the estimated cost and makes no call. --cap replaces the weekly cap for this run
  ai-audit-rematch          match the stored AI audit links to the outlet register again (after a register change)
  ai-panel-import FILE [--origin browser|panel] [--by EMAIL] [--country LY] [--dry-run]
                            log the source links of a supervised browser session (origin browser, the default:
                            asked from London). FILE is a JSON list of {question_key, lang, app, links, no_sources};
                            links is text or a list of URLs. Every entry is checked first: one bad entry stores none.
                            --by keeps an account as the author (it may then delete them). Answer text is never stored

theme model (app/ml):
  train-theme-model [--gold PATH] [--out PATH]  train base + small model and evaluate (LOCAL ONLY, ~1 GB RAM)
  register-model PATH [--activate] [--note TEXT]  copy a bundle to DATA_DIR/models and add it to the registry
  classify-items [--days N | --all] [--dry-run]  score articles with the live model and apply it (--reset undoes it)
  import-gold-labels PATH   blind review labels (jsonl) as silver theme_set labels (idempotent)
  train-small-model         refit the label-trained part of the live model; promote it if it does no worse
  model-status              live model, registry, labels per theme
  activate-model VERSION [--let-nightly] | rollback-model  live by hand; nightly versions then stay inactive

Commands that write data take the job lock (app/joblock.py) first, the same lock the scheduler's jobs
hold. If a scheduled job is running, the command says so and waits for it to finish.
Deploy steps, backups and restores: docs/DEPLOY.md.
"""
import getpass
import os
import sys

# Quick or read-only commands that do not wait for a running job. A --dry-run never waits either.
# ai-audit is not held for its whole run (the assistant calls take minutes): each answer's write takes
# the lock on its own, as the scheduled run does.
NO_LOCK = {"init", "create-admin", "invite", "review", "alerts-list", "model-status", "train-theme-model", "ai-audit"}
# Commands the scheduler runs as children: no seed_all, which would bring back deleted key events every hour.
NO_SEED = {"recompute"}


def _ai_audit_plan_text(res: list[dict]) -> str:
    """`ai-audit --dry-run` as a few readable lines: the plan per assistant, the estimate against the cap,
    what an assistant still waiting for its key would add, and why anything was skipped. No call is made."""
    from collections import Counter
    lines = []
    if not res:
        return "No country has AI audit questions (ai_audit.questions in config/countries/*.yaml)."
    for r in res:
        per = Counter(p["provider"] for p in r.get("planned", []))
        lines.append(f"{r.get('country')}  week from {r.get('week_start')}  cap USD {r.get('cap_usd', 0):.2f}"
                     f"  spent this week USD {r.get('spent_this_week_usd', 0):.4f}")
        for k, n in per.items():
            lines.append(f"  {k}: {n} answers planned")
        lines.append(f"  estimated USD {r.get('estimated_usd', 0):.4f} for {len(r.get('planned', []))} answers;"
                     f" {r.get('fits_cap', 0)} fit under the cap")
        for w in r.get("awaiting_key") or []:
            lines.append(f"  {w['provider']}: waiting for its API key; once set it adds {w['answers']} answers,"
                         f" about USD {w['estimated_usd']:.4f}")
        for sk in r.get("skipped") or []:
            lines.append(f"  skipped {sk.get('provider') or '(all)'}: {sk.get('reason')}")
    return "\n".join(lines)


def main(argv: list[str]):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    if cmd in NO_LOCK or "--dry-run" in args:
        return _run(cmd, args)
    from .joblock import held
    with held(note=lambda m: print(m, file=sys.stderr, flush=True), job=f"cli {cmd}"):
        return _run(cmd, args)


def _run(cmd: str, args: list[str]):
    from .db import SessionLocal, init_db
    from .seed import seed_all
    init_db()
    from .ml.commands import COMMANDS as ML_COMMANDS, run as run_ml
    if cmd in ML_COMMANDS:  # no seed_all: the scheduler runs these hourly, and seeding brings back deleted key events
        return run_ml(cmd, args)
    if cmd not in NO_SEED:
        with SessionLocal() as s:
            seed_all(s)
            s.commit()
    if cmd == "init":
        print("ok")
    elif cmd == "create-admin":
        from .auth import create_user
        email, name = args[0], " ".join(args[1:]) or "Admin"
        pw = os.environ.get("DW_ADMIN_PASSWORD") or getpass.getpass("Password (10+ chars): ")
        with SessionLocal() as s:
            create_user(s, email, pw, name, role="admin")
            s.commit()
        print("admin created")
    elif cmd == "invite":
        from .auth import create_invite
        with SessionLocal() as s:
            tok = create_invite(s, args[0], args[1] if len(args) > 1 else "journalist", None)
            s.commit()
        print(f"/invite/{tok}")
    elif cmd == "collect":
        from .jobs import collect
        kw = {}
        if "--weeks" in args:
            kw["weeks"] = int(args[args.index("--weeks") + 1])
        if "--days" in args:
            kw["days"] = int(args[args.index("--days") + 1])
        if "--themes" in args:
            kw["themes"] = args[args.index("--themes") + 1].split(",")
        print(collect(args[0], **kw))
    elif cmd == "backfill":
        from .jobs import backfill
        backfill(int(args[0]) if args else 12)
    elif cmd == "backfill-history":
        from datetime import date as _date
        from .jobs import collect
        since = _date.fromisoformat(args[0])
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        themes = opt("--themes").split(",") if opt("--themes") else None
        until = _date.fromisoformat(opt("--until")) if opt("--until") else None
        parts = opt("--parts", "gnews,rss,wikipedia").split(",")
        if "gnews" in parts:
            print("gnews", collect("gnews", start=since, end=until, step_days=int(opt("--step", "7")), themes=themes))
        if "rss" in parts:
            from .collectors import rss as rss_mod
            from .collectors.base import run_collector
            with SessionLocal() as s:
                run = run_collector(s, "rss_backfill", lambda sess: rss_mod.backfill(sess, since=since))
                print("rss_backfill", run.status, run.rows, run.error)
        if "official" in parts:
            print("official", collect("official", start=since, end=until, step_days=int(opt("--step", "14"))))
        if "wikipedia" in parts:
            print("wikipedia", collect("wikipedia", days=(_date.today() - since).days))
    elif cmd == "review":
        from pathlib import Path
        from . import settings
        from .review import run as run_review
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        out = Path(args[0]) if args and not args[0].startswith("--") else settings.REPO_ROOT / "docs" / "review"
        with SessionLocal() as s:
            print(run_review(s, out, theme_slugs=opt("--themes").split(",") if opt("--themes") else None))
    elif cmd == "apply-theme-terms":
        from .seed import apply_theme_terms
        if not args:
            print("usage: apply-theme-terms SLUG [SLUG ...]")
            return 1
        with SessionLocal() as s:
            changed = apply_theme_terms(s, args)
            s.commit()
        for slug, fields in changed.items():
            print(slug, ", ".join(fields) or "unchanged")
        if any(changed.values()):
            print("now run: retag-all")
    elif cmd == "retag-all":
        from .retag import retag_all
        with SessionLocal() as s:
            retag_all(s, dry_run="--dry-run" in args)
    elif cmd == "import-backfill":
        from pathlib import Path
        from .imports.backfill_links import run as run_backfill
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        with SessionLocal() as s:
            print(run_backfill(s, Path(args[0]), max_ratio=float(opt("--max-ratio") or 0.2),
                               limit=int(opt("--limit")) if opt("--limit") else None,
                               retry_failed="--retry-failed" in args))
    elif cmd == "reassign-social":
        from .ingest import reassign_social
        with SessionLocal() as s:
            print(reassign_social(s))
    elif cmd == "import-social-scrape":
        from pathlib import Path
        from .imports.social_scrape import run as run_import
        with SessionLocal() as s:
            print(run_import(s, Path(args[0])))
    elif cmd == "label-register-pages":
        from .imports.social_scrape import label_register_pages
        with SessionLocal() as s:
            print(label_register_pages(s))
    elif cmd == "digest":
        from .jobs import weekly_digest
        print(weekly_digest(force="--force" in args))
    elif cmd == "alerts-list":
        from pathlib import Path
        from . import settings
        from .alerts import sync_specs, write_list
        with SessionLocal() as s:
            sync_specs(s)
            md, csv_path = write_list(s, Path(args[0]) if args else settings.REPO_ROOT / "docs")
        print(md)
        print(csv_path)
    elif cmd == "sync-themes":
        import yaml
        from sqlalchemy import select
        from . import settings
        from .api.admin import _retag_theme
        from .models import Theme, utcnow
        data = yaml.safe_load(open(settings.CONFIG_DIR / "themes.yaml", encoding="utf-8"))
        print("sync-themes overwrites names, groups and terms edited in Admin (apply-theme-terms copies terms only)")
        changed = []
        with SessionLocal() as s:
            for t in data["themes"]:
                th = s.scalar(select(Theme).where(Theme.slug == t["slug"]))
                if not th:
                    th = Theme(slug=t["slug"], group=t.get("group"), name_en=t["name_en"], name_ar=t["name_ar"])
                    s.add(th)
                    s.flush()
                    changed.append(th.id)
                th.group, th.name_en, th.name_ar = t.get("group"), t["name_en"], t["name_ar"]
                new = {k: t.get(k, []) for k in ("en_terms", "ar_terms", "exclude", "cooc", "veto", "mask",
                                                 "cooc_veto_context", "acled_event_types", "reliefweb_themes")}
                new["strict"] = bool(t.get("strict", False))
                new["require_country"] = bool(t.get("require_country", False))
                # an empty list and NULL are the same (veto and mask are NULL on older rows)
                if th.id in changed or any((getattr(th, k) or ([] if isinstance(v, list) else False)) != v
                                           for k, v in new.items()):
                    for k, v in new.items():
                        setattr(th, k, v)
                    th.version += 1
                    th.updated_at = utcnow()
                    if th.id not in changed:
                        changed.append(th.id)
            s.commit()
        for tid in changed:
            _retag_theme(tid, recompute=False)
        print(f"updated {len(changed)} themes")
    elif cmd == "import-search":
        from pathlib import Path
        from .imports.search_trends import run as run_search
        with SessionLocal() as s:
            print(run_search(s, Path(args[0])))
    elif cmd == "collect-search":
        from .collectors.gtrends import collect_and_import
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        with SessionLocal() as s:
            print(collect_and_import(s, provider=opt("--provider", "serpapi"), daily="--daily" in args))
    elif cmd == "import-alignment-sources":
        from .imports.alignment_sources import run as run_align
        with SessionLocal() as s:
            print(run_align(s))
    elif cmd == "import-fx-archive":
        from .collectors.fxrate import import_archive
        with SessionLocal() as s:
            print(import_archive(s, args[0]))
    elif cmd == "fx-rates":
        from datetime import date
        from .collectors.fxrate import run as run_fx
        since = date.fromisoformat(args[args.index("--cbl-since") + 1]) if "--cbl-since" in args else None
        with SessionLocal() as s:
            print(run_fx(s, history="--history" in args, cbl_since=since))
    elif cmd == "wiki-reading":
        from datetime import date, timedelta
        from .collectors.wikireading import run as run_reading
        since = date.fromisoformat(args[args.index("--since") + 1]) if "--since" in args else date.today() - timedelta(days=7)
        until = date.fromisoformat(args[args.index("--until") + 1]) if "--until" in args else date.today() - timedelta(days=1)
        with SessionLocal() as s:
            res = run_reading(s, since, until, out=lambda r: print(r, flush=True))
        print({k: v for k, v in res.items() if k != "days"})
    elif cmd == "repair-wiki-themes":
        from .collectors.wikipedia import repair_themes
        with SessionLocal() as s:
            print(repair_themes(s), "theme links added")
    elif cmd == "dedupe":
        from .dedupe import mark_duplicates
        with SessionLocal() as s:
            print(mark_duplicates(s), "articles marked as duplicates")
    elif cmd == "mark-recurring":
        import json
        from datetime import datetime as _datetime
        from .recurring import RECUR_DAYS, RECUR_MIN, mark_recurring
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        since = _datetime.fromisoformat(opt("--since")) if opt("--since") else None
        with SessionLocal() as s:
            print(json.dumps(mark_recurring(s, days=int(opt("--days", RECUR_DAYS)), min_repeats=int(opt("--min", RECUR_MIN)),
                                            since=since)))
    elif cmd == "resolve-links":
        import json
        from .resolve import run as run_resolve
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        with SessionLocal() as s:
            print(json.dumps(run_resolve(s, days=int(opt("--days", "14")), limit=int(opt("--limit", "400")),
                                         minutes=float(opt("--minutes", "15"))),
                             ensure_ascii=False, indent=1))
    elif cmd == "reach-snapshot":
        import json
        from .reach import snapshot
        with SessionLocal() as s:
            print(json.dumps(snapshot(s, limit=int(args[args.index("--limit") + 1]) if "--limit" in args else None),
                             ensure_ascii=False, indent=1))
    elif cmd == "ai-audit":
        import json
        from .ai_audit.runner import run_all
        from .joblock import JobLock
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        res = run_all(provider=opt("--provider"), force="--force" in args, dry_run="--dry-run" in args,
                      limit=int(opt("--limit")) if opt("--limit") else None,
                      cap=float(opt("--cap")) if opt("--cap") else None, lock=JobLock("cli ai-audit"))
        if "--dry-run" in args and "--json" not in args:
            print(_ai_audit_plan_text(res))
        else:
            print(json.dumps(res, ensure_ascii=False, indent=1))
    elif cmd == "ai-audit-rematch":
        from .ai_audit.matcher import rematch
        with SessionLocal() as s:
            print(rematch(s))
    elif cmd == "ai-panel-import":
        import json
        from pathlib import Path
        from .api.ai_panel import import_entries
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
        if not args or args[0].startswith("--"):
            print("usage: ai-panel-import FILE [--origin browser|panel] [--by EMAIL] [--country LY] [--dry-run]")
            return 1
        items = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        with SessionLocal() as s:
            res = import_entries(s, items, origin=opt("--origin", "browser"), country=opt("--country", "LY"),
                                 by=opt("--by"), dry_run="--dry-run" in args)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if res.get("errors"):
            return 1
    elif cmd == "recompute":
        import json
        from .jobs import recompute
        n = recompute(weeks=int(args[args.index("--weeks") + 1]) if "--weeks" in args else None)
        print(json.dumps({"cells": n, "changed": n}))   # the last line is what the scheduler's child_job reads
    elif cmd == "backup":
        from .jobs import backup
        print(backup())
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
