"""Theme model: labels, registry, training on a small synthetic corpus, the decision rule,
the labelling endpoints and the scheduler hook. No real bundle needed."""
import json
import random
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.ingest import load_rules, store_article
from app.ml import labels as L
from app.ml import registry
from app.models import Country, Event, Item, ItemTheme, Label, ModelRegistry, SourceRun, Theme, utcnow

from .conftest import ids, login

PLACES = ["Tripoli", "Benghazi", "Sabha", "Misrata", "Zawiya", "Derna"]
FILL = ["officials said", "residents report", "on Tuesday", "this week", "local sources say", "according to a statement",
        "witnesses said", "in the morning"]
TOPICS = {
    "security": ["militia clashes erupt in {p}", "gunmen kidnapping reported in {p}", "heavy gunfire near a checkpoint in {p}"],
    "migration": ["migrants rescued off the {p} coast", "coast guard intercepts boat near {p}",
                  "dozens of people set off from the shore at dawn near {p}"],
    "economy": ["oil exports rise at the {p} terminal", "central bank sets a new dinar rate in {p}",
                "traders worry about rising prices in {p} market"],
    "health": ["hospital in {p} short of medicines", "cholera vaccination campaign starts in {p}",
               "clinic overwhelmed with patients in {p}"],
    "gender_violence": ["domestic violence case against a woman in {p}", "sexual harassment of women reported in {p}",
                        "woman beaten by her husband in {p}"],
    None: ["football final played in {p}", "cultural festival opens in {p}", "sunny weather expected in {p}",
           "new bakery opens in {p}"],
}


def make_corpus(db, n_per_topic=40, seed=0) -> dict[int, str | None]:
    """Synthetic articles; returns item id -> true theme slug (None = no theme)."""
    rng = random.Random(seed)
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    truth = {}
    when = utcnow() - timedelta(days=2)
    k = 0
    for topic, temps in TOPICS.items():
        for _ in range(n_per_topic if topic else n_per_topic * 3):
            title = f"{rng.choice(temps).format(p=rng.choice(PLACES))}, Libya {rng.choice(FILL)} {k}"
            it, _ = store_article(db, c.id, rules, url=f"https://ex.ly/a{k}", title=title, published_at=when,
                                  source_key="rss")
            truth[it.id] = topic
            k += 1
    db.commit()
    return truth


def add_labels(db, truth: dict, n: int, seed: int = 1, origin: str = "explicit", start: int = 0) -> list[int]:
    of = [t.slug for t in db.scalars(select(Theme).where(Theme.active.is_(True)))]
    picked = random.Random(seed).sample(sorted(truth), n)
    for i, iid in enumerate(picked):
        db.add(Label(label_type="theme_set", object_type="item", object_key=str(iid), origin=origin,
                     weight=1.0 if origin == "explicit" else 0.5, source_ref=f"t:{start + i}:{iid}",
                     value={"themes": [truth[iid]] if truth[iid] else [], "libya": True, "of": of}))
    db.commit()
    return picked


# ---------------------------------------------------------------- text
def test_clean_snippet():
    from app.ml.features import clean_snippet, item_text
    assert clean_snippet("Prices up &#8230; again. The post Prices up appeared first on Libya Review.") == "Prices up … again."
    galerts = "Torrential rains in Tripoli kill two ... Women's Representation . Other News to Consider"
    assert clean_snippet(galerts, "Torrential rains in Tripoli kill two", "galerts") == "Torrential rains in Tripoli kill two"
    assert item_text("Title", None) == "Title"


# ---------------------------------------------------------------- labels
def test_label_vectors_priority_and_shapes(db):
    themes, _ = ids(db)
    t_all = db.scalars(select(Theme).where(Theme.active.is_(True))).all()
    later = utcnow()
    db.add_all([
        # silver says health, a person later says security only: the person wins even if the silver row is newer
        Label(label_type="theme_set", object_type="item", object_key="1", origin="explicit", source_ref="a",
              value={"themes": ["security"], "libya": True}, created_at=later - timedelta(hours=1)),
        Label(label_type="theme_set", object_type="item", object_key="1", origin="silver", weight=0.5, source_ref="b",
              value={"themes": ["health"], "libya": "yes"}, created_at=later),
        Label(label_type="theme_relevance", object_type="item", object_key="2", origin="explicit", source_ref="c",
              value={"theme_id": themes["economy"], "theme_relevant": False}),
        Label(label_type="theme_set", object_type="item", object_key="3", origin="silver", weight=0.5, source_ref="d",
              value={"themes": ["migration"], "libya": "no", "of": ["migration", "health"]}),
        Label(label_type="theme_relevance", object_type="item", object_key="4", origin="explicit", source_ref="e",
              value={"themes": [themes["services"]], "relevant": True}),
    ])
    db.commit()
    v = L.item_vectors(db, t_all)
    assert v[1]["y"][themes["security"]] == 1 and v[1]["y"][themes["health"]] == 0
    assert len(v[1]["y"]) == len(t_all)
    assert v[2]["y"] == {themes["economy"]: 0}
    assert v[3]["y"] == {themes["migration"]: 0, themes["health"]: 0}
    assert v[4]["y"] == {themes["services"]: 1}
    st = L.theme_stats(v, t_all)
    assert st["economy"] == {"labelled": 2, "positives": 0}
    assert L.labelled_item_ids(db) >= {1, 2, 3, 4}


