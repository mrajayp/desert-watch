from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- geography / themes
class Country(Base):
    __tablename__ = "country"
    id: Mapped[int] = mapped_column(primary_key=True)
    iso2: Mapped[str] = mapped_column(String(2), unique=True)
    name_en: Mapped[str] = mapped_column(String(100))
    name_ar: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class Region(Base):
    __tablename__ = "region"
    __table_args__ = (UniqueConstraint("country_id", "slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"))
    slug: Mapped[str] = mapped_column(String(60))
    level: Mapped[str] = mapped_column(String(10))  # national | macro | district
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("region.id"))
    name_en: Mapped[str] = mapped_column(String(100))
    name_ar: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class PlaceAlias(Base):
    __tablename__ = "place_alias"
    __table_args__ = (UniqueConstraint("region_id", "norm"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"))
    alias: Mapped[str] = mapped_column(String(120))
    norm: Mapped[str] = mapped_column(String(120), index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    proposed_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    # also a common word once the article is stripped (الخمس -> خمس) or a place elsewhere (Tripoli, Lebanon):
    # tags only beside the country name or an unambiguous alias (config `ambiguous_aliases`, classify.PlaceRule)
    ambiguous: Mapped[bool | None] = mapped_column(Boolean, default=False)


class Theme(Base):
    __tablename__ = "theme"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    group: Mapped[str | None] = mapped_column(String(40))  # e.g. "gender": sub-themes filtered together
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    en_terms: Mapped[list] = mapped_column(JSON, default=list)
    ar_terms: Mapped[list] = mapped_column(JSON, default=list)
    exclude: Mapped[list] = mapped_column(JSON, default=list)
    # co-occurrence rules: a list of term-groups; matches when EVERY group has a hit
    # (e.g. [[women words], [violence words]]). Lets "women + killed" match without bare "women".
    cooc: Mapped[list | None] = mapped_column(JSON, default=list)
    # strict: search-query results count for this theme only when the rules confirm them
    strict: Mapped[bool | None] = mapped_column(Boolean, default=False)
    # require_country: count only items whose own text names the country or one of its places
    # (even from local outlets, which also publish world news on the topic)
    require_country: Mapped[bool | None] = mapped_column(Boolean, default=False)
    # veto: [{"terms": [weak terms], "context": [words]}]: the weak terms do not count when a context word is present
    # ("killed" next to "crash"). mask: phrases blanked out before matching ("territorial waters" for "water").
    veto: Mapped[list | None] = mapped_column(JSON, default=list)
    mask: Mapped[list | None] = mapped_column(JSON, default=list)
    acled_event_types: Mapped[list] = mapped_column(JSON, default=list)
    reliefweb_themes: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- outlets
class Outlet(Base):
    __tablename__ = "outlet"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("country.id"))
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(200), unique=True)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    rss_url: Mapped[str | None] = mapped_column(String(500))
    base_city: Mapped[str | None] = mapped_column(String(100))
    base_country: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    created_via: Mapped[str] = mapped_column(String(10), default="seed")  # seed | auto | user | import
    # False = known outlet we only see in part (Facebook register pages: the posts Google News indexes)
    monitored: Mapped[bool | None] = mapped_column(Boolean, default=True)
    # metrics from external datasets, keyed by source, e.g. {"social_media_scrape": {...}}
    external: Mapped[dict | None] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutletCategory(Base):
    """One dated, evidenced category assignment. History is kept: an assignment is
    closed (valid_to) rather than overwritten."""
    __tablename__ = "outlet_category"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(60))
    confidence: Mapped[str] = mapped_column(String(12))  # reported | likely | disputed | unverified
    evidence_url: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | proposed | rejected
    set_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    valid_from: Mapped[date] = mapped_column(Date, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- collection
class SourceRun(Base):
    __tablename__ = "source_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|ok|error|awaiting_key|partial
    rows: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class Item(Base):
    """Anything collected: an article (coverage) or a need unit (event, report, pageview day)."""
    __tablename__ = "item"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), index=True)  # article | event | report | pageview | suggestion
    source_key: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(600), unique=True)
    url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(String(8))
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlet.id"), index=True)
    value: Mapped[float] = mapped_column(Float, default=1.0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    relevant: Mapped[bool] = mapped_column(Boolean, default=True)  # users can mark an item irrelevant
    # another copy of the same story from the same outlet (e.g. Google News link + the outlet's own URL):
    # kept for reference, never counted. Points at the copy that is counted.
    duplicate_of: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ItemTheme(Base):
    __tablename__ = "item_theme"
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"), primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"), primary_key=True)
    method: Mapped[str] = mapped_column(String(8), default="rule")  # rule | query | user | model
    active: Mapped[bool] = mapped_column(Boolean, default=True)    # False = a user said "not about this"
    theme_version: Mapped[int] = mapped_column(Integer, default=1)
    # why the link exists: {"field": "title"|"snippet"|"query", "terms": [...], "query": "<alert or query key>"}
    evidence: Mapped[dict | None] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Float)          # learned model probability, when scored
    model_version: Mapped[str | None] = mapped_column(String(40))


