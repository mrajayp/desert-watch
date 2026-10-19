"""Theme-model commands for app.cli. Each prints a JSON summary as its last line; jobs.py reads it
back when it runs a command in a child process."""
import json
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings
from ..models import Item, ItemTheme, Label, ModelRegistry, Theme, utcnow
from . import labels as L
from . import registry

COMMANDS = ("train-theme-model", "register-model", "classify-items", "import-gold-labels", "train-small-model",
            "model-status", "activate-model", "rollback-model")


def _opt(args: list[str], k: str, d=None):
    return args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else d


def _f(m: dict) -> str:
    return f"{m['p']:.2f}/{m['r']:.2f}/{m['f1']:.2f}"


def print_metrics(metrics: dict) -> None:
    print(f"evaluated on {metrics['eval_items']} items ({metrics.get('eval_set', '')}); {metrics['method']}")
    print(f"{'theme':32s} {'pos':>4s} {'rules P/R/F1':>15s} {'links today':>15s} {'model':>15s} {'t':>5s} gate")
    for sl, m in metrics["themes"].items():
        gate = "" if "gate" not in m else ("on" if m["gate"] else "off")
        print(f"{sl:32s} {m['eval_positives']:4d} {_f(m['rules']):>15s} {_f(m['links_today']):>15s} "
              f"{_f(m['model']):>15s} {m['threshold']:5.2f} {gate}")
    for grp, d in metrics["macro"].items():
        if d["model"]["f1"] is not None:
            print(f"macro {grp:26s}      {_f(d['rules']):>15s} {_f(d['links_today']):>15s} {_f(d['model']):>15s}")


def train_theme_model(s: Session, args: list[str]) -> dict:
    from .train import save_bundle, train_full
    gold = _opt(args, "--gold")
    out = Path(_opt(args, "--out") or settings.DATA_DIR / "models")
    t0 = time.time()
    b = train_full(s, Path(gold) if gold else None, n_keep=int(_opt(args, "--features", "50000")))
    path = out if out.suffix == ".joblib" else out / f"{b['version']}.joblib"
    save_bundle(b, path)
    mpath = path.with_name(path.stem + ".metrics.json")
    mpath.write_text(json.dumps({"version": b["version"], "trained_on": b["trained_on"], "thresholds": b["thresholds"],
                                 "gates": b["gates"], "metrics": b["metrics"]}, indent=1, default=str), encoding="utf-8")
    print_metrics(b["metrics"])
    return {"version": b["version"], "bundle": path.as_posix(), "metrics": mpath.as_posix(),
            "seconds": round(time.time() - t0), "macro": b["metrics"]["macro"]}


def register_model(s: Session, args: list[str]) -> dict:
    """register-model PATH [--activate] [--note TEXT]. Running it again with the same file does nothing,
    so a deploy script can be re-run; the same version with a different file is an error."""
    from .infer import load_bundle
    from .train import bundle_meta
    path = Path(args[0])
    meta = bundle_meta(load_bundle(path))
    have = registry.get(s, meta["version"])
    if have is not None and registry.same_file(have, path):
        print(f"{have.version} is already registered with this file"
              f"{'' if have.active else ' (it is not live: activate-model makes it live)'}")
        return {"version": have.version, "path": have.path, "active": have.active, "already_registered": True,
                "changed": 0}
    row = registry.register(s, path, meta, activate_now="--activate" in args, note=_opt(args, "--note"))
    s.commit()
    return {"version": row.version, "path": row.path, "active": row.active, "changed": 1}


def _model(s: Session, path: str | None):
    from .infer import ThemeModel
    if path:
        return ThemeModel.load(path)
    row = registry.active(s)
    if not row:
        return None
    m = ThemeModel.load(row.path)
    m.version = row.version
    return m