def test_import_gold_labels_idempotent(db, tmp_path):
    from app.ml.commands import import_gold_labels
    truth = make_corpus(db, n_per_topic=2)
    a, b = sorted(truth)[:2]
    p = tmp_path / "gold_labels_2026-10-16.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"item_id": a, "libya": "yes", "themes": ["security", "not_a_theme"]},
        {"item_id": b, "libya": "no", "themes": []},
        {"item_id": 999999, "libya": "yes", "themes": ["health"]}]), encoding="utf-8")
    assert import_gold_labels(db, [str(p)]) == {"added": 2, "already_there": 0, "skipped_not_in_db": 1, "changed": 2}
    assert import_gold_labels(db, [str(p)])["added"] == 0
    lab = db.scalar(select(Label).where(Label.source_ref == f"gold2026-10-16:{a}"))
    assert lab.origin == "silver" and lab.weight == 0.5 and lab.label_type == "theme_set"
    assert lab.value["themes"] == ["security"] and lab.value["libya"] == "yes"


# ---------------------------------------------------------------- registry
def _fake_bundle_file(tmp_path, version):
    p = tmp_path / f"{version}.joblib"
    p.write_bytes(b"x")
    return p, {"version": version, "trained_on": {"labels": {"items": 3}}, "metrics": {"macro": {}},
               "thresholds": {"security": 0.3}}


def test_registry_activate_and_rollback(db, tmp_path):
    for v in ("theme-a", "theme-b"):
        p, meta = _fake_bundle_file(tmp_path, v)
        registry.register(db, p, meta, activate_now=True)
    db.commit()
    assert registry.active(db).version == "theme-b"
    assert (registry.models_dir() / "theme-a.joblib").exists()
    assert db.query(ModelRegistry).filter(ModelRegistry.active.is_(True)).count() == 1
    assert registry.rollback(db).version == "theme-a"
    assert registry.rollback(db).version == "theme-b"  # back to what was live before
    with pytest.raises(ValueError):
        registry.register(db, *_fake_bundle_file(tmp_path, "theme-a"))


def test_should_promote():
    from app.ml.train import should_promote
    assert should_promote({"non_gender": 0.70, "gender": 0.60}, {"non_gender": 0.705, "gender": 0.60})[0]
    assert not should_promote({"non_gender": 0.68, "gender": 0.70}, {"non_gender": 0.70, "gender": 0.60})[0]
    assert not should_promote({"non_gender": 0.75, "gender": 0.59}, {"non_gender": 0.70, "gender": 0.60})[0]


# ---------------------------------------------------------------- decision rule (fake model)
class FakeModel:
    def __init__(self, themes, probs, th, veto, version="fake-1"):
        self.themes, self.version, self.probs = themes, version, probs
        self.th = np.array(th, dtype=float)
        self.policy = ["and" if t.startswith("gender") else "or" for t in themes]
        self.veto = np.array(veto)
        self.has = np.ones(len(themes), dtype=bool)

    def proba(self, texts):
        return np.array([self.probs[t] for t in texts], dtype=float)


