"""PUT, LIST and DELETE on an S3-compatible bucket with Signature Version 4, over httpx.

No boto3: the backup needs three calls, and a 512 MB machine has no room for a second SDK. The
signing follows the AWS reference (canonical request, string to sign, derived key) and is checked
against the published example vectors in tests/test_backup.py. Path-style addressing
(https://endpoint/bucket/key) works on Tigris and on S3 itself.

    s3 = S3.from_settings()            # None until the bucket's secrets exist
    s3.put("backups/x.db.gz", open(p, "rb"), length, sha256_hex)
    s3.list("backups/")                # [{"key", "size", "last_modified"}, ...]
    s3.delete("backups/x.db.gz")"""
import hashlib
import hmac
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlsplit

import httpx

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
TIMEOUT = httpx.Timeout(300.0, connect=30.0)   # a 50 MB upload on a slow evening


class S3Error(RuntimeError):
    """The server's answer, reduced to its <Code> and <Message> when it is the usual error XML: the
    message is stored in source_run.error and shown on the health strip, so the rest of the body
    (which on AWS names the access key id and the request's headers) stays out of it."""

    def __init__(self, status: int, text: str):
        code, msg = _xml_field(text, "Code"), _xml_field(text, "Message")
        detail = f"{code}: {msg}" if code and msg else (code or msg or text[:300])
        super().__init__(f"S3 answered {status}: {detail[:300]}")
        self.status = status


def _xml_field(text: str, name: str) -> str | None:
    import re
    m = re.search(rf"<{name}>([^<]*)</{name}>", text or "")
    return m.group(1).strip() if m else None


def _enc(s: str) -> str:
    """URI-encode as SigV4 wants it: unreserved characters as they are, everything else %XX."""
    return quote(s, safe="-_.~")


def _canonical_query(params: dict | list[tuple[str, str]] | None) -> str:
    items = list(params.items()) if isinstance(params, dict) else list(params or [])
    return "&".join(f"{_enc(k)}={_enc(str(v))}" for k, v in sorted((str(k), v) for k, v in items))


def canonical_request(method: str, path: str, params, headers: dict, payload_hash: str) -> tuple[str, str]:
    """The canonical request and its signed-headers line. `headers` must already hold host, x-amz-date
    and x-amz-content-sha256. The path is encoded once, segment by segment (S3 does not double-encode)."""
    canon_headers = sorted((k.lower().strip(), " ".join(str(v).split())) for k, v in headers.items())
    signed = ";".join(k for k, _ in canon_headers)
    # unquote first: S3.url() already encodes the key, and a second encoding would sign "%20" as "%2520"
    lines = [method.upper(), quote(unquote(path or "/"), safe="/-_.~"), _canonical_query(params),
             "".join(f"{k}:{v}\n" for k, v in canon_headers), signed, payload_hash]
    return "\n".join(lines), signed


def signing_key(secret: str, day: str, region: str, service: str = "s3") -> bytes:
    k = hmac.new(("AWS4" + secret).encode(), day.encode(), hashlib.sha256).digest()
    for part in (region, service, "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    return k


def sign(method: str, url: str, headers: dict | None, payload_hash: str, key_id: str, secret: str, region: str,
         service: str = "s3", now: datetime | None = None, params=None) -> dict:
    """The headers to send: the given ones plus host, x-amz-date, x-amz-content-sha256 and Authorization."""
    now = now or datetime.now(timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    u = urlsplit(url)
    hdrs = {**(headers or {}), "host": u.netloc, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash}
    canon, signed = canonical_request(method, u.path, params, hdrs, payload_hash)
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canon.encode()).hexdigest()])
    sig = hmac.new(signing_key(secret, day, region, service), to_sign.encode(), hashlib.sha256).hexdigest()
    hdrs["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={key_id}/{scope},SignedHeaders={signed},Signature={sig}")
    return hdrs


class S3:
    def __init__(self, endpoint: str, bucket: str, key_id: str, secret: str, region: str = "auto",
                 client: httpx.Client | None = None):
        self.endpoint, self.bucket, self.key_id, self.secret, self.region = endpoint.rstrip("/"), bucket, key_id, secret, region
        self._client = client

    @classmethod
    def from_settings(cls) -> "S3 | None":
        """The bucket from the environment (the names Fly's Tigris integration sets), or None."""
        from . import settings
        if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_ENDPOINT_URL_S3
                and settings.BUCKET_NAME):
            return None
        return cls(settings.AWS_ENDPOINT_URL_S3, settings.BUCKET_NAME, settings.AWS_ACCESS_KEY_ID,
                   settings.AWS_SECRET_ACCESS_KEY, settings.AWS_REGION or "auto")

    def url(self, key: str = "") -> str:
        return f"{self.endpoint}/{_enc(self.bucket)}" + (f"/{quote(key, safe='/-_.~')}" if key else "")

    def _send(self, method: str, key: str, *, params=None, headers=None, content=None, payload_hash=EMPTY_SHA256):
        url = self.url(key)
        hdrs = sign(method, url, headers, payload_hash, self.key_id, self.secret, self.region, params=params)
        client = self._client or httpx.Client(timeout=TIMEOUT)
        try:
            r = client.request(method, url, params=params, headers=hdrs, content=content)
        finally:
            if client is not self._client:
                client.close()
        if r.status_code >= 300:
            raise S3Error(r.status_code, r.text)
        return r

    def put(self, key: str, content, length: int, sha256_hex: str, content_type: str = "application/octet-stream") -> None:
        """Upload `content` (bytes, or an iterable of bytes chunks, read once) of `length` bytes whose
        SHA-256 is `sha256_hex`. The explicit Content-Length keeps httpx from chunked transfer encoding,
        which S3 does not accept on a plain PUT."""
        self._send("PUT", key, headers={"content-type": content_type, "content-length": str(length)},
                   content=content, payload_hash=sha256_hex)

    def list(self, prefix: str = "") -> list[dict]:
        """Every object under the prefix: {"key", "size", "last_modified"}. Follows continuation tokens."""
        out, token = [], None
        while True:
            params = {"list-type": "2", "prefix": prefix}
            if token:
                params["continuation-token"] = token
            r = self._send("GET", "", params=params)
            root = ET.fromstring(r.text)
            for c in root.findall("{*}Contents"):   # {*}: whatever namespace the server declares
                out.append({"key": c.findtext("{*}Key"), "size": int(c.findtext("{*}Size") or 0),
                            "last_modified": c.findtext("{*}LastModified")})
            token = root.findtext("{*}NextContinuationToken") if (root.findtext("{*}IsTruncated") or "").lower() == "true" else None
            if not token:
                return out

    def delete(self, key: str) -> None:
        self._send("DELETE", key)
