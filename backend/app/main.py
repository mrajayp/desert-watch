import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import i18n, settings
from .api import account, admin, ai_audit, ai_panel, contribute, gaps, items, labelling, outlets, signals, social
from .db import SessionLocal, init_db
from .seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO. Some URLs carry keys, so request lines stay out of the log.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)
_state = {"scheduler": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as s:
        seed_all(s)
        s.commit()
    if settings.SCHEDULER_ENABLED:
        from .jobs import start_scheduler
        _state["scheduler"] = start_scheduler()
    yield
    if _state["scheduler"]:
        _state["scheduler"].shutdown(wait=False)


app = FastAPI(title="Desert Watch", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def interface_language(request: Request, call_next):
    """X-Lang from the browser decides the language of API text (?lang= is taken: it filters articles)."""
    token = i18n.set_lang(request.headers.get("x-lang"))
    try:
        return await call_next(request)
    finally:
        i18n.LANG.reset(token)


for r in (account.router, gaps.router, items.router, social.router, outlets.router, admin.router, contribute.router,
          labelling.router, signals.router, ai_audit.router, ai_panel.router):
    app.include_router(r)


@app.get("/health")
def health():
    """Fly's check. Only whether the process answers and the scheduler runs: it touches no table and
    never fails on a stale collector (on one machine a failing check stops routing and restarts
    nothing). The schedule, the lock holder, memory, disk and the backups are on /api/admin/health."""
    sched = _state["scheduler"]
    return {"ok": True, "scheduler": bool(sched and sched.running)}


app.mount("/geo", StaticFiles(directory=settings.CONFIG_DIR / "geo"), name="geo")

if settings.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = settings.FRONTEND_DIST / path
        if path and f.is_file() and settings.FRONTEND_DIST in f.resolve().parents:
            return FileResponse(f)
        # the page shell names the hashed bundle: browsers must ask again, or a deploy shows the old app
        return FileResponse(settings.FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
