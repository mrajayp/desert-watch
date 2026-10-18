"""Matching AI-audit links to the outlet register. Read-only: it never creates an Outlet row
(ingest.resolve_outlet does, so it is not used here).

Order (docs/research/ai_answers_audit_scope.md, section 4 "Mapping domains to outlets"):
  1. unwrap Google redirect and AMP links and drop tracking parameters (srsltid on top of ingest's list);
  2. a social post goes to the registered account. An account nobody listed, or a post whose account
     cannot be read from the link, is kept as its platform only: no account name, no path, no title,
     so a private person's account is never stored. Open-posting sites (reddit, medium ...) likewise;
  3. path outlets (hrw.org/ar), then the exact host, then the parent domain, longest known suffix first
     (arabic.cnn.com -> cnn.com, never co.uk);
  4. anything else is kept with no outlet (match "unknown").
A website and its own social accounts share a family (dedupe.outlet_families). The language of a link
comes from its title's script, then URL markers (/ar/, ar., arabic.), then the outlet's languages."""
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..collectors.galerts import unwrap
from ..dedupe import outlet_families
from ..ingest import _TRACKING, SOCIAL, USER_PLATFORMS, domain_of, normalise_url, social_outlet
from ..models import AiSource, Outlet
from ..textnorm import detect_lang

# Tracking parameters the matcher drops (ingest keeps its own, shorter list). utm_* are dropped by prefix:
# OpenAI adds utm_source=openai to every link it cites.
TRACKING = _TRACKING | {"srsltid", "gclsrc", "msclkid", "igshid", "mc_cid", "mc_eid", "_ga", "ocid", "gbraid",
                        "wbraid", "gad_source", "dclid", "yclid", "_hsenc", "_hsmi"}
# Second-level labels under a country code that are registries, not sites (co.uk, com.ly, gov.ly ...).
_REGISTRY_LABELS = {"co", "com", "org", "net", "gov", "edu", "ac", "or", "ne", "go", "mil", "nic", "sch", "plc",
                    "ltd", "info", "med", "law", "biz", "name", "web", "int"}
_AMP_CACHE = re.compile(r"^/[a-z]/(s/)?(.+)$")


@dataclass
class Match:
    url: str              # what is stored (admin-only); the platform root for an unlisted social account
    domain: str
    outlet_id: int | None
    family_id: int | None
    match: str            # path | exact | parent | social | unknown
    lang: str             # ar | en | und
    keep_title: bool = True


def clean_url(url: str) -> str:
    """The link with Google redirect and AMP wrappers removed and tracking parameters dropped,
    normalised as ingest does (lower-case host, no www., no fragment, no trailing slash)."""
    u = unwrap((url or "").strip())
    p = urlsplit(u)
    host = p.netloc.lower()
    if (host == "google.com" or host.endswith(".google.com")) and p.path.startswith("/amp/"):
        rest = p.path[len("/amp/"):]
        u = ("https://" + rest[2:]) if rest.startswith("s/") else ("http://" + rest)
        u += f"?{p.query}" if p.query else ""
    elif host.endswith(".cdn.ampproject.org") and (m := _AMP_CACHE.match(p.path)):
        u = ("https://" if m.group(1) else "http://") + m.group(2) + (f"?{p.query}" if p.query else "")
    p = urlsplit(u)
    if p.scheme.lower() not in ("http", "https") or not p.netloc:
        return u
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() not in TRACKING and not k.lower().startswith("utm_")]
    path = p.path
    if path.rstrip("/").endswith("/amp"):
        path = path.rstrip("/")[:-4] or "/"
    return normalise_url(urlunsplit((p.scheme, p.netloc, path, urlencode(query), "")))


def url_lang(url: str) -> str | None:
    """'ar' / 'en' from markers in the link: ar./arabic. host labels, /ar/ or /arabic/ path, ?lang=ar."""
    p = urlsplit(url)
    labels = p.netloc.lower().removeprefix("www.").split(".")
    segs = [x.lower() for x in p.path.split("/") if x]
    first = segs[0] if segs else ""
    q = {k.lower(): v.lower() for k, v in parse_qsl(p.query)}
    hint = q.get("lang") or q.get("hl") or ""
    if labels[0] in ("ar", "arabic") or "arabic" in labels[:-1] or first in ("ar", "arabic") \
            or first.startswith("ar-") or hint.startswith("ar"):
        return "ar"
    if labels[0] in ("en", "english") or "english" in labels[:-1] or first in ("en", "english") \
            or first.startswith("en-") or hint.startswith("en"):
        return "en"
    return None


def _registry_like(domain: str) -> bool:
    parts = domain.split(".")
    return len(parts) < 2 or (len(parts) == 2 and len(parts[1]) == 2 and parts[0] in _REGISTRY_LABELS)