class ItemRegion(Base):
    __tablename__ = "item_region"
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"), primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"), primary_key=True)
    method: Mapped[str] = mapped_column(String(8), default="rule")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertFeed(Base):
    """A Google Alert delivered as RSS. The alert itself is created by a person in a Google
    account (no API); the app generates the query list and polls the feed URL pasted back."""
    __tablename__ = "alert_feed"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"))
    key: Mapped[str] = mapped_column(String(80), unique=True)  # e.g. district:sabha:ar
    label: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(4))
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("theme.id"))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("region.id"))
    feed_url: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_items: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class CoverageSeries(Base):
    """GDELT timelinevolraw counts: long-history national coverage trend per theme."""
    __tablename__ = "coverage_series"
    __table_args__ = (UniqueConstraint("theme_id", "day", "series"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    series: Mapped[str] = mapped_column(String(20))  # all | sourcecountry
    day: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)


class CellWeek(Base):
    __tablename__ = "cell_week"
    __table_args__ = (UniqueConstraint("theme_id", "region_id", "week_start", "lens"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), index=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"))
    week_start: Mapped[date] = mapped_column(Date, index=True)
    lens: Mapped[str] = mapped_column(String(14))
    need: Mapped[float] = mapped_column(Float, default=0)
    coverage: Mapped[float] = mapped_column(Float, default=0)
    ratio: Mapped[float | None] = mapped_column(Float)
    ref_ratio: Mapped[float | None] = mapped_column(Float)
    gap: Mapped[float | None] = mapped_column(Float)
    insufficient: Mapped[bool] = mapped_column(Boolean, default=True)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- users
class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    pw_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(12), default="journalist")  # admin | journalist | viewer
    # pending (self-signup awaiting approval) | active | rejected | disabled
    status: Mapped[str | None] = mapped_column(String(10), default="active")
    organisation: Mapped[str | None] = mapped_column(String(200))
    signup_note: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[int | None] = mapped_column(Integer)
    pseudo_id: Mapped[str] = mapped_column(String(32), unique=True)
    tracking_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    tracking_notice_ack_at: Mapped[datetime | None] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invite(Base):
    __tablename__ = "invite"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(12), default="journalist")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuthSession(Base):
    __tablename__ = "auth_session"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


# ---------------------------------------------------------------- feedback
class GapVote(Base):
    __tablename__ = "gap_vote"
    __table_args__ = (UniqueConstraint("user_id", "theme_id", "region_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"))
    week_start: Mapped[date] = mapped_column(Date)
    lens: Mapped[str] = mapped_column(String(14))
    vote: Mapped[str] = mapped_column(String(16))  # real | covered | not_newsworthy
    covered_item_id: Mapped[int | None] = mapped_column(ForeignKey("item.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GapClaim(Base):
    """'I'm working on this' / 'published'. Team-only."""
    __tablename__ = "gap_claim"
    __table_args__ = (UniqueConstraint("user_id", "theme_id", "region_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"))
    status: Mapped[str] = mapped_column(String(10))  # working | published | dropped
    published_url: Mapped[str | None] = mapped_column(String(1000))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Comment(Base):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    object_type: Mapped[str] = mapped_column(String(10))  # gap | item | theme | outlet
    object_key: Mapped[str] = mapped_column(String(60), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comment.id"))
    body: Mapped[str] = mapped_column(Text)
    tag: Mapped[str | None] = mapped_column(String(20))  # optional: agree | disagree | missing_context | source_tip
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ArticleAssessment(Base):
    __tablename__ = "article_assessment"
    __table_args__ = (UniqueConstraint("user_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"))
    accuracy: Mapped[int] = mapped_column(Integer)
    depth: Mapped[int] = mapped_column(Integer)
    local_sourcing: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Suggestion(Base):
    __tablename__ = "suggestion"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))  # gap | keyword | source | alias | outlet_category
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    origin: Mapped[str] = mapped_column(String(8), default="user")  # user | model
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- learning
class Event(Base):
    """Behaviour log. Pseudonymous; implicit events are dropped for opted-out users."""
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    pseudo_id: Mapped[str] = mapped_column(String(32), index=True)
    session_id: Mapped[str | None] = mapped_column(String(40))
    type: Mapped[str] = mapped_column(String(24))
    object_type: Mapped[str | None] = mapped_column(String(10))
    object_key: Mapped[str | None] = mapped_column(String(60))
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class Label(Base):
    __tablename__ = "label"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    label_type: Mapped[str] = mapped_column(String(20), index=True)  # theme_relevance | region | gap_real | article_quality | interest
    object_type: Mapped[str] = mapped_column(String(10))
    object_key: Mapped[str] = mapped_column(String(60))
    value: Mapped[dict] = mapped_column(JSON)
    pseudo_id: Mapped[str | None] = mapped_column(String(32))
    origin: Mapped[str] = mapped_column(String(8))  # explicit | implicit
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source_ref: Mapped[str] = mapped_column(String(60), unique=True)  # idempotency: table:id or event:id


# ---------------------------------------------------------------- page feedback
class Feedback(Base):
    """Suggestions, questions and bug reports left at the bottom of any page."""
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    page: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(12))  # suggestion | question | problem
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="new")  # new | answered | planned | done | closed
    reply: Mapped[str | None] = mapped_column(Text)
    replied_by: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- key events (timeline)
