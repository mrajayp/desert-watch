"""python -m app.cli <command>

  init                      create tables + seed config
  create-admin EMAIL NAME   prompts for a password (or DW_ADMIN_PASSWORD)
  invite EMAIL [ROLE]       prints an invite path
  collect KEY [--weeks N]   run one collector (rss, gnews, gdelt, gdelt_timeline, wikipedia, ...)
  backfill [WEEKS]          gnews + wikipedia + gdelt history + rss
  recompute                 scores + network + labels
  alerts-list [DIR]         write the Google Alerts list (Markdown + CSV) to DIR (default: docs/)
  backfill-history SINCE [--themes a,b] [--step DAYS] [--until DATE]
                            Google News date-range backfill + paged outlet feeds + Wikipedia pageviews
  review [DIR] [--themes a,b]  data-quality summary + labelling sample (default DIR: docs/review)
  digest [--force]          generate the weekly AI digest (needs ANTHROPIC_API_KEY)
  import-social-scrape PATH load the converted social-media scrape JSON (outlets, Facebook register, labels)
  sync-themes               overwrite DB theme terms from config/themes.yaml (bumps versions, re-tags)
"""
import getpass
import os
import sys

from .db import SessionLocal, init_db
from .seed import seed_all


def main(argv: list[str]):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    init_db()
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
    elif cmd == "import-social-scrape":
        from pathlib import Path
        from .imports.social_scrape import run as run_import
        with SessionLocal() as s:
            print(run_import(s, Path(args[0])))
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
                new = {k: t.get(k, []) for k in ("en_terms", "ar_terms", "exclude", "cooc", "acled_event_types", "reliefweb_themes")}
                new["strict"] = bool(t.get("strict", False))
                new["require_country"] = bool(t.get("require_country", False))
                if th.id in changed or any(getattr(th, k) != v for k, v in new.items()):
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
    elif cmd == "recompute":
        from .jobs import recompute
        print(recompute(weeks=int(args[args.index("--weeks") + 1]) if "--weeks" in args else None), "cells")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
