"""Model registry: bundles live on the data volume (DATA_DIR/models/<version>.joblib), one
ModelRegistry row per version, exactly one active per kind. Plain Python (no joblib here):
callers that read a bundle pass its metadata in.

A version made live by hand (Admin > Activate, activate-model, rollback-model) is pinned: the
nightly retrain still builds and checks new versions but keeps them inactive until an admin
activates one or lets nightly updates take over again. Activation state lives in trained_on:
activated (timestamps), pinned (live by hand now), by_hand (was ever picked by hand)."""
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings
from ..models import ModelRegistry, utcnow

KIND = "theme"
KEEP_NIGHTLY = 5  # nightly versions kept on disk besides the live one and hand-picked ones


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


def has_file(r: ModelRegistry) -> bool:
    return bool(r.path) and Path(r.path).exists()


def is_pinned(r: ModelRegistry | None) -> bool:
    return bool(r and (r.trained_on or {}).get("pinned"))


def activate(s: Session, version: str, *, by_hand: bool = False) -> ModelRegistry:
    """Make a version live. by_hand pins it (see the module note); an automatic promotion does not."""
    row = get(s, version)
    if not row:
        raise ValueError(f"unknown model version {version}")
    if not has_file(row):
        raise FileNotFoundError(f"the bundle file of {version} was removed")
    was_live = row.active
    for other in s.scalars(select(ModelRegistry).where(ModelRegistry.kind == row.kind, ModelRegistry.active.is_(True))):
        other.active = False
        other.trained_on = {**(other.trained_on or {}), "pinned": False}
    row.active = True
    t = dict(row.trained_on or {})
    if not was_live:  # activation history, so a rollback goes back to the version that was really live before
        t["activated"] = [*t.get("activated", []), utcnow().isoformat()]
    t["pinned"] = by_hand
    if by_hand:
        t["by_hand"] = True
    row.trained_on = t
    s.flush()
    return row


def set_pinned(s: Session, pinned: bool, kind: str = KIND) -> ModelRegistry | None:
    row = active(s, kind)
    if row:
        row.trained_on = {**(row.trained_on or {}), "pinned": pinned, **({"by_hand": True} if pinned else {})}
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
        and max(r.trained_on["activated"]) <= since and has_file(r)]
    if not earlier:
        return None
    prev = max(earlier, key=lambda x: (x[0], x[1]))[2]
    return activate(s, prev.version, by_hand=True)


def prune(s: Session, keep: int = KEEP_NIGHTLY, kind: str = KIND) -> list[str]:
    """Delete the bundle files of old nightly versions ('-small'): all but the newest `keep`, never the
    live one, never one picked by hand. Their registry rows stay, marked as having no file."""
    removed = []
    nightly = [r for r in s.scalars(select(ModelRegistry).where(ModelRegistry.kind == kind)
                                    .order_by(ModelRegistry.id.desc())) if r.version.endswith("-small")]
    for r in nightly[keep:]:
        if r.active or (r.trained_on or {}).get("by_hand") or not has_file(r):
            continue
        Path(r.path).unlink()
        r.trained_on = {**(r.trained_on or {}), "file_removed": utcnow().date().isoformat()}
        removed.append(r.version)
    s.flush()
    return removed


def row_json(r: ModelRegistry) -> dict:
    return {"version": r.version, "kind": r.kind, "active": r.active, "created_at": r.created_at.isoformat(),
            "path": r.path, "trained_on": r.trained_on, "metrics": r.metrics, "thresholds": r.thresholds, "note": r.note,
            "pinned": is_pinned(r), "file": has_file(r)}


def summary(s: Session, kind: str = KIND) -> list[dict]:
    """Registry rows, newest first, without the per-theme detail (for the learning overview)."""
    out = []
    for r in s.scalars(select(ModelRegistry).where(ModelRegistry.kind == kind).order_by(ModelRegistry.id.desc())):
        m = r.metrics or {}
        out.append({"version": r.version, "active": r.active, "created_at": r.created_at.isoformat(),
                    "macro": m.get("macro"), "labels": (r.trained_on or {}).get("labels"), "note": r.note,
                    "pinned": is_pinned(r), "file": has_file(r)})
    return out
