"""Fix round 2 on integ/2026-10-16 (review_fixes.md): the job lock the CLI shares with the scheduler
(prod M1), model links going back to the rules (X2 follow-up), no 4-week usual level on a search
window that misses a week (X1 remnant), lens availability in the digest and on Contribute, and
Admin saves sharing one re-score."""
import subprocess
import sys
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app import joblock
from app.models import CellWeek, Country, ItemTheme, Theme

from .conftest import ids, login
from .test_integ_model import _fake_model, _link, _store

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


@pytest.fixture(autouse=True)
def _no_follow_up_left_running():
    yield
    from app.api import admin
    admin._FOLLOW.update(classify=False, recompute=False, running=False)


# ---------------------------------------------------------------- prod M1: the job lock
def _holder(seconds: float) -> subprocess.Popen:
    """Another process that holds the job lock for a while (a CLI step, or the web process's job)."""
    code = ("import sys, time\nfrom app import joblock\nwith joblock.held():\n"
            f"    print('held', flush=True)\n    time.sleep({seconds})\n")
    p = subprocess.Popen([sys.executable, "-c", code], cwd=BACKEND, stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def _other_process_can_lock() -> bool:
    code = "from app import joblock\nfd = joblock._open()\nprint(joblock._try_lock(fd))"
    r = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    return r.stdout.strip() == "True"


def test_the_job_lock_keeps_other_processes_out_and_is_reentrant():
    with joblock.held():
        with joblock.held():                 # a CLI command that runs a scheduled job takes it once
            assert joblock.is_held()
            assert not _other_process_can_lock()
        assert not _other_process_can_lock()
    assert not joblock.is_held() and _other_process_can_lock()


def test_a_thread_waits_for_a_job_in_another_thread():
    order = []
    inside = threading.Event()

    def job():
        with joblock.held():
            inside.set()
            time.sleep(0.5)
            order.append("first")

    t = threading.Thread(target=job)
    t.start()
    inside.wait(5)
    assert not joblock.is_held()             # held by the other thread, not this one
    with joblock.held():
        order.append("second")
    t.join()
    assert order == ["first", "second"]


def test_cli_data_commands_wait_for_a_running_job(db, capsys):
    from app.cli import main
    p = _holder(1.5)
    t0 = time.time()
    assert main(["dedupe"]) == 0
    assert time.time() - t0 >= 0.8
    assert "Waiting for it to finish" in capsys.readouterr().err
    p.wait(10)
    p = _holder(60)
    try:
        assert main(["init"]) == 0 and main(["retag-all", "--dry-run"]) == 0   # quick and read-only ones never wait
        assert p.poll() is None and "Waiting" not in capsys.readouterr().err  # done while the job still runs
    finally:
        p.kill()
        p.wait(10)


def test_the_scoring_child_skips_the_lock_only_when_its_parent_holds_it(db, tmp_path, monkeypatch):
    from app import jobs
    envs = []

    def fake_run(cmd, **kw):
        envs.append(kw["env"])
        return subprocess.CompletedProcess(cmd, 0, stdout='{"changed": 0}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv(joblock.HELD_ENV, raising=False)
    _fake_model(db, tmp_path)
    jobs.model_job("theme_model", "classify-items", "--days", "3")
    jobs.JOBS["classify"]()
    assert joblock.HELD_ENV not in envs[0]   # nobody holds it: the child takes it itself
    assert envs[1][joblock.HELD_ENV] == "1"  # the hourly job holds it: the child must not wait for its parent


def test_runbook_and_steps_script():
    md = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    assert "flyctl secrets set DW_SCHEDULER=0 --stage" in md and "flyctl secrets unset DW_SCHEDULER" in md
    flat = " ".join(md.split())
    assert "After classify-items --reset, run retag-all" in flat
    assert "Once a model is live, run classify-items --all after every retag-all" in flat
    assert ";" not in md and chr(0x2014) not in md
    sh = (ROOT / "scripts" / "apply_review_2026_10_16.sh").read_text(encoding="utf-8")
    assert "docs/DEPLOY.md" in sh and sh.index("retag-all") < sh.index("classify-items --all")


# ---------------------------------------------------------------- X2 follow-up: model links go back to the rules
def _set_terms(db, theme_id, en, ar):
    th = db.get(Theme, theme_id)
    th.en_terms, th.ar_terms = list(en), list(ar)
    th.version += 1
    db.commit()


def test_a_link_the_rules_match_again_goes_back_to_them(db, tmp_path):
    from app.ml.infer import apply_link, reset_model_links
    from app.retag import retag_all, retag_theme
    themes, _ = ids(db)
    sec = themes["security"]
    it = _store(db, "https://ex.ly/back", "Militia clashes in Tripoli, Libya")
    lk = _link(db, it.id, sec)
    words, rule_ev = set(lk.evidence["terms"]), dict(lk.evidence)
    lk.score, lk.model_version = 0.9, "theme-live"
    db.commit()
    _fake_model(db, tmp_path)
    th = db.get(Theme, sec)
    en, ar = list(th.en_terms), list(th.ar_terms)
    # an Admin edit drops the words: the model keeps the link (rule OR p >= t)
    _set_terms(db, sec, [w for w in en if w not in words], [w for w in ar if w not in words])
    retag_theme(db, sec)
    lk = _link(db, it.id, sec)
    assert (lk.method, lk.active, lk.evidence["was"]) == ("model", True, "rule")
    # and the undo gives it back to the rules, with the rule evidence and the score kept in its column
    _set_terms(db, sec, en, ar)
    retag_theme(db, sec)
    lk = _link(db, it.id, sec)
    assert (lk.method, lk.active, lk.score, lk.evidence) == ("rule", True, 0.9, rule_ev)
    assert retag_all(db, out=lambda *_: None)["links_changed"] == 0
    # a reset or a version that scores it lower no longer takes it away
    assert reset_model_links(db).get("model_links_off", 0) == 0
    lk = _link(db, it.id, sec)
    assert (lk.method, lk.active) == ("rule", True)
    assert apply_link(db, it.id, sec, 1, lk, 0.01, 0.3, "or", False, "theme-next") == "unchanged" and lk.active


def test_a_new_term_takes_over_a_model_link_also_after_a_reset(db, tmp_path):
    from app.ml.infer import reset_model_links
    from app.retag import retag_all
    themes, _ = ids(db)
    sec = themes["security"]
    it = _store(db, "https://ex.ly/quad", "Quadcopter seen over a farm near Sirte, Libya")
    assert _link(db, it.id, sec) is None
    db.add(ItemTheme(item_id=it.id, theme_id=sec, method="model", active=True, theme_version=1,
                     evidence={"model": 0.8}, score=0.8, model_version="theme-live"))
    db.commit()
    _fake_model(db, tmp_path)
    assert reset_model_links(db)["model_links_off"] == 1
    assert (_link(db, it.id, sec).method, _link(db, it.id, sec).active) == ("model", False)
    th = db.get(Theme, sec)
    _set_terms(db, sec, [*th.en_terms, "quadcopter"], th.ar_terms)
    dry = retag_all(db, dry_run=True, out=lambda *_: None)
    real = retag_all(db, out=lambda *_: None)
    assert {**dry, "dry_run": False} == real
    lk = _link(db, it.id, sec)
    assert (lk.method, lk.active, lk.evidence["terms"], lk.score) == ("rule", True, ["quadcopter"], 0.8)


def test_retag_never_writes_over_a_correction_made_to_a_model_link_mid_batch(db, tmp_path, monkeypatch):
    from sqlalchemy import update

    import app.retag as rt
    from app.db import engine
    themes, _ = ids(db)
    sec = themes["security"]
    it = _store(db, "https://ex.ly/race", "Quadcopter over Zawiya, Libya")
    db.add(ItemTheme(item_id=it.id, theme_id=sec, method="model", active=True, theme_version=1,
                     evidence={"model": 0.8}, score=0.8))
    db.commit()
    th = db.get(Theme, sec)
    _set_terms(db, sec, [*th.en_terms, "quadcopter"], th.ar_terms)
    item_id, plan = it.id, rt.plan_item

    def racing(item, *a, **k):
        p = plan(item, *a, **k)
        if item.id == item_id:   # a person says it is not about security before the hand-back is written
            with engine.begin() as con:
                con.execute(update(ItemTheme).where(ItemTheme.item_id == item_id, ItemTheme.theme_id == sec)
                            .values(method="user", active=False))
        return p

    monkeypatch.setattr(rt, "plan_item", racing)
    rt.retag_all(db, out=lambda *_: None)
    lk = _link(db, item_id, sec)
    assert (lk.method, lk.active) == ("user", False)


def test_reset_says_to_retag_next(db, capsys):
    from app.cli import main
    assert main(["classify-items", "--reset"]) == 0
    out = capsys.readouterr().out
    assert "Run retag-all next" in out and '"next": "retag-all"' in out


# ---------------------------------------------------------------- X1 remnant: the gap panel's 4-week line
def test_a_search_window_missing_a_week_quotes_no_usual_level(client, users, db):
    from .test_integ_lenses import IMPORTED_TO, LAST_FULL, _search_before_import
    themes, regions = ids(db)
    _search_before_import(db)
    login(client, "j@example.org", "journo-password-1")

    def gap(wk):
        return client.get("/api/gap", params={"theme_id": themes["health"], "region_id": regions["national"],
                                              "lens": "search", "week": wk.isoformat()}).json()["cell"]["breakdown"]
    b = gap(LAST_FULL)
    assert b["search_missing_weeks"] == [LAST_FULL.isoformat()] and b["reason"] == "no_search_data"
    assert b["articles_4w"] is not None and b["expected_4w"] is None
    assert gap(IMPORTED_TO)["expected_4w"] > 0
    panel = (ROOT / "frontend" / "src" / "components" / "GapPanel.jsx").read_text(encoding="utf-8")
    assert "b.expected_4w != null && !b.search_missing_weeks?.length &&" in panel


# ---------------------------------------------------------------- digest and Contribute: only lenses the site offers
def _cells(db, cid, national, week, themes):
    """Audience judged on every theme for 5 weeks (an available lens), one big humanitarian gap (not available)."""
    for w in range(5):
        for tid in themes.values():
            db.add(CellWeek(country_id=cid, theme_id=tid, region_id=national, week_start=week - timedelta(weeks=w),
                            lens="audience", need=100, coverage=50, gap=0.0, insufficient=False, flags=[], breakdown={}))
    big = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.week_start == week,
                                           CellWeek.lens == "audience"))
    big.gap = 0.9
    db.add(CellWeek(country_id=cid, theme_id=themes["migration"], region_id=national, week_start=week,
                    lens="humanitarian", need=2, coverage=1, gap=1.5, insufficient=False, flags=[], breakdown={}))
    db.commit()