def _user_platform(host: str) -> str | None:
    return next((p for p in USER_PLATFORMS if host == p or host.endswith("." + p)), None)


class Matcher:
    """Load the register once, then match() many links."""

    def __init__(self, s: Session):
        self.hosts: dict[str, int] = {}
        self.paths: dict[str, list[tuple[tuple[str, ...], int]]] = {}
        self.social: dict[str, int] = {}
        self.spelling: dict[int, str] = {}     # the register's own spelling (facebook.com/LibyaAlAhrarTV)
        self.langs: dict[int, list[str]] = {}
        for oid, domain, langs in s.execute(select(Outlet.id, Outlet.domain, Outlet.languages).order_by(Outlet.id)):
            d = (domain or "").strip().lower().removeprefix("www.")
            if not d:
                continue
            self.langs[oid] = list(langs or [])
            self.spelling[oid] = domain.strip().removeprefix("www.")
            host, _, path = d.partition("/")
            if path and host in SOCIAL:
                self.social.setdefault(d, oid)
            elif path:
                prefix = tuple(x for x in path.split("/") if x)
                if prefix:
                    self.paths.setdefault(host, []).append((prefix, oid))
            else:
                self.hosts.setdefault(d, oid)
        for v in self.paths.values():
            v.sort(key=lambda x: -len(x[0]))   # longest path first
        self.families = outlet_families(s)

    def family(self, oid: int | None) -> int | None:
        return self.families.get(oid, (oid,))[0] if oid is not None else None

    def lang(self, title: str | None, url: str, oid: int | None) -> str:
        if title and title.strip():
            got = detect_lang(title)
            if got in ("ar", "en"):
                return got
        marker = url_lang(url)
        if marker:
            return marker
        langs = (self.langs.get(oid) or []) if oid is not None else []
        return langs[0] if len(langs) == 1 and langs[0] in ("ar", "en") else "und"

    def _hit(self, url: str, domain: str, oid: int, how: str, title: str | None) -> Match:
        return Match(url=url, domain=domain, outlet_id=oid, family_id=self.family(oid), match=how,
                     lang=self.lang(title, url, oid))

    def match(self, url: str, title: str | None = None) -> Match | None:
        """None for a link that is not http(s) (OpenAI's oai-sports / oai-weather feeds, empty values)."""
        u = clean_url(url)
        if not u.startswith(("http://", "https://")):
            return None
        host = domain_of(u)
        if not host or "." not in host:
            return None
        soc = social_outlet(u)
        if soc:
            account = soc[0]
            if "/" in account and (oid := self.social.get(account.lower())):
                return self._hit(u, self.spelling.get(oid, account), oid, "social", title)
            platform = account.split("/", 1)[0]
            # language from the title before it is dropped; the tag names nobody
            return Match(url=f"https://{platform}/", domain=platform, outlet_id=None, family_id=None, match="social",
                         lang=self.lang(title, u, None), keep_title=False)
        if up := _user_platform(host):
            return Match(url=f"https://{up}/", domain=up, outlet_id=None, family_id=None, match="social",
                         lang=self.lang(title, u, None), keep_title=False)
        segs = tuple(x.lower() for x in urlsplit(u).path.split("/") if x)
        for prefix, oid in self.paths.get(host, []):
            if segs[:len(prefix)] == prefix:
                return self._hit(u, f"{host}/{'/'.join(prefix)}", oid, "path", title)
        if oid := self.hosts.get(host):
            return self._hit(u, host, oid, "exact", title)
        labels = host.split(".")
        for i in range(1, len(labels) - 1):
            parent = ".".join(labels[i:])
            if _registry_like(parent):
                break
            if oid := self.hosts.get(parent):
                return self._hit(u, parent, oid, "parent", title)
        return Match(url=u, domain=host, outlet_id=None, family_id=None, match="unknown", lang=self.lang(title, u, None))


def rematch(s: Session) -> dict:
    """Redo the matching over every stored link (after a register change). Links stored as a platform
    only stay that way: their account was never kept."""
    m = Matcher(s)
    changed = total = 0
    # streamed in batches: the table grows by about a thousand links a week and the machine has 512 MB
    for row in s.scalars(select(AiSource).order_by(AiSource.id).execution_options(yield_per=500)):
        total += 1
        res = m.match(row.url, row.title)
        if res is None:
            continue
        new = {"domain": res.domain[:200], "outlet_id": res.outlet_id, "family_id": res.family_id, "match": res.match,
               "lang": res.lang if res.lang != "und" else (row.lang or "und")}
        if not res.keep_title:
            new.update(url=res.url, title=None)
        if any(getattr(row, k) != v for k, v in new.items()):
            for k, v in new.items():
                setattr(row, k, v)
            changed += 1
    s.commit()
    return {"rows": total, "changed": changed}
