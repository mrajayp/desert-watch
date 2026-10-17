"""Fetch title/description/date/site name for a user-pasted article URL.
Guarded against SSRF: http(s) only, public IPs only (checked on every redirect),
small byte budget, short timeout."""
import ipaddress
import re
import socket
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx

from . import settings
from .i18n import tr

MAX_BYTES = 600_000
_META = re.compile(r"<meta\s+[^>]*>", re.I | re.S)
_ATTR = re.compile(r'(\w[\w:-]*)\s*=\s*("([^"]*)"|\'([^\']*)\')', re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_HTML_LANG = re.compile(r"<html[^>]*\blang\s*=\s*[\"']?([a-zA-Z-]+)", re.I)


class FetchError(ValueError):
    pass


def _check_public(url: str) -> None:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError(tr("Only http(s) links are accepted."))
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise FetchError(tr("That address could not be resolved.")) from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError(tr("That address is not a public website."))


def parse_meta(html: str) -> dict:
    meta = {}
    for tag in _META.findall(html):
        attrs = {k.lower(): (v1 or v2) for k, _, v1, v2 in _ATTR.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and "content" in attrs and key not in meta:
            meta[key] = unescape(attrs["content"]).strip()
    title = meta.get("og:title") or meta.get("twitter:title")
    if not title:
        m = _TITLE.search(html)
        title = unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else None
    lang = _HTML_LANG.search(html)
    return {
        "title": title,
        "description": meta.get("og:description") or meta.get("description"),
        "site_name": meta.get("og:site_name"),
        "published": meta.get("article:published_time") or meta.get("og:updated_time") or meta.get("date"),
        "lang": lang.group(1).split("-")[0].lower() if lang else None,
    }


def fetch_meta(url: str) -> dict:
    current = url
    with httpx.Client(timeout=10, follow_redirects=False, headers={"User-Agent": settings.USER_AGENT}) as c:
        for _ in range(5):
            _check_public(current)
            with c.stream("GET", current) as r:
                if r.is_redirect:
                    current = urljoin(current, r.headers.get("location", ""))
                    continue
                if r.status_code >= 400:
                    raise FetchError(tr("The site answered {code}.", code=r.status_code))
                buf = b""
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        break
                html = buf.decode(r.encoding or "utf-8", errors="replace")
                return {"final_url": current, **parse_meta(html)}
    raise FetchError(tr("Too many redirects."))