def test_decision_rule(db):
    from app.ml.infer import classify_items, reset_model_links
    themes, _ = ids(db)
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    when = utcnow() - timedelta(days=1)
    A, B, D = "Militia clashes in Tripoli, Libya", "Ships seen near Zuwara, Libya", "Domestic violence against a woman in Sabha, Libya"
    a, _ = store_article(db, c.id, rules, url="https://ex.ly/A", title=A, published_at=when, source_key="rss")
    b, _ = store_article(db, c.id, rules, url="https://ex.ly/B", title=B, published_at=when, source_key="rss")
    d, _ = store_article(db, c.id, rules, url="https://ex.ly/D", title=D, published_at=when, source_key="rss")
    db.add(ItemTheme(item_id=b.id, theme_id=themes["migration"], method="query", active=False, evidence={"field": "query"}))
    db.add(ItemTheme(item_id=b.id, theme_id=themes["security"], method="user", active=False))
    db.commit()
    assert db.get(ItemTheme, (a.id, themes["security"])).method == "rule"
    assert db.get(ItemTheme, (d.id, themes["gender_violence"])).active
    slugs = ["security", "migration", "gender_violence"]
    run = lambda probs, veto: classify_items(db, FakeModel(slugs, probs, [0.3, 0.3, 0.5], veto))  # noqa: E731

    res = run({A: [0.1, 0.9, 0.0], B: [0.9, 0.8, 0.3], D: [0.0, 0.0, 0.1]}, [False, False, False])
    db.expire_all()
    assert db.get(ItemTheme, (a.id, themes["security"])).active             # rule links stay for non-gender
    assert db.get(ItemTheme, (a.id, themes["security"])).score == 0.1
    added = db.get(ItemTheme, (a.id, themes["migration"]))
    assert added.method == "model" and added.active and added.model_version == "fake-1"
    q = db.get(ItemTheme, (b.id, themes["migration"]))
    assert q.method == "model" and q.active and q.evidence == {"field": "query", "model": 0.8, "was": "query"}
    u = db.get(ItemTheme, (b.id, themes["security"]))
    assert u.method == "user" and not u.active and u.score == 0.9           # people's decisions are never changed
    g = db.get(ItemTheme, (d.id, themes["gender_violence"]))
    assert g.active and g.score == 0.1                                      # before the gate: scores only
    assert db.get(Item, b.id).extra["model"]["near"] == {"gender_violence": 0.3}
    assert res["themes"]["migration"]["added"] == 2

    res = run({A: [0.1, 0.1, 0.0], B: [0.9, 0.1, 0.0], D: [0.0, 0.0, 0.1]}, [False, False, True])
    db.expire_all()
    assert not db.get(ItemTheme, (a.id, themes["migration"])).active
    q = db.get(ItemTheme, (b.id, themes["migration"]))
    assert q.method == "query" and not q.active and q.evidence == {"field": "query", "model": 0.1}
    g = db.get(ItemTheme, (d.id, themes["gender_violence"]))
    assert not g.active and g.evidence["veto"] == 0.1
    assert res["themes"]["gender_violence"]["vetoed"] == 1 and res["themes"]["migration"]["removed"] == 2

    dry = classify_items(db, FakeModel(slugs, {A: [0, 0, 0], B: [0, 0, 0], D: [0, 0, 0.9]}, [0.3, 0.3, 0.5],
                                       [False, False, True]), dry_run=True)
    db.expire_all()
    assert dry["themes"]["gender_violence"]["unvetoed"] == 1 and not db.get(ItemTheme, (d.id, themes["gender_violence"])).active
    run({A: [0.1, 0.9, 0.0], B: [0, 0, 0], D: [0.0, 0.0, 0.9]}, [False, False, True])
    db.expire_all()
    assert db.get(ItemTheme, (d.id, themes["gender_violence"])).active
    run({A: [0.1, 0.9, 0.0], B: [0, 0, 0], D: [0.0, 0.0, 0.1]}, [False, False, True])
    assert reset_model_links(db) == {"model_links_off": 1, "vetoes_lifted": 1}
    db.expire_all()
    assert db.get(ItemTheme, (d.id, themes["gender_violence"])).active
    assert not db.get(ItemTheme, (a.id, themes["migration"])).active


