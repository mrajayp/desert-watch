"""Training and honest evaluation of the theme model.

base   per theme LogisticRegression(C=4, balanced) on weak labels (active rule links = 1, no link or a
       switched-off rule link = 0, search-only and model links left out), TF-IDF char_wb 2-5 + word
       1-2, pruned to the 50,000 features with the largest |coef| and refit on that vocabulary.
       Heavy (about 1 GB on the production data): run it locally, never on the server.
small  same features, trained only on labelled items (people's labels, silver labels).
       Blended p = 0.5 base + 0.5 small for themes with >= 10 positive labels, else base only.
Evaluation never lets an item score itself: the small model is cross-fitted (5 folds) over the
labelled items, and thresholds are tuned by repeated 2-fold CV on those out-of-fold scores.
Gender themes: the veto gate, the gender thresholds and the gender check before a new version goes
live use people's labels only (origin 'explicit'), never the silver review labels.
New versions are compared with the live one on a fixed reference set (the review labels), each
side scored honestly when it was trained."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from math import sqrt
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..classify import clean_snippet
from ..ingest import Rules, load_rules, theme_hits
from ..models import Country, Item, ItemTheme, Theme, utcnow
from ..textnorm import normalise
from . import labels as L
from .features import Features, item_text
from .infer import ThemeModel, _sigmoid

C = 4.0
N_KEEP = 50_000
BLEND = 0.5
MIN_POS_BASE = 3
MIN_POS_SMALL = 10                  # positive labels before the small model joins the blend
GATE_ITEMS, GATE_POS = 100, 10      # gender veto gate (labelled items, positives)
NEW_LABELS_FOR_THRESHOLDS = 100     # keep the live thresholds until this many new labelled items
FOLDS, REPS = 5, 20
GRID = np.round(np.concatenate([[0.01, 0.02, 0.03, 0.04], np.arange(0.05, 0.96, 0.025)]), 3)
SINCE = datetime(2024, 1, 1)
SILVER_WEIGHT = 0.5


def _log(msg):
    print(msg, flush=True)


def model_themes(s: Session) -> list[Theme]:
    return s.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)).all()


def new_version(suffix: str = "") -> str:
    return "theme-" + utcnow().strftime("%Y%m%d-%H%M%S") + suffix


def _chunks(xs, n=900):
    xs = list(xs)
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ---------------------------------------------------------------- rules (the 'rule' half of the decision)
def country_rules(s: Session) -> Rules:
    cid = s.scalar(select(Country.id).where(Country.iso2 == "LY")) or s.scalar(select(Country.id).limit(1))
    return load_rules(s, cid)


def rule_hits(rules: Rules, title: str | None, snippet: str | None, source_key: str | None = None) -> set[int]:
    """Theme ids the keyword rules give this article, exactly as production applies them
    (ingest.theme_hits: title first, the cleaned snippet, require_country), so the evaluation and
    the tuned thresholds describe the rules that actually run. Same result as ingest.item_hits."""
    return set(theme_hits(rules, title, clean_snippet(source_key, title, snippet)))


# ---------------------------------------------------------------- fitting
def fit_themes(X, Y: np.ndarray, W: np.ndarray | None = None, *, small: bool = False, min_pos: int = MIN_POS_BASE):
    """One LogisticRegression per column of Y (1 / 0, -1 = left out). Returns (coef, intercept, has)."""
    k = Y.shape[1]

    def one(j):
        m = Y[:, j] >= 0
        y = Y[m, j]
        if y.sum() < min_pos or y.sum() == len(y):
            return None
        lr = (LogisticRegression(C=C, class_weight="balanced", max_iter=3000) if small else
              LogisticRegression(C=C, class_weight="balanced", solver="liblinear", max_iter=200))
        lr.fit(X[m], y, sample_weight=None if W is None else W[m, j])
        return lr

    with ThreadPoolExecutor(int(os.environ.get("DW_NJOBS", "4"))) as ex:
        ms = list(ex.map(one, range(k)))
    coef = np.vstack([m.coef_[0] if m is not None else np.zeros(X.shape[1]) for m in ms]).astype(np.float32)
    icp = np.array([m.intercept_[0] if m is not None else -30.0 for m in ms], dtype=np.float32)
    return coef, icp, np.array([m is not None for m in ms])


# ---------------------------------------------------------------- base model (offline)
def _weak(method: str, active: bool, evidence: dict | None) -> int:
    if method in ("rule", "user"):
        if active:
            return 1
        return -1 if (evidence or {}).get("veto") is not None else 0
    return -1  # search or model links: nothing in the text the rules accept, so leave them out


def weak_pool(s: Session, themes: list[Theme], exclude_ids: set[int], exclude_titles: set[str], since: datetime = SINCE):
    k_of = {t.id: k for k, t in enumerate(themes)}
    rows = s.execute(select(Item.id, Item.title, Item.snippet, Item.source_key).where(
        Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.published_at >= since)
        .order_by(Item.id)).all()
    keep = [r for r in rows if r.id not in exclude_ids and normalise(r.title).strip() not in exclude_titles]
    idx = {r.id: i for i, r in enumerate(keep)}
    Y = np.zeros((len(keep), len(themes)), dtype=np.int8)
    for iid, tid, method, active, ev in s.execute(select(ItemTheme.item_id, ItemTheme.theme_id, ItemTheme.method,
                                                         ItemTheme.active, ItemTheme.evidence)):
        i, k = idx.get(iid), k_of.get(tid)
        if i is not None and k is not None:
            Y[i, k] = _weak(method, active, ev)
    texts = [item_text(r.title, r.snippet, r.source_key) for r in keep]
    return [r.id for r in keep], texts, Y, len(rows) - len(keep)


def train_base(s: Session, *, exclude_ids: set[int] = frozenset(), exclude_titles: set[str] = frozenset(),
               n_keep: int = N_KEEP, min_df: tuple[int, int] = (3, 2), since: datetime = SINCE, log=_log) -> dict:
    themes = model_themes(s)
    t0 = time.time()
    ids, texts, Y, left_out = weak_pool(s, themes, set(exclude_ids), set(exclude_titles), since)
    log(f"base pool {len(ids)} items ({left_out} labelled or same-title items left out)")
    fz = Features(min_df=min_df)
    X = fz.fit_transform(texts)
    coef, _, _ = fit_themes(X, Y)
    n_full = X.shape[1]
    keep = np.sort(np.argsort(-np.abs(coef).max(axis=0))[:n_keep])
    del X, coef
    fz = fz.pruned(keep)
    X = fz.fit_transform(texts)  # refit idf on the pruned vocabulary so training and inference vectors match
    coef, icp, has = fit_themes(X, Y)
    log(f"base trained on {X.shape[1]} of {n_full} features in {time.time() - t0:.0f}s")
    return {"themes": [t.slug for t in themes], "groups": [t.group for t in themes], **fz.to_bundle(),
            "coef": coef, "intercept": icp, "has_model": has, "blend_a": BLEND,
            "policy": {t.slug: "and" if t.group == "gender" else "or" for t in themes},
            "base": {"items": len(ids), "since": since.date().isoformat(), "features": int(X.shape[1]),
                     "features_before_pruning": int(n_full), "C": C, "seconds": round(time.time() - t0),
                     "positives": {t.slug: int((Y[:, k] == 1).sum()) for k, t in enumerate(themes)},
                     "left_out": {t.slug: int((Y[:, k] == -1).sum()) for k, t in enumerate(themes)}}}


# ---------------------------------------------------------------- labelled set
def read_gold(path: Path, themes: list[Theme]) -> dict[int, dict]:
    """Blind review labels (jsonl: item_id, libya yes/no/unclear, themes [slugs]) as label vectors."""
    slug2id = {t.slug: t.id for t in themes}
    all_ids = sorted(slug2id.values())
    out = {}
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        y = L._cells("theme_set", {"themes": r.get("themes", []), "libya": r.get("libya")}, slug2id, all_ids)
        out[int(r["item_id"])] = {"y": y, "w": dict.fromkeys(y, SILVER_WEIGHT), "o": dict.fromkeys(y, "gold_file"),
                                  "origin": {"gold_file"}}
    return out


def labelled_set(s: Session, model: ThemeModel, gold: dict[int, dict] | None = None, ref_tag: str | None = None) -> dict:
    """Labelled items aligned with the model's themes: texts, Y (1/0, -1 unknown), weights, relevance,
    rule hits (R), today's machine links (T: active rule or search links), H (the cell was decided
    by a person's label, not a silver one) and Yref: the reference labels alone (the gold file, or
    the review labels with ref_tag), so a later relabel does not move the yardstick."""
    db_themes = {t.slug: t for t in s.scalars(select(Theme))}
    themes = [db_themes[sl] for sl in model.themes if sl in db_themes]
    k_of = {db_themes[sl].id: k for k, sl in enumerate(model.themes) if sl in db_themes}
    vec = {i: {"y": dict(d["y"]), "w": dict(d["w"]), "o": dict(d["o"]), "origin": set(d["origin"])}
           for i, d in (gold or {}).items()}
    for iid, d in L.item_vectors(s, themes).items():  # labels in the database win over the file
        g = vec.setdefault(iid, {"y": {}, "w": {}, "o": {}, "origin": set()})
        g["y"].update(d["y"])
        g["w"].update(d["w"])
        g["o"].update(d["o"])
        g["origin"] |= d["origin"]
    items = {}
    for ch in _chunks(vec):
        for r in s.execute(select(Item.id, Item.title, Item.snippet, Item.source_key, Item.relevant).where(Item.id.in_(ch))):
            items[r.id] = r
    ids = [i for i in sorted(vec) if i in items]
    n, k = len(ids), len(model.themes)
    Y = -np.ones((n, k), dtype=np.int8)
    W = np.zeros((n, k), dtype=np.float64)
    H = np.zeros((n, k), dtype=bool)
    for i, iid in enumerate(ids):
        for tid, y in vec[iid]["y"].items():
            if tid in k_of:
                Y[i, k_of[tid]] = y
                W[i, k_of[tid]] = vec[iid]["w"].get(tid, 1.0)
                H[i, k_of[tid]] = vec[iid]["o"].get(tid) in L.PEOPLE
    refv = gold if gold else (L.item_vectors(s, themes, source_prefix=ref_tag) if ref_tag else None)
    Yref = Y
    if refv:
        Yref = -np.ones((n, k), dtype=np.int8)
        for i, iid in enumerate(ids):
            for tid, y in (refv.get(iid) or {}).get("y", {}).items():
                if tid in k_of:
                    Yref[i, k_of[tid]] = y
    rules = country_rules(s)
    R = np.zeros((n, k), dtype=bool)
    for i, iid in enumerate(ids):
        for tid in rule_hits(rules, items[iid].title, items[iid].snippet, items[iid].source_key):
            if tid in k_of:
                R[i, k_of[tid]] = True
    T = np.zeros((n, k), dtype=bool)
    pos = {iid: i for i, iid in enumerate(ids)}
    for ch in _chunks(ids):
        for lk in s.scalars(select(ItemTheme).where(ItemTheme.item_id.in_(ch), ItemTheme.active.is_(True),
                                                    ItemTheme.method.in_(("rule", "query")))):
            if lk.theme_id in k_of:
                T[pos[lk.item_id], k_of[lk.theme_id]] = True
    origins = {}
    for iid in ids:
        for o in vec[iid]["origin"]:
            origins[o] = origins.get(o, 0) + 1
    return {"ids": ids, "texts": [item_text(items[i].title, items[i].snippet, items[i].source_key) for i in ids],
            "titles": {normalise(items[i].title).strip() for i in ids}, "Y": Y, "W": W, "R": R, "T": T, "H": H,
            "Yref": Yref,
            "relevant": np.array([bool(items[i].relevant) for i in ids], dtype=bool), "origins": origins}


labels_fingerprint = L.labels_fingerprint  # lives in labels.py (no scikit-learn) for the nightly check


# ---------------------------------------------------------------- evaluation
def _pred(kind: str, p: np.ndarray, r: np.ndarray, t: float) -> np.ndarray:
    if kind == "or":
        return r | (p >= t)
    if kind == "and":
        return r & (p >= t)
    if kind == "rule":
        return r.copy()
    return p >= t


def _counts(pred: np.ndarray, gold: np.ndarray) -> np.ndarray:
    g = gold == 1
    return np.array([(pred & g).sum(), (pred & ~g).sum(), (~pred & g).sum()], dtype=np.float64)


def _f1(c) -> float:
    tp, fp, fn = c
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def wilson(k: float, n: float, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def prf(c) -> dict:
    tp, fp, fn = (float(x) for x in c)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"p": round(p, 3), "r": round(r, 3), "f1": round(_f1((tp, fp, fn)), 3), "p_ci": wilson(tp, tp + fp),
            "r_ci": wilson(tp, tp + fn), "tp": round(tp, 1), "fp": round(fp, 1), "fn": round(fn, 1)}


def _best_t(kind, p, r, g) -> float:
    if not (g == 1).any():
        return 0.5
    best, bt = -1.0, 0.5
    for t in GRID:
        f = _f1(_counts(_pred(kind, p, r, t), g))
        if f > best + 1e-9:
            best, bt = f, float(t)
    return bt


def cv_tune(kinds: list[str], P, R, Y, rows: np.ndarray, reps: int = REPS, seed: int = 0,
            tune_mask: np.ndarray | None = None, test_mask: np.ndarray | None = None, Ytest: np.ndarray | None = None):
    """Repeated 2-fold CV over `rows`: tune t on one half (best F1), test on the other. Per theme,
    tune_mask / test_mask (n x k) say which labelled cells may tune and which are scored; Ytest
    (default Y) holds the answers the test half is scored against.
    Returns (median thresholds, test counts averaged per pass) per theme."""
    rng = np.random.default_rng(seed)
    k = Y.shape[1]
    Yt = Y if Ytest is None else Ytest
    tm = np.ones(Y.shape, dtype=bool) if tune_mask is None else tune_mask
    sm = np.ones(Y.shape, dtype=bool) if test_mask is None else test_mask
    tot = np.zeros((k, 3))
    ts = [[] for _ in range(k)]
    for _ in range(reps):
        perm = rng.permutation(rows)
        halves = (perm[: len(perm) // 2], perm[len(perm) // 2:])
        for a, b in ((0, 1), (1, 0)):
            ha, hb = halves[a], halves[b]
            for j in range(k):
                tune = ha[(Y[ha, j] >= 0) & tm[ha, j]]
                test = hb[(Yt[hb, j] >= 0) & sm[hb, j]]
                t = _best_t(kinds[j], P[tune, j], R[tune, j], Y[tune, j])
                ts[j].append(t)
                tot[j] += _counts(_pred(kinds[j], P[test, j], R[test, j], t), Yt[test, j])
    return np.array([float(np.median(x)) if x else 0.5 for x in ts]), tot / reps


def fixed_counts(kind_of, P, R, Y, rows, thresholds) -> np.ndarray:
    out = np.zeros((Y.shape[1], 3))
    for j in range(Y.shape[1]):
        rr = rows[Y[rows, j] >= 0]
        out[j] = _counts(_pred(kind_of[j], P[rr, j], R[rr, j], thresholds[j]), Y[rr, j])
    return out


def crossfit(model: ThemeModel, X, Y, W, Pb, folds: int = FOLDS, seed: int = 11) -> np.ndarray:
    """Out-of-fold blended probabilities: each labelled item is scored by a small model that did not see it."""
    n = Y.shape[0]
    P = model.blend(Pb, None, np.zeros(Y.shape[1], dtype=bool))
    if n < folds * 2:
        return P
    perm = np.random.default_rng(seed).permutation(n)
    for f in np.array_split(perm, folds):
        tr = np.setdiff1d(perm, f)
        coef, icp, has = fit_themes(X[tr], Y[tr], W[tr], small=True, min_pos=MIN_POS_SMALL)
        P[f] = model.blend(Pb[f], model.small_proba(X[f], coef, icp), has)
    return P


def macro(counts: np.ndarray, ks: list[int]) -> dict:
    if not ks:
        return {"p": None, "r": None, "f1": None}
    ms = [prf(counts[k]) for k in ks]
    return {m: round(float(np.mean([x[m] for x in ms])), 3) for m in ("p", "r", "f1")}


def fit_small_and_tune(bundle: dict, data: dict, *, eval_ids: set[int] | None = None, ref_tag: str | None = None,
                       log=_log):
    """Cross-fit the small model over the labelled items, tune thresholds, decide the gender gates,
    then fit the small model on all labels. Returns (bundle, metrics, oof probabilities, reference rows).

    Non-gender themes: thresholds tuned on every labelled article, scored on the reference rows
    (eval_ids, the review labels) so versions can be compared on the same articles.
    Gender themes: thresholds, the veto figure and the gate use people's labels only (data["H"]).
    The gate opens with >= GATE_ITEMS labelled items and >= GATE_POS positives from people, a model
    for the theme, and a cross-fitted veto that finds some of them and does no worse than the rules
    on people's labels."""
    model = ThemeModel(bundle)
    Y, W, R, T, H = data["Y"], data["W"], data["R"], data["T"], data["H"]
    themes = model.themes
    kinds = list(model.policy)
    gender = [k for k, p in enumerate(kinds) if p == "and"]
    core = [k for k, p in enumerate(kinds) if p == "or"]
    X = model.vectorise(data["texts"])
    Pb = model.base_proba(X)
    P = crossfit(model, X, Y, W, Pb)
    rows = np.flatnonzero(data["relevant"])  # every labelled article about the country
    is_ref = np.isin(data["ids"], list(eval_ids)) if eval_ids else np.ones(len(data["ids"]), dtype=bool)
    ref = rows[is_ref[rows]]
    g = np.array([p == "and" for p in kinds])[None, :]
    # non-gender: scored on the reference rows against the reference labels; gender: people's labels
    Yr = data.get("Yref", Y) if eval_ids else Y
    Ytest = np.where(g, Y, Yr)
    th, cv = cv_tune(kinds, P, R, Y, rows, tune_mask=np.where(g, H, True), test_mask=np.where(g, H, is_ref[:, None]),
                     Ytest=Ytest)
    rules = fixed_counts(["rule"] * len(themes), P, R, Yr, ref, th)
    today = np.zeros_like(rules)
    people_rules = np.zeros_like(rules)
    for j in range(len(themes)):
        rr = ref[Yr[ref, j] >= 0]
        today[j] = _counts(T[rr, j], Yr[rr, j])
        hr = rows[(Y[rows, j] >= 0) & H[rows, j]]
        people_rules[j] = _counts(R[hr, j], Y[hr, j])
    stats = {sl: {"labelled": int((Y[:, k] >= 0).sum()), "positives": int((Y[:, k] == 1).sum())} for k, sl in enumerate(themes)}
    people = {sl: {"labelled": int(((Y[:, k] >= 0) & H[:, k]).sum()), "positives": int(((Y[:, k] == 1) & H[:, k]).sum())}
              for k, sl in enumerate(themes)}
    coef, icp, has = fit_themes(X, Y, W, small=True, min_pos=MIN_POS_SMALL)
    gates = {}
    for k in gender:
        enough = people[themes[k]]["labelled"] >= GATE_ITEMS and people[themes[k]]["positives"] >= GATE_POS
        gates[themes[k]] = bool(enough and (model.has_base[k] or has[k]) and _f1(cv[k]) > 0
                                and _f1(cv[k]) >= _f1(people_rules[k]))
    veto_ref = fixed_counts(kinds, P, R, Yr, ref, th)  # the gender veto on the reference rows, at the people-tuned thresholds
    applied = np.array([cv[k] if kinds[k] == "or" else veto_ref[k] if gates.get(themes[k]) else rules[k]
                        for k in range(len(themes))])
    out = dict(bundle, small_coef=coef, small_intercept=icp, small_has=has,
               thresholds={sl: round(float(th[k]), 3) for k, sl in enumerate(themes)}, gates=gates, gates_from="people",
               label_stats=stats, people_stats=people)
    per = {}
    for k, sl in enumerate(themes):
        per[sl] = {"policy": kinds[k], "threshold": round(float(th[k]), 3), "labelled": stats[sl]["labelled"],
                   "positives": stats[sl]["positives"], "eval_positives": int((Yr[ref, k] == 1).sum()),
                   "blended": bool(has[k]), "rules": prf(rules[k]), "links_today": prf(today[k]), "model": prf(applied[k])}
        if kinds[k] == "and":
            per[sl]["gate"] = gates[sl]
            per[sl]["veto_cv"] = prf(cv[k])  # on people's labels
            per[sl]["people"] = {**people[sl], "rules": prf(people_rules[k]), "veto_cv": prf(cv[k])}
    mac = {grp: {"rules": macro(rules, ks), "links_today": macro(today, ks), "model": macro(applied, ks)}
           for grp, ks in (("non_gender", core), ("gender", gender))}
    metrics = {"eval_items": int(len(ref)), "label_items": len(data["ids"]), "origins": data["origins"],
               "method": f"small model cross-fitted ({FOLDS} folds), thresholds by {REPS}x2-fold CV "
                         f"(gender themes on people's labels only)",
               "macro": mac, "themes": per,
               "reference": {"set": ref_tag, "items": int(len(ref)), "non_gender": mac["non_gender"]["model"]["f1"],
                             "gender": mac["gender"]["model"]["f1"]}}
    log(f"labelled {len(data['ids'])} items ({int(H.any(axis=1).sum())} with people's labels), evaluated on "
        f"{len(ref)}; gender gates open: {[sl for sl, g in gates.items() if g] or 'none'}")
    return out, metrics, P, ref


