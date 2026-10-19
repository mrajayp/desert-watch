"""The job lock the CLI, the scheduler and the children share (joblock.py, plan C-R1.2), with the
runbook that explains it (docs/DEPLOY.md)."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app import joblock

from .conftest import ids
from .test_integ_model import _fake_model

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def _holder(seconds: float) -> subprocess.Popen:
    """Another process that holds the job lock for a while (a CLI step, or the web process's job)."""
    code = ("import sys, time\nfrom app import joblock\nwith joblock.held(job='test holder'):\n"
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


def test_the_holder_sidecar_names_the_job_and_clears_when_the_lock_is_free():
    assert joblock.holder() is None
    seen = []
    with joblock.held(job="hourly"):
        info = joblock.holder()
        assert info["job"] == "hourly" and info["pid"] and info["since"]
        t = threading.Thread(target=lambda: seen.append(joblock.holder()))   # another thread sees it held
        t.start()
        t.join(5)
    assert seen and seen[0]["job"] == "hourly"
    assert joblock.holder() is None and not joblock.holder_path().exists()
    # a sidecar left behind by a crash is not a holder: the lock itself decides
    joblock.holder_path().write_text('{"pid": 1, "job": "ghost", "since": "x"}', encoding="utf-8")
    assert joblock.holder() is None
    joblock.holder_path().unlink(missing_ok=True)


def test_acquire_with_a_timeout_gives_up_while_another_process_holds_the_lock():
    p = _holder(4)
    try:
        t0 = time.time()
        assert joblock.acquire(timeout=0.6) is False and time.time() - t0 >= 0.5
        assert joblock.JobLock("ai_audit").acquire(timeout=0.3) is False
        assert not joblock.is_held()
        info = joblock.holder()
        # the venv's python.exe is a launcher that starts the real interpreter, so p.pid is not the holder's
        assert info["job"] == "test holder" and isinstance(info["pid"], int) and info["pid"] != os.getpid()
    finally:
        p.kill()
        p.wait(10)
    lock = joblock.JobLock("ai_audit")
    assert lock.acquire(timeout=5) is True and joblock.holder()["job"] == "ai_audit"
    lock.release()
    assert joblock.holder() is None


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


def test_a_child_told_the_lock_is_held_does_not_take_it_again(monkeypatch):
    p = _holder(4)                               # started before the variable is set: the holder must take the lock
    monkeypatch.setenv(joblock.HELD_ENV, "1")
    try:
        t0 = time.time()
        with joblock.held(job="child"):          # would wait 4 s for its parent otherwise
            assert time.time() - t0 < 1.0
            assert joblock.holder()["job"] == "test holder"   # the parent still holds it
    finally:
        p.kill()
        p.wait(10)


def test_an_admin_theme_save_waits_for_a_running_job(db):
    from app.api.admin import _retag_theme
    themes, _ = ids(db)
    p = _holder(1.5)
    t0 = time.time()
    _retag_theme(themes["security"], recompute=False, classify=False)
    assert time.time() - t0 >= 0.8
    p.wait(10)


def test_the_six_hourly_job_takes_the_lock_per_collector(monkeypatch):
    from app import jobs
    holders = []

    def collect(key, **kw):
        holders.append((key, joblock.holder()["job"]))

    monkeypatch.setattr(jobs, "collect", collect)
    jobs.six_hourly()
    assert [k for k, _ in holders] == ["official", "gnews", "gdelt", "fb_url", "wikireading", "fxrate"]
    assert all(job == "collect" for _, job in holders) and joblock.holder() is None


# ---------------------------------------------------------------- X2 follow-up: model links go back to the rules (C-R2.8)
def _set_terms(db, theme_id, en, ar):
    from app.models import Theme
    th = db.get(Theme, theme_id)
    th.en_terms, th.ar_terms = list(en), list(ar)
    th.version += 1
    db.commit()


def test_a_link_the_rules_match_again_goes_back_to_them(db, tmp_path):
    from app.ml.infer import apply_link, reset_model_links
    from app.models import Theme
    from app.retag import retag_all, retag_theme
    from .test_integ_model import _link, _store
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
    from app.models import ItemTheme, Theme
    from app.retag import retag_all
    from .test_integ_model import _link, _store
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
    from app.models import ItemTheme, Theme
    from .test_integ_model import _link, _store
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


# ---------------------------------------------------------------- digest and Contribute: only lenses the site offers (C-R2.8)
def _cells(db, cid, national, week, themes):
    """Audience judged on every theme for 5 weeks (an available lens), one big humanitarian gap (not available)."""
    from datetime import timedelta
    from sqlalchemy import select
    from app.models import CellWeek
    for w in range(5):
        for tid in themes.values():
            db.add(CellWeek(country_id=cid, theme_id=tid, region_id=national, week_start=week - timedelta(weeks=w),
                            lens="audience", need=100, coverage=50, gap=0.0, insufficient=False, flags=[], breakdown={}))
    big = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.week_start == week,
                                           CellWeek.lens == "audience"))
    big.gap, big.verdict = 0.9, "short"
    db.add(CellWeek(country_id=cid, theme_id=themes["migration"], region_id=national, week_start=week,
                    lens="humanitarian", need=2, coverage=1, gap=1.5, insufficient=False, flags=[], verdict="short", breakdown={}))
    db.commit()


def test_digest_and_contribute_leave_out_lenses_the_site_does_not_offer(client, users, db):
    from datetime import date
    from sqlalchemy import select
    from app import digest
    from app.api.gaps import available_lenses
    from app.models import Country, Theme
    from .conftest import login
    themes, regions = ids(db)
    country = db.scalar(select(Country))
    week = date(2026, 10, 5)
    active = {t.slug: t.id for t in db.scalars(select(Theme).where(Theme.active.is_(True)))}
    _cells(db, country.id, regions["national"], week, active)
    assert available_lenses(db, country.id) == {"audience"}
    facts = digest.build_facts(db, country, week)
    assert facts["top_gaps"][0]["lens"] == "audience" and facts["top_gaps"][0]["gap"] == 0.9
    assert facts["lenses_with_data"] == ["audience"] and facts["lenses_offered"] == ["audience"]
    assert any(x.startswith("gaps are reported only on the lenses the site offers now (audience)") for x in facts["known_limits"])
    login(client, "j@example.org", "journo-password-1")
    d = client.get("/api/contribute").json()
    assert [(g["lens"], g["theme_id"]) for g in d["gaps"]] == [("audience", themes["health"])]
    assert d["lenses"]["offered"] == ["audience"] and d["lenses"]["note"].startswith("Gaps are listed only for the lenses")
    ar = client.get("/api/contribute", headers={"X-Lang": "ar"}).json()["lenses"]["note"]
    assert ar.startswith("تُعرض الفجوات")


def test_runbook():
    md = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    assert "flyctl secrets set DW_SCHEDULER=0 --stage" in md and "flyctl secrets unset DW_SCHEDULER" in md
    flat = " ".join(md.split())
    assert "After classify-items --reset, run retag-all" in flat
    assert "Once a model is live, run classify-items --all after every retag-all" in flat
    assert "## Restore" in md and "incoming.db.gz" in md and "## Backups" in md and "flyctl storage create" in flat
    assert "7 daily, 4 weekly and 3 monthly" in flat and "/api/admin/health" in md
    assert ";" not in md and chr(0x2014) not in md