def test_digest_and_contribute_leave_out_lenses_the_site_does_not_offer(client, users, db):
    from app import digest
    from app.api.gaps import available_lenses
    themes, regions = ids(db)
    country = db.scalar(select(Country))
    week = date(2026, 10, 5)
    active = {t.slug: t.id for t in db.scalars(select(Theme).where(Theme.active.is_(True)))}
    _cells(db, country.id, regions["national"], week, active)
    assert available_lenses(db, country.id) == {"audience"}
    facts = digest.build_facts(db, country, week)
    assert facts["top_gaps"][0]["lens"] == "audience" and facts["top_gaps"][0]["gap"] == 0.9
    assert facts["lenses_with_data"] == ["audience"]
    login(client, "j@example.org", "journo-password-1")
    gaps = client.get("/api/contribute").json()["gaps"]
    assert [(g["lens"], g["theme_id"]) for g in gaps] == [("audience", themes["health"])]


# ---------------------------------------------------------------- Admin saves share one re-score
def _fake_follow_up(monkeypatch):
    from app import jobs
    calls, running, most = [], [0], [0]
    first, release = threading.Event(), threading.Event()

    def step(name):
        running[0] += 1
        most[0] = max(most[0], running[0])
        calls.append(name)
        if len(calls) == 1:
            first.set()
            release.wait(10)
        running[0] -= 1

    monkeypatch.setitem(jobs.JOBS, "classify_all", lambda: step("classify"))
    monkeypatch.setattr("app.scoring.compute_all", lambda s, **kw: step("compute"))
    monkeypatch.setattr("app.gtrends.flag_missing_weeks", lambda s, *a: 0)
    return calls, most, first, release