class KeyEvent(Base):
    """Dated reference events for the timeline: seeded from config (`events`) and added by users
    (each needs a source link)."""
    __tablename__ = "key_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(200))
    label_ar: Mapped[str | None] = mapped_column(String(300))   # config events carry an Arabic label
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("theme.id"))
    source_url: Mapped[str] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(8), default="config")  # config | user
    added_by: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- digest
class Digest(Base):
    """Weekly AI-written brief. The input facts are stored next to the text so every claim
    can be checked against the numbers the model was given."""
    __tablename__ = "digest"
    __table_args__ = (UniqueConstraint("country_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"))
    week_start: Mapped[date] = mapped_column(Date)
    model: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(12))  # ok | refused | error
    content_md: Mapped[str | None] = mapped_column(Text)
    content_md_ar: Mapped[str | None] = mapped_column(Text)   # the same brief in Arabic (from 2026-10-17)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- network
class NetworkEdgeWeek(Base):
    __tablename__ = "network_edge_week"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), index=True)
    kind: Mapped[str] = mapped_column(String(14))  # outlet_region | outlet_theme | outlet_outlet | syndication
    source_node: Mapped[str] = mapped_column(String(40))
    target_node: Mapped[str] = mapped_column(String(40))
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("theme.id"))
    week_start: Mapped[date | None] = mapped_column(Date, index=True)
    weight: Mapped[float] = mapped_column(Float)


class ModelRegistry(Base):
    """A trained theme classifier. One row per version; exactly one is active per kind.
    The bundle itself lives on the data volume (path), never in the database."""
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="theme")
    version: Mapped[str] = mapped_column(String(40), unique=True)
    path: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    trained_on: Mapped[dict] = mapped_column(JSON, default=dict)   # label counts, data window
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)      # per-theme precision/recall/F1 on the audit set
    thresholds: Mapped[dict] = mapped_column(JSON, default=dict)   # theme slug -> probability threshold
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)