# ---------------------------------------------------------------- the two commands
def bundle_meta(b: dict) -> dict:
    return {"version": b["version"], "trained_on": b.get("trained_on", {}), "metrics": b.get("metrics", {}),
            "thresholds": b.get("thresholds", {})}


def save_bundle(b: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(b, path, compress=3)
    return path


def train_full(s: Session, gold_path: Path | None = None, *, n_keep: int = N_KEEP, min_df: tuple[int, int] = (3, 2),
               log=_log) -> dict:
    """train-theme-model: base + small from scratch. Heavy; local only. The review labels (the gold
    file, or the newest imported set) are the reference set later versions are compared on."""
    themes = model_themes(s)
    gold = read_gold(gold_path, themes) if gold_path else {}
    tag = L.gold_tag(Path(gold_path).name) if gold_path else L.latest_gold_tag(s)
    lab_ids = set(gold) | set(L.item_vectors(s, themes))
    titles = set()
    for ch in _chunks(lab_ids):
        titles |= {normalise(t).strip() for t in s.scalars(select(Item.title).where(Item.id.in_(ch)))}
    titles.discard("")
    bundle = train_base(s, exclude_ids=lab_ids, exclude_titles=titles, n_keep=n_keep, min_df=min_df, log=log)
    bundle["version"] = new_version()
    data = labelled_set(s, ThemeModel(bundle), gold, ref_tag=tag)
    have = set(data["ids"])
    ref_ids = {i for i in gold if i in have} if gold else L.reference_ids(s, tag) & have
    bundle, metrics, _, _ = fit_small_and_tune(bundle, data, eval_ids=ref_ids or None, ref_tag=tag if ref_ids else None,
                                               log=log)
    metrics["eval_set"] = Path(gold_path).name if gold_path else (tag if ref_ids else "all labelled items")
    bundle["metrics"] = metrics
    bundle["trained_on"] = {"date": utcnow().date().isoformat(), "base": bundle["base"],
                            "labels": {"items": len(data["ids"]), "by_origin": data["origins"],
                                       "fingerprint": labels_fingerprint(s)},
                            "gold": Path(gold_path).name if gold_path else None}
    return bundle


def live_reference(b: dict) -> dict | None:
    """The live version's score on its reference set: {set, items, non_gender, gender}. Bundles from
    before the reference block name their gold file in metrics.eval_set."""
    m = b.get("metrics") or {}
    if (m.get("reference") or {}).get("set") and m["reference"].get("non_gender") is not None:
        return m["reference"]
    name = str(m.get("eval_set") or "")
    f1 = (((m.get("macro") or {}).get("non_gender") or {}).get("model") or {}).get("f1")
    if name.endswith(".jsonl") and f1 is not None:
        return {"set": L.gold_tag(name), "items": m.get("eval_items"), "non_gender": f1}
    return None


def should_promote(cand_ng: float, live_ng: float, gender: dict[str, tuple[float, float]] | None = None,
                   where: str = "") -> tuple[bool, str]:
    """cand_ng / live_ng: non-gender macro-F1 on the same reference set, each cross-fitted when it was
    trained. gender: {slug: (candidate, live)} F1 on people's labels for each theme the candidate would veto."""
    if cand_ng < live_ng - 0.01:
        return False, f"non-gender macro-F1 {cand_ng:.3f} vs live {live_ng:.3f}{where}"
    for sl, (c, lv) in (gender or {}).items():
        if c < lv - 1e-9:
            return False, f"{sl} F1 on people's labels {c:.3f} vs live {lv:.3f}"
    g = "".join(f", {sl} {c:.3f} (live {lv:.3f})" for sl, (c, lv) in (gender or {}).items())
    return True, f"non-gender macro-F1 {cand_ng:.3f} (live {live_ng:.3f}){where}{g}"


def promotion_check(metrics: dict, live_bundle: dict) -> tuple[bool, str, dict]:
    """Compare a candidate's honest scores with the live version's (see should_promote)."""
    ref = live_reference(live_bundle)
    mine = metrics.get("reference") or {}
    if not ref or mine.get("set") != ref.get("set") or mine.get("non_gender") is None:
        return False, "no fixed set of labelled articles to compare with the live version (run import-gold-labels)", {}
    lm = (live_bundle.get("metrics") or {}).get("themes") or {}
    live_veto = live_bundle.get("gates", {}) if live_bundle.get("gates_from") == "people" else {}
    gender = {}
    for sl, m in metrics["themes"].items():
        if m.get("gate"):
            mine_f = m["people"]["veto_cv"]["f1"]
            theirs = ((lm.get(sl) or {}).get("people") or {}).get("veto_cv", {}).get("f1") if live_veto.get(sl) else None
            gender[sl] = (mine_f, theirs if theirs is not None else m["people"]["rules"]["f1"])
    where = f" on the {mine.get('items')} articles of {ref['set']}"
    ok, why = should_promote(mine["non_gender"], ref["non_gender"], gender, where)
    comp = {"set": ref["set"], "items": mine.get("items"),
            "candidate": {"non_gender": mine["non_gender"], **{sl: c for sl, (c, _) in gender.items()}},
            "live": {"non_gender": ref["non_gender"], **{sl: lv for sl, (_, lv) in gender.items()}}}
    return ok, why, comp


def retrain_small(s: Session, active_bundle: dict, *, seen: list | tuple = (), log=_log) -> tuple[dict | None, dict]:
    """train-small-model: refit only the label-trained part on the live model's features, re-tune,
    and say whether it may replace the live model. Cheap enough for the server.
    seen: label fingerprints already tried on top of this live version (skip when nothing is new)."""
    fp = labels_fingerprint(s)
    trained = active_bundle.get("trained_on", {}).get("labels", {})
    if fp == trained.get("fingerprint") or fp in [list(x) for x in seen]:
        return None, {"skipped": "no new labels since the live model or the last check"}
    live = ThemeModel(active_bundle)
    ref = live_reference(active_bundle)
    data = labelled_set(s, live, ref_tag=ref["set"] if ref else None)
    if len(data["ids"]) < trained.get("items", 0):
        return None, {"skipped": f"the database has {len(data['ids'])} labelled items, fewer than the "
                                 f"{trained.get('items')} the live model learned from (run import-gold-labels?)"}
    ref_ids = L.reference_ids(s, ref["set"]) & set(data["ids"]) if ref else set()
    base = {k: v for k, v in active_bundle.items() if not k.startswith("small_")}
    cand, metrics, _, _ = fit_small_and_tune(base, data, eval_ids=ref_ids or None,
                                             ref_tag=ref["set"] if ref_ids else None, log=log)
    new = len(data["ids"]) - trained.get("items", 0)
    if new < NEW_LABELS_FOR_THRESHOLDS:  # gender thresholds always come from people's labels
        keep = active_bundle.get("thresholds", {})
        cand["thresholds"] = {sl: keep.get(sl, t) if p == "or" else t
                              for (sl, t), p in zip(cand["thresholds"].items(), ThemeModel(cand).policy)}
        metrics["thresholds_kept"] = f"{new} new labelled items, fewer than {NEW_LABELS_FOR_THRESHOLDS}"
    ok, why, comp = promotion_check(metrics, active_bundle)
    cand["version"] = new_version("-small")
    cand["metrics"] = {**metrics, "eval_set": ref["set"] if ref_ids else "all labelled items",
                       "compared_with": active_bundle.get("version"), "comparison": comp, "promote": ok, "reason": why}
    cand["trained_on"] = {**active_bundle.get("trained_on", {}), "date": utcnow().date().isoformat(),
                          "labels": {"items": len(data["ids"]), "by_origin": data["origins"], "fingerprint": fp},
                          "small_from": active_bundle.get("version")}
    for k in ("activated", "pinned", "by_hand", "file_removed"):
        cand["trained_on"].pop(k, None)
    return cand, {"promote": ok, "reason": why}