def test_saves_during_a_rescore_share_one_more_round(db, monkeypatch):
    from app.api import admin
    calls, most, first, release = _fake_follow_up(monkeypatch)
    t = threading.Thread(target=admin._follow_up, args=(True, True))
    t.start()
    assert first.wait(5)
    assert admin._follow_up(True, True) is False and admin._follow_up(True, True) is False
    release.set()
    t.join(10)
    assert calls == ["classify", "compute", "classify", "compute"] and most[0] == 1
    assert not admin._FOLLOW["running"]


def test_a_save_while_the_follow_up_waits_for_the_lock_joins_it(db, monkeypatch):
    from app.api import admin
    calls, most, first, release = _fake_follow_up(monkeypatch)
    release.set()
    holding, done = threading.Event(), threading.Event()

    def job():  # the scheduler's recompute, say
        with joblock.held():
            holding.set()
            done.wait(10)

    h = threading.Thread(target=job)
    h.start()
    assert holding.wait(5)
    t = threading.Thread(target=admin._follow_up, args=(True, True))
    t.start()
    time.sleep(0.2)
    assert calls == [] and admin._follow_up(True, False) is False
    done.set()
    h.join(10)
    t.join(10)
    assert calls == ["classify", "compute"] and not admin._FOLLOW["running"]