def classify_items_cmd(s: Session, args: list[str]) -> dict:
    from .infer import classify_items, reset_model_links
    if "--reset" in args:
        out = reset_model_links(s)
        print("Model links are back to what they were. Run retag-all next: it turns a link back on wherever the "
              "rules match it.")
        return {**out, "changed": sum(out.values()), "next": "retag-all"}
    model = _model(s, _opt(args, "--model"))
    if model is None:
        return {"skipped": "no active theme model", "changed": 0}
    since = None if "--all" in args else utcnow() - timedelta(days=int(_opt(args, "--days", "3")))
    t0 = time.time()
    res = classify_items(s, model, since=since, dry_run="--dry-run" in args,
                         catch_up=int(_opt(args, "--catch-up", "0")), log=print if "--verbose" in args else None)
    res["seconds"] = round(time.time() - t0, 1)
    acts = ("above", "added", "removed", "vetoed", "unvetoed", "unchanged")
    print(f"{res['items']} items ({res['caught_up']} older ones the live version had not scored), "
          f"model {res['version']}{' (dry run)' if res['dry_run'] else ''}, {res['seconds']}s")
    print(f"{'theme':32s} " + " ".join(f"{a:>9s}" for a in acts))
    for sl, c in res["themes"].items():
        print(f"{sl:32s} " + " ".join(f"{c.get(a, 0):9d}" for a in acts))
    res["changed"] = sum(c.get(a, 0) for c in res["themes"].values() for a in ("added", "removed", "vetoed", "unvetoed"))
    return res


def import_gold_labels(s: Session, args: list[str]) -> dict:
    """Blind review labels as silver theme_set labels. Idempotent (source_ref = <tag>:<item id>)."""
    path = Path(args[0])
    tag = L.gold_tag(path.name)
    of = [t.slug for t in s.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id))]
    rows = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    have = set()
    ids = [int(r["item_id"]) for r in rows]
    for i in range(0, len(ids), 900):
        have |= set(s.scalars(select(Item.id).where(Item.id.in_(ids[i:i + 900]))))
    done = set(s.scalars(select(Label.source_ref).where(Label.source_ref.like(f"{tag}:%"))))
    added = skipped = present = 0
    for r in rows:
        iid, ref = int(r["item_id"]), f"{tag}:{int(r['item_id'])}"
        if iid not in have:
            skipped += 1
            continue
        if ref in done:
            present += 1
            continue
        s.add(Label(label_type="theme_set", object_type="item", object_key=str(iid), origin="silver", weight=0.5,
                    source_ref=ref, value={"themes": [t for t in r.get("themes", []) if t in of],
                                           "libya": r.get("libya"), "of": of}))
        done.add(ref)
        added += 1
    s.commit()
    return {"added": added, "already_there": present, "skipped_not_in_db": skipped, "changed": added}


def train_small_model(s: Session, args: list[str]) -> dict:
    """Nightly: retrain the label-trained part on top of the live version. It goes live only if it
    passes the check and the live version was not picked by hand."""
    row = registry.active(s)
    if not row:
        return {"skipped": "no active theme model", "changed": 0}
    seen = [f for r in s.scalars(select(ModelRegistry)) if (r.trained_on or {}).get("small_from") == row.version
            and (f := ((r.trained_on or {}).get("labels") or {}).get("fingerprint"))]
    # nothing new since the live version or the last check: stop before scikit-learn and the bundle are loaded
    fp = L.labels_fingerprint(s)
    if fp == ((row.trained_on or {}).get("labels") or {}).get("fingerprint") or fp in [list(f) for f in seen]:
        return {"skipped": "no new labels since the live model or the last check", "live": row.version, "changed": 0}
    from .infer import load_bundle
    from .train import bundle_meta, retrain_small, save_bundle
    cand, decision = retrain_small(s, load_bundle(row.path), seen=seen)
    if cand is None:
        return {**decision, "live": row.version, "changed": 0}
    pinned = registry.is_pinned(row)
    promote = decision["promote"] and not pinned
    path = save_bundle(cand, registry.models_dir() / f"{cand['version']}.joblib")
    if promote:
        note = "promoted: " + decision["reason"]
    elif pinned and decision["promote"]:
        note = f"kept inactive: {row.version} was made live by hand (it passed the check: {decision['reason']})"
    else:
        note = "kept inactive: " + decision["reason"]
    registry.register(s, path, bundle_meta(cand), activate_now=promote, note=note)
    removed = registry.prune(s)
    s.commit()
    print(note)
    return {"version": cand["version"], "promoted": promote, "reason": decision["reason"], "pinned": pinned,
            "live": cand["version"] if promote else row.version, "files_removed": removed, "changed": 1}