# ---------------------------------------------------------------- training end to end (small synthetic corpus)
def test_train_register_classify_retrain(db, tmp_path):
    from app.ml.infer import ThemeModel, classify_items, load_bundle
    from app.ml.train import bundle_meta, retrain_small, save_bundle, train_full
    truth = make_corpus(db)
    add_labels(db, truth, 150)
    b = train_full(db, None, n_keep=3000, min_df=(1, 1), log=lambda m: None)
    assert b["base"]["items"] == len(truth) - 150
    assert set(b["thresholds"]) == set(b["themes"]) and all(0 < t < 1 for t in b["thresholds"].values())
    assert b["policy"]["security"] == "or" and b["policy"]["gender_violence"] == "and"
    assert set(b["gates"]) == {t for t in b["themes"] if t.startswith("gender")}
    m = b["metrics"]
    assert m["eval_items"] == 150 and m["themes"]["security"]["eval_positives"] > 10
    assert m["themes"]["security"]["model"]["f1"] >= 0.7 and m["macro"]["non_gender"]["model"]["f1"] is not None
    assert m["themes"]["security"]["rules"]["p_ci"][0] <= m["themes"]["security"]["rules"]["p"]
    assert b["small_has"][b["themes"].index("security")] and not b["small_has"][b["themes"].index("gender_lgbtq")]

    path = save_bundle(b, tmp_path / "bundle.joblib")
    row = registry.register(db, path, bundle_meta(b), activate_now=True)
    db.commit()
    model = ThemeModel.load(row.path)
    p = model.proba(["militia clashes erupt in Tripoli, Libya", "sunny weather expected in Derna, Libya"])
    k = model.themes.index("security")
    assert p.shape == (2, len(model.themes)) and p[0, k] > p[1, k]
    res = classify_items(db, model)
    assert res["items"] == len(truth)
    db.expire_all()
    scored = db.scalars(select(ItemTheme).where(ItemTheme.score.is_not(None))).all()
    assert scored and all(x.model_version == b["version"] for x in scored)
    assert all((it.extra or {}).get("model", {}).get("v") == b["version"] for it in db.scalars(select(Item)))

    assert retrain_small(db, load_bundle(row.path)) == (None, {"skipped": "no new labels since the live model"})
    add_labels(db, truth, 5, seed=7, start=1000)
    cand, decision = retrain_small(db, load_bundle(row.path))
    assert cand["version"].endswith("-small") and isinstance(decision["promote"], bool)
    assert cand["thresholds"] == b["thresholds"]  # fewer than 100 new labels: live thresholds kept
    assert cand["metrics"]["compared_with"] == b["version"]


