"""The nightly off-site backup (backup.py) and the SigV4 client it uploads with (s3put.py), plan C-R1.3."""
import gzip
import hashlib
import sqlite3
from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app import backup, s3put, settings
from app.models import SourceRun, User
from app.s3put import EMPTY_SHA256, S3, canonical_request, sign

from .conftest import login

# The worked examples in the AWS reference (Authenticating Requests: Using Query Parameters / headers,
# "Examples: Signature Calculations in AWS Signature Version 4"), with the published example credentials.
KEY_ID, SECRET = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
WHEN = datetime(2013, 5, 24, tzinfo=timezone.utc)


def test_sigv4_get_object_matches_the_aws_example():
    hdrs = sign("GET", "https://examplebucket.s3.amazonaws.com/test.txt", {"Range": "bytes=0-9"}, EMPTY_SHA256,
                KEY_ID, SECRET, "us-east-1", now=WHEN)
    assert hdrs["Authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    assert hdrs["x-amz-date"] == "20130524T000000Z" and hdrs["host"] == "examplebucket.s3.amazonaws.com"


def test_sigv4_put_object_matches_the_aws_example():
    body = b"Welcome to Amazon S3."
    hdrs = sign("PUT", "https://examplebucket.s3.amazonaws.com/test$file.text",
                {"Date": "Fri, 24 May 2013 00:00:00 GMT", "x-amz-storage-class": "REDUCED_REDUNDANCY"},
                hashlib.sha256(body).hexdigest(), KEY_ID, SECRET, "us-east-1", now=WHEN)
    assert hdrs["Authorization"].endswith("Signature=98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd")
    assert "SignedHeaders=date;host;x-amz-content-sha256;x-amz-date;x-amz-storage-class," in hdrs["Authorization"]


def test_canonical_query_is_sorted_and_encoded_once():
    canon, signed = canonical_request("GET", "/", {"prefix": "J", "max-keys": 2},
                                      {"host": "b.example", "x-amz-date": "20130524T000000Z", "x-amz-content-sha256": EMPTY_SHA256},
                                      EMPTY_SHA256)
    assert canon.splitlines()[:3] == ["GET", "/", "max-keys=2&prefix=J"] and signed == "host;x-amz-content-sha256;x-amz-date"
    canon, _ = canonical_request("GET", "/my-bucket", {"list-type": "2", "prefix": "backups/"}, {"host": "h"}, EMPTY_SHA256)
    assert canon.splitlines()[2] == "list-type=2&prefix=backups%2F"
    canon, _ = canonical_request("PUT", "/my-bucket/backups/desert_watch_2026-10-18.db.gz", None, {"host": "h"}, EMPTY_SHA256)
    assert canon.splitlines()[1] == "/my-bucket/backups/desert_watch_2026-10-18.db.gz"


LISTING = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>dw</Name><Prefix>backups/</Prefix>
<IsTruncated>false</IsTruncated>
<Contents><Key>backups/desert_watch_2026-10-17.db.gz</Key><LastModified>2026-10-17T01:16:00.000Z</LastModified><Size>41000000</Size></Contents>
<Contents><Key>backups/desert_watch_2026-10-18.db.gz</Key><LastModified>2026-10-18T01:16:00.000Z</LastModified><Size>41500000</Size></Contents>
</ListBucketResult>"""


def test_client_puts_a_stream_with_content_length_lists_and_deletes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), dict(request.headers), request.read()))
        if request.method == "GET":
            return httpx.Response(200, text=LISTING)
        return httpx.Response(204 if request.method == "DELETE" else 200)

    s3 = S3("https://fly.storage.tigris.dev", "dw-backups", KEY_ID, SECRET, "auto",
            client=httpx.Client(transport=httpx.MockTransport(handler)))
    payload = b"x" * 3000 + b"y" * 1234
    s3.put("backups/desert_watch_2026-10-18.db.gz", iter([payload[:3000], payload[3000:]]), len(payload),
           hashlib.sha256(payload).hexdigest(), content_type="application/gzip")
    method, url, hdrs, body = seen[0]
    assert (method, url) == ("PUT", "https://fly.storage.tigris.dev/dw-backups/backups/desert_watch_2026-10-18.db.gz")
    assert body == payload and hdrs["content-length"] == str(len(payload)) and "transfer-encoding" not in hdrs
    assert hdrs["x-amz-content-sha256"] == hashlib.sha256(payload).hexdigest()
    assert hdrs["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/") and "/auto/s3/aws4_request" in hdrs["authorization"]
    assert [o["key"] for o in s3.list("backups/")] == ["backups/desert_watch_2026-10-17.db.gz", "backups/desert_watch_2026-10-18.db.gz"]
    assert seen[1][0] == "GET" and "list-type=2" in seen[1][1] and "prefix=backups" in seen[1][1]
    s3.delete("backups/desert_watch_2026-10-17.db.gz")
    assert seen[2][:2] == ("DELETE", "https://fly.storage.tigris.dev/dw-backups/backups/desert_watch_2026-10-17.db.gz")

    def refuse(request):
        # AWS's error body names the access key id and the request headers: only Code and Message may
        # reach source_run.error (the health strip shows it to every signed-in user)
        return httpx.Response(403, text="<Error><Code>AccessDenied</Code><Message>Access Denied</Message>"
                                        f"<AWSAccessKeyId>{KEY_ID}</AWSAccessKeyId></Error>")
    bad = S3("https://e", "b", KEY_ID, SECRET, client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(s3put.S3Error) as e:
        bad.delete("x")
    assert e.value.status == 403 and str(e.value) == "S3 answered 403: AccessDenied: Access Denied"
    assert KEY_ID not in str(e.value)
    # the signed path is encoded once: a key S3.url() already encoded is not encoded again
    seen.clear()
    s3.delete("backups/a b.gz")
    assert seen[0][1].endswith("/backups/a%20b.gz")
    canon, _ = s3put.canonical_request("DELETE", "/dw-backups/backups/a%20b.gz", None, {"host": "h"}, s3put.EMPTY_SHA256)
    assert canon.splitlines()[1] == "/dw-backups/backups/a%20b.gz"


def test_retention_keeps_7_daily_4_weekly_3_monthly():
    days = [date(2026, 10, 18) - __import__("datetime").timedelta(days=i) for i in range(100)]
    keep = backup.keep_dates(days)
    # the newest seven days
    assert all(date(2026, 10, 18 - i) in keep for i in range(7))
    # the newest copy of each of the four newest ISO weeks: 18 Oct is a Sunday (week 42), then 11, 4 Oct and 27 Sep
    assert {date(2026, 10, 18), date(2026, 10, 11), date(2026, 10, 4), date(2026, 9, 27)} <= keep
    assert date(2026, 9, 20) not in keep
    # the newest copy of each of the three newest months: 18 Oct, 30 Sep, 31 Aug (July is gone)
    assert {date(2026, 9, 30), date(2026, 8, 31)} <= keep and date(2026, 7, 31) not in keep
    assert len(keep) == 7 + 3 + 2   # 11 Oct, 4 Oct, 27 Sep from the weeks, 30 Sep and 31 Aug from the months
    # gaps: the newest copy in a week counts even when it is not the Sunday
    assert backup.keep_dates([date(2026, 10, 14), date(2026, 10, 6)], daily=1) == {date(2026, 10, 14), date(2026, 10, 6)}
    assert backup.keep_dates([]) == set()


class FakeS3:
    """A bucket in memory with the three calls backup.py makes."""

    def __init__(self, keys=()):
        self.objects = {k: b"" for k in keys}
        self.deleted = []

    def put(self, key, content, length, sha256_hex, content_type="application/octet-stream"):
        body = content if isinstance(content, bytes) else b"".join(content)
        assert len(body) == length and hashlib.sha256(body).hexdigest() == sha256_hex
        self.objects[key] = body

    def list(self, prefix=""):
        return [{"key": k, "size": len(v), "last_modified": None} for k, v in sorted(self.objects.items()) if k.startswith(prefix)]

    def delete(self, key):
        self.deleted.append(key)
        del self.objects[key]


def test_backup_uploads_a_checked_copy_then_prunes(db, users):
    old = [backup.key_for(date(2026, 10, 18) - __import__("datetime").timedelta(days=i)) for i in range(1, 40)]
    s3 = FakeS3(old + ["backups/keep-me.txt", "other/desert_watch_2020-01-01.db.gz"])
    res = backup.run(db, today=date(2026, 10, 18), s3=s3)
    key = backup.key_for(date(2026, 10, 18))
    assert key in s3.objects and res.rows == 1 and key in res.detail and "pruned" in res.detail
    # the upload is a gzip of a database that passes quick_check and holds the accounts
    raw = gzip.decompress(s3.objects[key])
    tmp = settings.DATA_DIR / "restored.db"
    tmp.write_bytes(raw)
    con = sqlite3.connect(str(tmp))
    try:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert con.execute('select count(*) from "user"').fetchone()[0] == len(db.scalars(select(User)).all()) == 2
    finally:
        con.close()
        tmp.unlink()
    # retention after the upload: 7 daily + weekly + monthly stay, the rest of the 39 old copies go,
    # and objects that are not dated backups are never touched
    kept = backup.keep_dates([date(2026, 10, 18)] + [backup.day_of(k) for k in old])
    assert {backup.day_of(k) for k in s3.objects if backup.day_of(k) and k.startswith("backups/")} == kept
    assert "backups/keep-me.txt" in s3.objects and "other/desert_watch_2020-01-01.db.gz" in s3.objects
    assert s3.deleted and all(k.startswith("backups/desert_watch_") for k in s3.deleted)
    assert f"{len(s3.deleted)} older copies pruned" in res.detail
    # the working copy on the volume is gone
    assert not list(settings.DATA_DIR.glob("backup-*"))


def test_backup_job_records_awaiting_key_until_the_bucket_exists(client, users, db, monkeypatch):
    from app import jobs
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3", "BUCKET_NAME"):
        monkeypatch.setattr(settings, k, None)
    assert jobs.backup() == "awaiting_key"
    run = db.scalar(select(SourceRun).where(SourceRun.source_key == "backup"))
    assert run.status == "awaiting_key" and "AWS_ACCESS_KEY_ID" in run.error and "BUCKET_NAME" in run.error
    login(client, "admin@example.org", "admin-password-1")
    line = next(h for h in client.get("/api/sources/health").json() if h["key"] == "backup")
    assert line["status"] == "awaiting_key" and line["stale"] is True
    ar = next(h for h in client.get("/api/sources/health", headers={"X-Lang": "ar"}).json() if h["key"] == "backup")
    assert "AWS_ACCESS_KEY_ID" in ar["error"] and "Set the bucket" not in ar["error"]
    assert "backup" in jobs.JOBS and client.post("/api/admin/run/backup").json() == {"queued": "backup"}


def test_backup_job_uploads_through_the_bucket_from_the_environment(db, monkeypatch):
    from app import jobs
    fake = FakeS3()
    monkeypatch.setattr(S3, "from_settings", classmethod(lambda cls: fake))
    assert jobs.backup() == "ok"
    run = db.scalar(select(SourceRun).where(SourceRun.source_key == "backup"))
    assert run.status == "ok" and len(fake.objects) == 1 and next(iter(fake.objects)).startswith("backups/desert_watch_")
    # a failed quick_check is an error run, not a silent upload
    monkeypatch.setattr(backup, "snapshot", lambda src, dest: (_ for _ in ()).throw(RuntimeError("quick_check on the copy said: bad")))
    assert jobs.backup() == "error"
    runs = db.scalars(select(SourceRun).where(SourceRun.source_key == "backup").order_by(SourceRun.id)).all()
    assert runs[-1].status == "error" and "quick_check" in runs[-1].error and len(fake.objects) == 1


def test_s3_from_settings_needs_all_four_names(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3", "BUCKET_NAME"):
        monkeypatch.setattr(settings, k, None)
    assert S3.from_settings() is None
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "tid_x")
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "tsec_y")
    monkeypatch.setattr(settings, "AWS_ENDPOINT_URL_S3", "https://fly.storage.tigris.dev/")
    assert S3.from_settings() is None
    monkeypatch.setattr(settings, "BUCKET_NAME", "dw-backups")
    s3 = S3.from_settings()
    assert s3.url("backups/a b.gz") == "https://fly.storage.tigris.dev/dw-backups/backups/a%20b.gz" and s3.region == "auto"
