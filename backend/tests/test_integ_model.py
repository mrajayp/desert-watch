"""Integration fixes 2026-10-16 around the theme model: re-tagging with a live model (X2, m6), the hourly
scoring (M2, X3), the nightly check, register-model (m4), the review queue's generic words (X4),
story pickup by outlet family (X5), the network write transactions (m3) and seeded feeds (m5)."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select, text

from app.ingest import load_rules, store_article
from app.ml import labels as L
from app.ml import registry
from app.models import Country, Item, ItemEngagement, ItemTheme, NetworkEdgeWeek, Outlet, SourceRun, utcnow

from .conftest import ids, login

T0 = datetime(2026, 10, 6, 8)
STORY = "Clashes erupt in Zawiya between rival armed groups, residents say"


def _fake_model(db, tmp_path, version="theme-live", thresholds=None):
    p = tmp_path / f"{version}.joblib"
    p.write_bytes(version.encode())
    row = registry.register(db, p, {"version": version, "trained_on": {"labels": {"items": 3}}, "metrics": {},
                                    "thresholds": thresholds or {"security": 0.3, "gender_violence": 0.5}},
                            activate_now=True)
    db.commit()
    return row


def _store(db, url, title, when=None, snippet=None, source_key="rss"):
    c = db.scalar(select(Country))
    it, _ = store_article(db, c.id, load_rules(db, c.id), url=url, title=title, snippet=snippet,
                          published_at=when or utcnow() - timedelta(days=40), source_key=source_key)
    db.commit()
    return it


def _link(db, item_id, theme_id):
    db.expire_all()
    return db.get(ItemTheme, (item_id, theme_id))


# ---------------------------------------------------------------- X2 / m6: re-tagging with a live model
def test_admin_edit_keeps_the_links_the_live_model_supports(client, users, db, tmp_path, monkeypatch):
    from app import jobs
    themes, _ = ids(db)
    sec = themes["security"]
    kept = _store(db, "https://ex.ly/kept", "Militia clashes in Tripoli, Libya")
    dropped = _store(db, "https://ex.ly/dropped", "Militia clashes near Sabha, Libya")
    lk = _link(db, kept.id, sec)
    assert (lk.method, lk.active) == ("rule", True)
    words = set(lk.evidence["terms"])
    old_evidence = dict(lk.evidence)
    lk.score, lk.model_version = 0.9, "theme-live"           # the live model scores it above its bar (0.3)
    _link(db, dropped.id, sec).score = 0.1                    # and this one below
    db.commit()
    _fake_model(db, tmp_path)
    queued = []
    monkeypatch.setitem(jobs.JOBS, "classify_all", lambda: queued.append("classify_all"))

    login(client, "admin@example.org", "admin-password-1")
    t = next(x for x in client.get("/api/themes").json() if x["id"] == sec)
    body = {k: t[k] for k in ("group", "cooc", "strict", "name_en", "name_ar", "exclude", "veto", "mask",
                              "acled_event_types", "reliefweb_themes", "active") if t.get(k) is not None}
    body |= {"en_terms": [w for w in t["en_terms"] if w not in words],
             "ar_terms": [w for w in t["ar_terms"] if w not in words]}
    assert client.put(f"/api/themes/{sec}", json=body).status_code == 200   # the retag runs as a background task

    lk = _link(db, kept.id, sec)
    assert (lk.method, lk.active) == ("model", True)        # rule OR p >= t: still counted
    assert lk.evidence == {**old_evidence, "model": 0.9, "was": "rule"}
    lk = _link(db, dropped.id, sec)
    assert (lk.method, lk.active, lk.evidence) == ("rule", False, None)
    assert queued == ["classify_all"]                        # then the model re-scores everything


def test_retag_without_a_live_model_queues_nothing(db, monkeypatch):
    from app import jobs
    from app.api.admin import _retag_theme
    themes, _ = ids(db)
    queued = []
    monkeypatch.setitem(jobs.JOBS, "classify_all", lambda: queued.append("classify_all"))
    _retag_theme(themes["security"], recompute=False, classify=True)
    assert queued == []


def test_a_vetoed_rule_link_stays_off_after_any_retag(db, tmp_path):
    from app.ml.infer import reset_model_links
    from app.retag import retag_all, retag_theme
    themes, _ = ids(db)
    gv = themes["gender_violence"]
    it = _store(db, "https://ex.ly/gv", "Domestic violence against a woman in Sabha, Libya")
    lk = _link(db, it.id, gv)
    assert (lk.method, lk.active) == ("rule", True)
    terms = lk.evidence["terms"]
    lk.active, lk.evidence, lk.score = False, {**lk.evidence, "veto": 0.1}, 0.1   # what classify-items does
    db.commit()
    lines = []
    for run in (lambda: retag_all(db, out=lines.append), lambda: retag_theme(db, gv)):
        run()
        lk = _link(db, it.id, gv)
        assert (lk.method, lk.active, lk.evidence["veto"], lk.evidence["terms"]) == ("rule", False, 0.1, terms)
    assert retag_all(db, out=lines.append)["links_changed"] == 0
    assert not any("classify-items --all" in x for x in lines)   # no model live: no hint
    _fake_model(db, tmp_path)
    retag_all(db, out=lines.append)
    assert any("theme-live" in x and "classify-items --all" in x for x in lines)
    assert reset_model_links(db)["vetoes_lifted"] == 1          # the veto was kept, so it can still be lifted
    assert _link(db, it.id, gv).active


def test_retag_dry_run_agrees_with_the_real_run_when_the_model_keeps_a_link(db, tmp_path):
    from app.retag import retag_all
    themes, _ = ids(db)
    it = _store(db, "https://ex.ly/m", "Mayor opens a market in Misrata, Libya")
    db.add(ItemTheme(item_id=it.id, theme_id=themes["security"], method="rule", active=True, theme_version=1,
                     evidence={"field": "title", "terms": ["old word"], "query": None}, score=0.8))
    db.commit()
    _fake_model(db, tmp_path)
    dry = retag_all(db, dry_run=True, out=lambda *_: None)
    real = retag_all(db, out=lambda *_: None)
    assert {**dry, "dry_run": False} == real
    assert real["themes"]["security"]["after"] == real["themes"]["security"]["before"]
    assert (_link(db, it.id, themes["security"]).method, _link(db, it.id, themes["security"]).active) == ("model", True)


# ---------------------------------------------------------------- M2 / X3: the hourly scoring
class _ZeroModel:
    """Scores 0 for every theme it knows (enough to mark items as scored)."""

    def __init__(self, themes, version="theme-live"):
        self.themes, self.version = themes, version
        self.th = np.full(len(themes), 0.5)
        self.policy = ["and" if t.startswith("gender") else "or" for t in themes]
        self.veto = np.zeros(len(themes), dtype=bool)
        self.has = np.ones(len(themes), dtype=bool)

    def proba(self, texts):
        return np.zeros((len(texts), len(self.themes)))


def _old(db, url, title, days):
    it = _store(db, url, title, when=utcnow() - timedelta(days=days))
    it.created_at = utcnow() - timedelta(days=days)
    db.commit()
    return it


def test_hourly_scoring_catches_up_on_articles_the_live_version_never_scored(db):
    from app.ml.infer import classify_items
    a = _old(db, "https://ex.ly/a", "Militia clashes in Tripoli, Libya", 30)
    b = _old(db, "https://ex.ly/b", "Hospital in Derna short of medicines, Libya", 20)
    new = _old(db, "https://ex.ly/n", "Water cuts across Sabha, Libya", 1)
    model = _ZeroModel(["security", "health"])
    since = utcnow() - timedelta(days=3)
    res = classify_items(db, model, since=since, catch_up=1)
    assert res["items"] == 2 and res["caught_up"] == 1      # the window, plus the newest older one
    db.expire_all()
    assert db.get(Item, new.id).extra["model"]["v"] == "theme-live" and db.get(Item, b.id).extra["model"]["v"] == "theme-live"
    assert "model" not in (db.get(Item, a.id).extra or {})
    assert classify_items(db, model, since=since, catch_up=5000)["caught_up"] == 1   # a, the next hour
    assert classify_items(db, model, since=since, catch_up=5000)["caught_up"] == 0
    assert classify_items(db, model, since=since)["items"] == 1                       # off by default


def test_classify_dry_run_over_several_batches(db):
    from app.ml.infer import classify_items
    for k in range(3):
        _old(db, f"https://ex.ly/d{k}", f"Militia clashes in Tripoli number {k}, Libya", 1)
    res = classify_items(db, _ZeroModel(["security", "health"]), since=utcnow() - timedelta(days=3), dry_run=True, batch=1)
    assert res["items"] == 3


def test_hourly_skips_the_model_child_when_nothing_is_new(db, tmp_path, monkeypatch):
    from app import jobs
    calls = []
    monkeypatch.setattr(jobs, "collect", lambda key, **kw: None)
    monkeypatch.setattr(jobs, "model_job", lambda *a: calls.append(a))
    it = _old(db, "https://ex.ly/h", "Militia clashes in Tripoli, Libya", 2)
    jobs.hourly()
    assert calls == [] and not jobs.classify_due()            # no model live
    _fake_model(db, tmp_path)
    assert jobs.classify_due()                                # never scored
    db.add(SourceRun(source_key="theme_model", started_at=utcnow(), status="ok"))
    db.commit()
    assert jobs.classify_due()                                # an article the live version has not marked
    it.extra = {**(it.extra or {}), "model": {"v": "theme-live"}}
    db.commit()
    assert not jobs.classify_due()
    jobs.hourly()
    assert calls == []
    fresh = _store(db, "https://ex.ly/h2", "Hospital in Derna short of medicines, Libya", when=utcnow())
    fresh.created_at = utcnow() + timedelta(seconds=1)
    db.commit()
    jobs.hourly()
    assert calls == [("theme_model", "classify-items", "--days", "3", "--catch-up", str(jobs.CATCH_UP))]


# ---------------------------------------------------------------- C-R1.8: the recomputes as children
def test_scheduled_recomputes_run_as_children_under_the_parents_lock(db, monkeypatch):
    import subprocess
    from app import joblock, jobs
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw["env"]))
        return subprocess.CompletedProcess(cmd, 0, stdout='recompute: 3 new duplicates\n{"cells": 41, "changed": 41}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv(joblock.HELD_ENV, raising=False)
    assert jobs.recompute_child(weeks=12) == {"cells": 41, "changed": 41}
    cmd, env = calls[0]
    assert cmd[1:] == ["-m", "app.cli", "recompute", "--weeks", "12"] and env[joblock.HELD_ENV] == "1"
    assert jobs.recompute_child()["cells"] == 41 and calls[1][0][1:] == ["-m", "app.cli", "recompute"]
    runs = db.scalars(select(SourceRun).where(SourceRun.source_key == "recompute")).all()
    assert [(r.status, r.rows) for r in runs] == [("ok", 41), ("ok", 41)]
    assert jobs.JOBS["recompute"] is jobs.recompute_child
    src = (Path(__file__).resolve().parents[1] / "app" / "jobs.py").read_text(encoding="utf-8")
    assert 'sched.add_job(recompute_child, "cron", minute=45' in src and 'sched.add_job(recompute_child, "cron", hour=3, minute=30' in src
    assert 'sched.add_job(recompute, "cron"' not in src


def test_the_recompute_command_prints_json_for_the_parent_and_seeds_nothing(db, monkeypatch, capsys):
    import json
    from app import cli, jobs
    monkeypatch.setattr(jobs, "recompute", lambda weeks=None: 5 if weeks == 12 else 9)
    seeded = []
    monkeypatch.setattr("app.seed.seed_all", lambda s: seeded.append(1))
    assert cli.main(["recompute", "--weeks", "12"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"cells": 5, "changed": 5}
    assert seeded == []                                  # hourly children never seed (deleted key events would return)
    assert cli.main(["recompute"]) == 0 and json.loads(capsys.readouterr().out.strip().splitlines()[-1])["cells"] == 9


def test_nightly_checkpoints_the_wal_and_marks_recurring_when_the_module_exists(db, monkeypatch):
    import sys
    import types
    from app import jobs
    from app.db import engine
    monkeypatch.setattr(jobs, "collect", lambda key, **kw: None)
    monkeypatch.setattr(jobs, "_resolve_links", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "model_job", lambda *a: None)
    monkeypatch.setattr(jobs.learning, "purge_old_events", lambda s: 0)
    monkeypatch.setattr(jobs.learning, "purge_account_leftovers", lambda s: {})
    monkeypatch.setitem(sys.modules, "app.recurring", None)   # not written yet: the night goes on without it
    _store(db, "https://ex.ly/wal", "Militia clashes in Tripoli, Libya")
    wal = Path(engine.url.database + "-wal")
    jobs.nightly()
    assert not wal.exists() or wal.stat().st_size == 0        # wal_checkpoint(TRUNCATE) ran
    marked = []
    fake = types.ModuleType("app.recurring")
    # the real one (app/recurring.py) returns its counts as a dict; nightly logs them and returns "marked"
    fake.mark_recurring = lambda s: marked.append(1) or {"headlines": 1, "marked": 3, "cleared": 0, "articles": 3, "days": 30,
                                                          "since": "2026-09-18"}
    monkeypatch.setitem(sys.modules, "app.recurring", fake)
    jobs.nightly()
    assert marked == [1]


def test_nightly_check_skips_before_loading_the_bundle(db, tmp_path, monkeypatch):
    from app.ml import commands, infer, train
    assert train.labels_fingerprint is L.labels_fingerprint
    row = _fake_model(db, tmp_path)
    row.trained_on = {**row.trained_on, "labels": {"items": 3, "fingerprint": L.labels_fingerprint(db)}}
    db.commit()
    monkeypatch.setattr(infer, "load_bundle", lambda p: pytest.fail("the bundle was loaded"))
    out = commands.train_small_model(db, [])
    assert out["skipped"].startswith("no new labels") and out["changed"] == 0 and out["live"] == "theme-live"


# ---------------------------------------------------------------- m4: register-model twice
def test_register_model_twice_with_the_same_file_does_nothing(db, tmp_path, capsys):
    import joblib
    from app.ml import commands
    path = tmp_path / "bundle.joblib"
    joblib.dump({"version": "theme-r1", "trained_on": {}, "metrics": {}, "thresholds": {"security": 0.3}}, path)
    first = commands.register_model(db, [str(path), "--activate"])
    assert first["changed"] == 1 and first["active"]
    again = commands.register_model(db, [str(path), "--activate"])
    assert again == {"version": "theme-r1", "path": first["path"], "active": True, "already_registered": True,
                     "changed": 0}
    assert "already registered" in capsys.readouterr().out
    other = tmp_path / "other.joblib"
    joblib.dump({"version": "theme-r1", "trained_on": {"x": 1}, "metrics": {}, "thresholds": {}}, other)
    with pytest.raises(ValueError):
        commands.register_model(db, [str(other)])


# ---------------------------------------------------------------- X4: generic words from the links' evidence
def test_generic_only_reads_the_evidence():
    from app.api.labelling import _generic_only
    assert _generic_only([{"terms": ["minister"]}]) == "minister"
    assert _generic_only([{"terms": ["minister"]}, {"field": "title", "terms": ["minister"], "query": None}]) == "minister"
    assert _generic_only([{"terms": ["مقتل"]}]) == "مقتل"
    assert _generic_only([{"terms": ["minister"]}, {"terms": ["clashes"]}]) is None
    assert _generic_only([{"terms": ["minister", "council"]}]) is None
    assert _generic_only([{"terms": ["clashes"]}]) is None
    assert _generic_only([None]) is None


def test_review_queue_generic_word_ignores_other_words_in_the_raw_snippet(client, users, db):
    # the snippet names one security word, too few for a snippet link: the only link rests on "minister"
    it = _store(db, "https://ex.ly/g", "Minister visits Sabha, Libya", when=utcnow() - timedelta(days=2),
                snippet="The visit followed clashes last week.")
    rules = {lk.theme_id: lk.evidence for lk in db.scalars(select(ItemTheme).where(
        ItemTheme.item_id == it.id, ItemTheme.method == "rule", ItemTheme.active.is_(True)))}
    assert rules and all(ev["terms"] == ["minister"] for ev in rules.values())
    login(client, "j@example.org", "journo-password-1")
    by = {x["id"]: x for x in client.get("/api/review-queue?n=10").json()["items"]}
    assert by[it.id]["reason"] == "generic_term" and by[it.id]["generic_term"] == "minister"


# ---------------------------------------------------------------- X5: outlet families in pickup and reprints
def test_pickup_and_reprints_count_outlet_families():
    from app.network import find_syndication, story_pickup
    # 11 is a page of the website 10. The website's article (1) is 60 h before outlet 12's (3), too far
    # apart to match, but its own page's post (2) matches both: the story keeps all three
    items = [(1, 10, T0, STORY), (2, 11, T0 + timedelta(hours=30), STORY), (3, 12, T0 + timedelta(hours=60), STORY)]
    family = {10: 10, 11: 10, 12: 12}
    pairs, stories = find_syndication(items, clusters=True, family=family)
    assert pairs == {(11, 12): 1}                            # no reprint arrow inside the family
    assert sorted(map(sorted, stories)) == [[1, 2, 3]]
    pick = story_pickup(items, stories, family)
    assert pick[1]["total"] == pick[2]["total"] == pick[3]["total"] == 2
    plain = find_syndication(items, clusters=True)
    assert plain[0] == {(10, 11): 1, (11, 12): 1} and story_pickup(items, plain[1])[1]["total"] == 3


def test_compute_counts_a_page_and_its_website_once(db):
    from datetime import date
    from app.network import compute
    title = "Libya: " + STORY
    a = _store(db, "https://a.ly/1", title, when=T0)
    b = _store(db, "https://b.ly/1", title, when=T0 + timedelta(hours=1))
    c = _store(db, "https://c.ly/1", title, when=T0 + timedelta(hours=2))
    page = db.get(Outlet, b.outlet_id)
    page.external = {"parent": db.get(Outlet, a.outlet_id).domain}
    db.commit()
    compute(db, a.country_id, weeks=2, today=date(2026, 10, 12))
    got = {r.item_id: r.total for r in db.scalars(select(ItemEngagement).where(ItemEngagement.source == "pickup"))}
    assert got[a.id] == got[b.id] == got[c.id] == 2
    syn = {(e.source_node, e.target_node) for e in db.scalars(select(NetworkEdgeWeek).where(
        NetworkEdgeWeek.kind == "syndication"))}
    assert (f"o:{a.outlet_id}", f"o:{b.outlet_id}") not in syn and (f"o:{a.outlet_id}", f"o:{c.outlet_id}") in syn


# ---------------------------------------------------------------- m3: short network write transactions
def test_network_work_happens_outside_the_write_transaction(db, monkeypatch):
    from datetime import date
    import app.network as net
    from app.db import engine
    for k, host in enumerate(("a.ly", "b.ly", "c.ly")):
        _store(db, f"https://{host}/{k}", "Libya: " + STORY, when=T0 + timedelta(hours=k))
    free = []

    def probe():
        con = sqlite3.connect(engine.url.database, timeout=0)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.rollback()
            free.append(True)
        except sqlite3.OperationalError:
            free.append(False)
        finally:
            con.close()

    find, louvain = net.find_syndication, net.nx.community.louvain_communities
    monkeypatch.setattr(net, "find_syndication", lambda *a, **k: (probe(), find(*a, **k))[1])
    monkeypatch.setattr(net.nx.community, "louvain_communities", lambda *a, **k: (probe(), louvain(*a, **k))[1])
    net.compute(db, db.scalar(select(Country.id)), weeks=2, today=date(2026, 10, 12))
    assert len(free) >= 2 and all(free)
    assert db.scalar(select(ItemEngagement.id).where(ItemEngagement.source == "pickup")) is not None
    assert db.execute(text("PRAGMA busy_timeout")).scalar() == 30000


# ---------------------------------------------------------------- m5: seeded feeds and parents
def test_seed_never_puts_back_a_feed_or_parent_an_admin_cleared(db):
    from app.seed import seed_all
    wasat = db.scalar(select(Outlet).where(Outlet.domain == "youtube.com/channel/UCTjGk6smzE1z4P_nI8dUqJw"))
    assert wasat.rss_url and wasat.external["parent"] == "alwasat.ly"
    assert set(wasat.external["seed_filled"]) == {"rss_url", "parent"}
    wasat.rss_url = None                                     # an admin stops the feed
    wasat.external = {k: v for k, v in wasat.external.items() if k != "parent"}   # and unlinks the website
    db.commit()
    seed_all(db)
    db.commit()
    db.expire_all()
    wasat = db.get(Outlet, wasat.id)
    assert wasat.rss_url is None and "parent" not in wasat.external
    # a channel stored before the seed noted what it filled: an empty field is filled once
    hnec = db.scalar(select(Outlet).where(Outlet.domain == "youtube.com/channel/UCnygNoGcbVM8AY4fIa3Nm8w"))
    hnec.rss_url, hnec.external = None, {}
    db.commit()
    seed_all(db)
    db.commit()
    db.expire_all()
    hnec = db.get(Outlet, hnec.id)
    assert hnec.rss_url.endswith("UCnygNoGcbVM8AY4fIa3Nm8w") and hnec.external["parent"]
    assert set(hnec.external["seed_filled"]) == {"rss_url", "parent"}