def test_cli_commands(db, capsys):
    from app.cli import main
    assert main(["classify-items", "--days", "3"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["skipped"] == "no active theme model"
    assert main(["model-status"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["active"] is None


# ---------------------------------------------------------------- endpoints
def _story_with_copy(db, title="Hospital in Sabha short of medicines, Libya"):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    when = utcnow() - timedelta(days=1)
    a, _ = store_article(db, c.id, rules, url="https://ex.ly/story", title=title, published_at=when, source_key="rss")
    b, _ = store_article(db, c.id, rules, url="https://news.google.com/story", title=title, published_at=when,
                         source_key="gnews")
    b.duplicate_of = a.id
    db.commit()
    return a, b


def test_full_vector_labels_cover_duplicates(client, users, db):
    from app.auth import create_user
    from app.learning import build_labels
    themes, _ = ids(db)
    a, b = _story_with_copy(db)
    login(client, "j@example.org", "journo-password-1")
    r = client.post(f"/api/items/{b.id}/labels", json={"themes": [themes["health"], themes["services"]], "libya": True})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["theme_ids"]) == sorted([themes["health"], themes["services"]])
    n_active = db.query(Theme).filter(Theme.active.is_(True)).count()
    db.expire_all()
    for x in (a, b):
        links = db.scalars(select(ItemTheme).where(ItemTheme.item_id == x.id)).all()
        assert len(links) == n_active and all(lk.method == "user" for lk in links)
        assert {lk.theme_id for lk in links if lk.active} == {themes["health"], themes["services"]}
    assert db.get(ItemTheme, (a.id, themes["health"])).evidence == {"was": "rule"}
    ev = db.scalar(select(Event).where(Event.type == "correction"))
    assert ev.context["label_type"] == "theme_set" and sorted(ev.context["themes"]) == ["health", "services"]
    assert build_labels(db) == 1
    lab = db.scalar(select(Label).where(Label.label_type == "theme_set"))
    assert L.item_vectors(db)[int(lab.object_key)]["y"][themes["security"]] == 0
    r = client.post(f"/api/items/{a.id}/labels", json={"themes": [], "libya": False})
    db.expire_all()
    assert not db.get(Item, a.id).relevant and not db.get(Item, b.id).relevant
    assert db.get(Item, b.id).extra["user_relevance"] is False
    assert client.post(f"/api/items/{a.id}/labels", json={"themes": [99999], "libya": True}).status_code == 400
    create_user(db, "v@example.org", "viewer-password-1", "Viewer", "viewer")
    db.commit()
    client.post("/api/auth/logout")
    login(client, "v@example.org", "viewer-password-1")
    assert client.post(f"/api/items/{a.id}/labels", json={"themes": [], "libya": True}).status_code == 403


def test_single_correction_covers_duplicates_and_detail(client, users, db):
    themes, _ = ids(db)
    a, b = _story_with_copy(db)
    login(client, "j@example.org", "journo-password-1")
    r = client.post(f"/api/items/{a.id}/correction", json={"theme_id": themes["health"], "theme_relevant": False})
    assert themes["health"] not in r.json()["theme_ids"]
    detail = {d["theme_id"]: d for d in r.json()["theme_detail"]}
    assert detail[themes["health"]]["method"] == "user" and detail[themes["health"]]["active"] is False
    db.expire_all()
    assert db.get(ItemTheme, (b.id, themes["health"])).method == "user"
    assert not db.get(ItemTheme, (b.id, themes["health"])).active


def test_review_queue(client, users, db, tmp_path):
    themes, _ = ids(db)
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    when = utcnow() - timedelta(days=3)
    mk = lambda u, t: store_article(db, c.id, rules, url=f"https://ex.ly/{u}", title=t, published_at=when,  # noqa: E731
                                    source_key="rss")[0]
    w = mk("w", "Women open a new market in Benghazi, Libya")
    gender = [t.id for t in db.scalars(select(Theme).where(Theme.group == "gender"))]
    for lk in db.scalars(select(ItemTheme).where(ItemTheme.item_id == w.id, ItemTheme.theme_id.in_(gender))):
        db.delete(lk)
    g1 = mk("g1", "Minister visits Sabha, Libya")
    g2 = mk("g2", "Minister opens a school in Misrata, Libya")
    u = mk("u", "Talks continue in Tripoli, Libya")
    u.extra = {"model": {"v": "theme-x", "u": 4.2, "near": {"health": 0.12}}}
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    d = client.get("/api/review-queue?n=10").json()
    reasons = {x["id"]: x["reason"] for x in d["items"]}
    assert d["model"] is None and reasons.get(w.id) == "gender_candidate"
    assert reasons.get(g1.id) == "generic_term" and u.id not in reasons
    assert next(x for x in d["items"] if x["id"] == g1.id)["generic_term"] == "minister"
    client.post(f"/api/items/{g1.id}/labels", json={"themes": [themes["governance"]], "libya": True})
    p, meta = _fake_bundle_file(tmp_path, "theme-x")
    registry.register(db, p, meta, activate_now=True)
    db.commit()
    d = client.get("/api/review-queue?n=10").json()
    by = {x["id"]: x for x in d["items"]}
    assert g1.id not in by and g2.id in by
    assert by[u.id]["reason"] == "uncertain" and by[u.id]["scores"] == {str(themes["health"]): 0.12}
    assert d["model"] == "theme-x" and d["labelled"] >= 1


def test_admin_models(client, users, db, tmp_path):
    for v in ("theme-1", "theme-2"):
        registry.register(db, *_fake_bundle_file(tmp_path, v))
    registry.activate(db, "theme-1")
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/admin/models").status_code == 403
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    d = client.get("/api/admin/models").json()
    assert d["active"] == "theme-1" and [m["version"] for m in d["models"]] == ["theme-2", "theme-1"]
    assert {t["slug"] for t in d["themes"]} >= {"security", "gender_violence"}
    assert client.post("/api/admin/models/theme-2/activate").json()["active"] is True
    assert client.get("/api/admin/models").json()["active"] == "theme-2"
    assert client.post("/api/admin/models/nope/activate").status_code == 404
    learning = client.get("/api/admin/learning").json()
    assert learning["models"][0]["version"] == "theme-2" and learning["note"] is None


# ---------------------------------------------------------------- scheduler hook and import hygiene
def test_model_job_runs_in_child_process(db, tmp_path, monkeypatch):
    from app import jobs
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='table\n{"changed": 7}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert jobs.model_job("theme_model", "classify-items", "--days", "3") is None and not calls  # no live model
    registry.register(db, *_fake_bundle_file(tmp_path, "theme-j"), activate_now=True)
    db.commit()
    assert jobs.model_job("theme_model", "classify-items", "--days", "3") == {"changed": 7}
    assert calls[0][1:] == ["-m", "app.cli", "classify-items", "--days", "3"]
    run = db.scalar(select(SourceRun).where(SourceRun.source_key == "theme_model"))
    assert run.status == "ok" and run.rows == 7


def test_web_app_does_not_import_sklearn():
    code = ("import sys, app.main, app.jobs, app.api.labelling, app.ml.commands; "
            "assert not {'sklearn', 'numpy', 'scipy'} & set(sys.modules), sorted(sys.modules)")
    r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
