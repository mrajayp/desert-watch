"""Model registry: bundles live on the data volume (DATA_DIR/models/<version>.joblib), one
ModelRegistry row per version, exactly one active per kind. Plain Python (no joblib here):
callers that read a bundle pass its metadata in."""
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings
from ..models import ModelRegistry, utcnow

KIND = "theme"


def models_dir() -> Path:
    return settings.DATA_DIR / "models"


def active(s: Session, kind: str = KIND) -> ModelRegistry | None:
    return s.scalar(select(ModelRegistry).where(ModelRegistry.kind == kind, ModelRegistry.active.is_(True))
                    .order_by(ModelRegistry.id.desc()).limit(1))


def get(s: Session, version: str) -> ModelRegistry | None:
    return s.scalar(select(ModelRegistry).where(ModelRegistry.version == version))


def register(s: Session, path: Path, meta: dict, *, activate_now: bool = False, note: str | None = None,
             kind: str = KIND) -> ModelRegistry:
    """Copy the bundle into the models folder and add its row. meta: version, trained_on, metrics,
    thresholds (from the bundle)."""
    version = meta["version"]
    if get(s, version):
        raise ValueError(f"version {version} is already registered")
    dest = models_dir() / f"{version}.joblib"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(path).resolve() != dest.resolve():
        shutil.copyfile(path, dest)
    row = ModelRegistry(kind=kind, version=version, path=dest.as_posix(), trained_on=meta.get("trained_on") or {},
                        metrics=meta.get("metrics") or {}, thresholds=meta.get("thresholds") or {}, active=False,
                        note=note)
    s.add(row)
    s.flush()
    if activate_now:
        activate(s, version)
    return row


def activate(s: Session, version: str) -> ModelRegistry:
    row = get(s, version)
    if not row:
        raise ValueError(f"unknown model version {version}")
    for other in s.scalars(select(ModelRegistry).where(ModelRegistry.kind == row.kind, ModelRegistry.active.is_(True))):
        other.active = False
    row.active = True
    # activation history, so a rollback goes back to the version that was really live before
    row.trained_on = {**(row.trained_on or {}), "activated": [*(row.trained_on or {}).get("activated", []),
                                                            utcnow().isoformat()]}
    s.flush()
    return row


def rollback(s: Session, kind: str = KIND) -> ModelRegistry | None:
    """Re-activate the version that was active before the current one (None if there is none)."""
    cur = active(s, kind)
    if not cur:
        return None
    since = max((cur.trained_on or {}).get("activated", [""]))
    earlier = [(max(r.trained_on["activated"]), r.id, r) for r in s.scalars(select(ModelRegistry).where(
        ModelRegistry.kind == kind, ModelRegistry.id != cur.id)) if (r.trained_on or {}).get("activated")
        and max(r.trained_on["activated"]) <= since]
    if not earlier:
        return None
    prev = max(earlier, key=lambda x: (x[0], x[1]))[2]
    return activate(s, prev.version)


def row_json(r: ModelRegistry) -> dict:
    return {"version": r.version, "kind": r.kind, "active": r.active, "created_at": r.created_at.isoformat(),
            "path": r.path, "trained_on": r.trained_on, "metrics": r.metrics, "thresholds": r.thresholds, "note": r.note}


def summary(s: Session, kind: str = KIND) -> list[dict]:
    """Registry rows, newest first, without the per-theme detail (for the learning overview)."""
    out = []
    for r in s.scalars(select(ModelRegistry).where(ModelRegistry.kind == kind).order_by(ModelRegistry.id.desc())):
        m = r.metrics or {}
        out.append({"version": r.version, "active": r.active, "created_at": r.created_at.isoformat(),
                    "macro": m.get("macro"), "labels": (r.trained_on or {}).get("labels"), "note": r.note})
    return out