def model_status(s: Session, args: list[str]) -> dict:
    act = registry.active(s)
    themes = s.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)).all()
    stats = L.theme_stats(L.item_vectors(s, themes), themes)
    links = {f"{m}{'' if a else ' (off)'}": n for m, a, n in s.execute(
        select(ItemTheme.method, ItemTheme.active, func.count()).group_by(ItemTheme.method, ItemTheme.active))}
    vetoed = s.scalar(select(func.count()).where(ItemTheme.method == "rule", ItemTheme.active.is_(False),
                                                 func.json_extract(ItemTheme.evidence, "$.veto").is_not(None)))
    by_origin = dict(s.execute(select(Label.origin, func.count()).where(Label.label_type.in_(L.THEME_LABELS))
                               .group_by(Label.origin)).all())
    people = L.theme_stats(L.item_vectors(s, themes), themes, people_only=True)
    print(f"live model: {act.version if act else 'none'}{' (made live by hand)' if registry.is_pinned(act) else ''}")
    for r in registry.summary(s):
        print(f"  {'*' if r['active'] else ' '} {r['version']}  {r['created_at'][:16]}  "
              f"{'' if r['file'] else '(file removed) '}{r['note'] or ''}")
    print("labels per theme (labelled / positives): " + ", ".join(f"{k} {v['labelled']}/{v['positives']}" for k, v in stats.items()))
    print("people's labels, gender themes (gate needs 100 / 10): " + ", ".join(
        f"{t.slug} {people[t.slug]['labelled']}/{people[t.slug]['positives']}" for t in themes if t.group == "gender"))
    print(f"links: {links}; vetoed rule links: {vetoed}")
    return {"active": act.version if act else None, "pinned": registry.is_pinned(act),
            "gates": (act.metrics or {}).get("themes") and {
                k: bool(v["gate"]) and "people" in v for k, v in act.metrics["themes"].items() if "gate" in v} if act else None,
            "labels_by_origin": by_origin, "theme_labels": stats, "people_labels": people, "links": links,
            "vetoed": vetoed}


def activate_model(s: Session, args: list[str]) -> dict:
    """activate-model VERSION [--let-nightly]: by hand, so the version is pinned unless --let-nightly."""
    was = registry.active(s)
    was_version = was.version if was else None
    row = registry.activate(s, args[0], by_hand="--let-nightly" not in args)
    s.commit()
    out = {"active": row.version, "pinned": registry.is_pinned(row), "changed": int(was_version != row.version)}
    return {**out, "next": "classify-items --all"} if out["changed"] else out


def rollback_model(s: Session, args: list[str]) -> dict:
    row = registry.rollback(s)
    s.commit()
    return {"active": row.version if row else None, "pinned": registry.is_pinned(row), "changed": int(row is not None),
            "next": "classify-items --all"}


HANDLERS = {"train-theme-model": train_theme_model, "register-model": register_model,
            "classify-items": classify_items_cmd, "import-gold-labels": import_gold_labels,
            "train-small-model": train_small_model, "model-status": model_status,
            "activate-model": activate_model, "rollback-model": rollback_model}


def run(cmd: str, args: list[str]) -> int:
    from ..db import SessionLocal
    with SessionLocal() as s:
        out = HANDLERS[cmd](s, args)
    print(json.dumps(out, default=str, ensure_ascii=False))
    return 0
