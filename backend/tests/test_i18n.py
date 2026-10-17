"""The API speaks the interface language: every wrapped string has Arabic, error messages are wrapped,
and the X-Lang header reaches the endpoint (sync endpoints run in a worker thread)."""
import ast
import re
from pathlib import Path

from app import i18n
from tests.conftest import login

APP = Path(__file__).resolve().parent.parent / "app"
PH = re.compile(r"\{(\w+)\}")


def _sources():
    return [p for p in APP.rglob("*.py") if "locales" not in p.parts]


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return None
    return None


def _calls(tree, names):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            n = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if n in names:
                yield node


def test_every_wrapped_string_has_arabic_with_the_same_placeholders():
    cat = i18n.load()
    missing, bad = [], []
    for p in _sources():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for call in _calls(tree, {"tr", "N_"}):
            if not call.args:
                continue
            s = _literal(call.args[0])
            if isinstance(call.args[0], ast.JoinedStr):
                bad.append(f"{p.name}:{call.lineno} f-string inside tr(): use {{placeholders}} and keyword arguments")
                continue
            if s is None:
                continue
            ar = cat.get(s)
            if not ar:
                missing.append(f"{p.name}:{call.lineno} {s[:70]!r}")
            elif set(PH.findall(s)) != set(PH.findall(ar)):
                bad.append(f"{p.name}:{call.lineno} placeholders differ for {s[:50]!r}")
            elif not re.search(r"[؀-ۿ]", ar):
                bad.append(f"{p.name}:{call.lineno} Arabic entry has no Arabic letters for {s[:50]!r}")
    assert not missing, "no Arabic for:\n" + "\n".join(missing)
    assert not bad, "\n".join(bad)


def test_error_messages_are_wrapped():
    plain = []
    for p in _sources():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for call in _calls(tree, {"HTTPException"}):
            for a in call.args[1:2] + [k.value for k in call.keywords if k.arg == "detail"]:
                if _literal(a) is not None or isinstance(a, ast.JoinedStr):
                    plain.append(f"{p.relative_to(APP)}:{call.lineno}")
    assert not plain, "HTTPException detail not wrapped in tr():\n" + "\n".join(plain)


def test_the_header_reaches_the_endpoint(client, users):
    # async middleware -> sync endpoint in a worker thread -> sync dependency: the language arrives everywhere
    r = client.post("/api/auth/login", json={"email": "nobody@example.org", "password": "x"}, headers={"X-Lang": "ar"})
    assert r.json()["detail"] == "البريد الإلكتروني أو كلمة المرور غير صحيحة."
    assert client.post("/api/auth/login", json={"email": "nobody@example.org", "password": "x"}).json()["detail"] == "Email or password is wrong."
    assert client.get("/api/me", headers={"X-Lang": "ar"}).json()["detail"] == "لم يتم تسجيل الدخول"
    login(client, "j@example.org", "journo-password-1")
    health = client.get("/api/sources/health", headers={"X-Lang": "ar"}).json()
    assert all(re.search(r"[؀-ۿ]", h["label"]) for h in health)
    ind = client.get("/api/indicators", params={"days": 30}, headers={"X-Lang": "ar"}).json()
    assert ind["charts"]["usd"] == "سعر الدولار الأمريكي بالدينار الليبي"


def test_every_source_label_and_config_reason_has_arabic():
    from app.collectors import COLLECTORS, EXTRA_HEALTH
    cat = i18n.load()
    assert all(cat.get(v[1]) for v in COLLECTORS.values()) and all(cat.get(v) for v in EXTRA_HEALTH.values())
    import yaml
    cfg = yaml.safe_load((APP.parent.parent / "config" / "countries" / "libya.yaml").read_text(encoding="utf-8"))
    assert all(e.get("label_ar") for e in cfg["events"])
    assert set(cfg["gtrends"]["unmeasured_ar"]) == set(cfg["gtrends"]["unmeasured"])


def test_how_the_numbers_work_exists_in_arabic():
    content = APP / "content"
    for md in content.glob("*.md"):
        if md.name.endswith(".ar.md"):
            continue
        assert (content / f"{md.stem}.ar.md").exists(), f"{md.name} has no Arabic version"