class ItemEngagement(Base):
    """An engagement reading for one article from one source at one age (e.g. Facebook link
    engagement at 48 h and 7 days, Telegram views, story pickup)."""
    __tablename__ = "item_engagement"
    __table_args__ = (UniqueConstraint("item_id", "source", "age_bucket"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20))       # fb_url | telegram | pickup | youtube
    age_bucket: Mapped[str] = mapped_column(String(8))    # 48h | 7d | now
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Indicator(Base):
    """A daily number from outside the news, shown next to coverage and never scored: the dinar's
    exchange rates, or how often people in Libya looked up a page on Wikipedia. value is None when
    the day was checked and the source had nothing (a Wikipedia page below the privacy threshold)."""
    __tablename__ = "indicator"
    __table_args__ = (UniqueConstraint("country_id", "key", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), index=True)
    key: Mapped[str] = mapped_column(String(40), index=True)   # wiki_fx_platform | usd_lyd_parallel | usd_lyd_official
    day: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WikiReading(Base):
    """A Wikipedia page that people in the country read on a day, from Wikimedia's privacy-protected
    daily dataset (only pages above about 90 views from that country, with noise added). We keep only
    pages that name the country or one of its places, or that a theme or an indicator lists."""
    __tablename__ = "wiki_reading"
    __table_args__ = (UniqueConstraint("country_id", "day", "project", "page_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    project: Mapped[str] = mapped_column(String(40))
    page_id: Mapped[int] = mapped_column(Integer)
    page_title: Mapped[str] = mapped_column(String(300))
    qid: Mapped[str | None] = mapped_column(String(20))
    views: Mapped[int] = mapped_column(Integer)


# ---------------------------------------------------------------- AI answers audit (ai_audit/)
class AiRun(Base):
    """One assistant's weekly run of the AI answers audit (docs/research/ai_answers_audit_scope.md).
    One per (country, week_start, provider) unless an admin forces another. Never scored: the audit
    writes only ai_run, ai_answer and ai_source."""
    __tablename__ = "ai_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)     # anthropic | openai | ..., or an app key
    model: Mapped[str | None] = mapped_column(String(80))
    tool: Mapped[str | None] = mapped_column(String(60))
    week_start: Mapped[date] = mapped_column(Date, index=True)        # Monday, UTC
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    # running | ok | partial | error | awaiting_key | over_budget | disabled
    status: Mapped[str] = mapped_column(String(14), default="running")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)        # location_sent, max_searches, fly_region, date_line
    usage: Mapped[dict] = mapped_column(JSON, default=dict)           # input_tokens, output_tokens, searches
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    price_basis: Mapped[dict] = mapped_column(JSON, default=dict)     # as_of + the rates used
    error: Mapped[str | None] = mapped_column(Text)
    forced: Mapped[bool] = mapped_column(Boolean, default=False)
    # api: the automatic developer-API run. panel: answers journalists logged from the apps on their own phones.
    # browser: a supervised session an admin ran in a signed-in browser. The three are never counted together.
    # A panel or browser run is one row per (country, week, app, origin), made with the week's first entry
    # (api/ai_panel.py): provider is the app key, model is null and cost stays 0, so it never touches the cap.
    origin: Mapped[str] = mapped_column(String(10), default="api", server_default="api")


class AiAnswer(Base):
    """One question asked in one language in a run. The answer text is never stored: only its
    language and length, worked out in memory. The assistant's own queries are admin-only."""
    __tablename__ = "ai_answer"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ai_run.id", ondelete="CASCADE"), index=True)
    question_key: Mapped[str] = mapped_column(String(40))
    question_version: Mapped[str] = mapped_column(String(8))          # first 8 hex of sha1(en + ar)
    lang: Mapped[str] = mapped_column(String(2))                      # the language asked: ar | en
    # ok | no_search | refused | rate_limited | error | over_budget
    status: Mapped[str] = mapped_column(String(14))                   # panel and browser entries: ok | no_sources
    answer_lang: Mapped[str | None] = mapped_column(String(4))
    answer_chars: Mapped[int | None] = mapped_column(Integer)
    queries: Mapped[list] = mapped_column(JSON, default=list)         # admin-only
    n_searched: Mapped[int] = mapped_column(Integer, default=0)
    n_cited: Mapped[int] = mapped_column(Integer, default=0)
    searches: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    origin: Mapped[str] = mapped_column(String(10), default="api", server_default="api")   # api | panel | browser
    # panel and browser entries: who logged it (their right to delete it; never shown to anyone else, set to
    # NULL when the account is deleted) and where it was asked from: LY | other | London (a browser session)
    logged_by: Mapped[int | None] = mapped_column(Integer)
    asked_in: Mapped[str | None] = mapped_column(String(8))


class AiSource(Base):
    """A link an answer's search returned (searched) or the answer cited (cited), matched read-only
    to the outlet register (ai_audit/matcher.py). url and title are admin-only; an unlisted social
    account is kept as its platform only."""
    __tablename__ = "ai_source"
    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("ai_answer.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(8))                      # searched | cited
    rank: Mapped[int] = mapped_column(Integer, default=0)
    url: Mapped[str] = mapped_column(String(2000))                    # admin-only
    domain: Mapped[str] = mapped_column(String(200), index=True)
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlet.id", ondelete="SET NULL"), index=True)
    family_id: Mapped[int | None] = mapped_column(Integer)
    match: Mapped[str] = mapped_column(String(8))                     # path | exact | parent | social | unknown
    title: Mapped[str | None] = mapped_column(Text)                   # admin-only
    lang: Mapped[str] = mapped_column(String(4), default="und")       # ar | en | und
    date: Mapped[str | None] = mapped_column(String(40))
    citations: Mapped[int] = mapped_column(Integer, default=0)


class NodeMetric(Base):
    __tablename__ = "node_metric"
    __table_args__ = (UniqueConstraint("country_id", "node", "graph"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"))
    graph: Mapped[str] = mapped_column(String(14))
    node: Mapped[str] = mapped_column(String(40))
    degree: Mapped[float] = mapped_column(Float, default=0)
    strength: Mapped[float] = mapped_column(Float, default=0)
    community: Mapped[int | None] = mapped_column(Integer)
    centrality: Mapped[float] = mapped_column(Float, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
