import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import settings
from .api import account, admin, contribute, gaps, items, labelling, outlets, social
from .db import SessionLocal, init_db
from .models import SourceRun
from .seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
for r in (account.router, gaps.router, items.router, social.router, outlets.router, admin.router, contribute.router,
          labelling.router):
    app.include_router(r)


@app.get("/health")
def health():
    sched = _state["scheduler"]
    with SessionLocal() as s:
        last = s.scalar(select(func.max(SourceRun.started_at)))
    return {"ok": True, "scheduler": bool(sched and sched.running),
            "next_runs": [str(j.next_run_time) for j in sched.get_jobs()] if sched else [],
            "last_collector_run": last.isoformat() if last else None}


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
        return FileResponse(settings.FRONTEND_DIST / "index.html")
