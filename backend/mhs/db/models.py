"""ORM — the Source → FeedItem → Signal → Story spine, plus entities, events,
digests, cycles, the materialised trend cells, and the Miesbach additions
(spec §5): monitoring questions and their judgements, the evidence graph
(edges, relation candidates, forum profiles, gaps) and the seeded calendar."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    # Every datetime is an instant: feeds publish in their own zones and the app
    # runs in UTC on Railway. Mapping it once means no column can be created
    # naive by accident and then reject an aware value at insert time.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    layer: Mapped[str] = mapped_column(String(32), index=True)
    authority: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(16))
    places: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    language: Mapped[str] = mapped_column(String(8), default="de")
    method: Mapped[str] = mapped_column(String(16))  # vocab.METHODS
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # method=query: the search expression (Google News RSS); the URL is built at fetch time.
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    homepage: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="thematic")  # core | thematic
    cadence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    item_selector: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Only live-verified sources of a collected method are collected. Everything else stays
    # in the table so Coverage can say exactly what is not being watched, and why.
    collect: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    not_collected_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    items_at_check: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="active")  # active | quarantined
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_ok_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_page_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # method=diff: the normalised main text last seen, and its hash. First sight is a baseline.
    snapshot_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    feed_items: Mapped[list["FeedItem"]] = relationship(back_populates="source")


class FeedItem(Base):
    """One raw item as collected, before any interpretation."""

    __tablename__ = "feed_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_item_source_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    canonical_url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    # Normalised headline (casefolded, outlet stripped): a search-feed item whose key matches a
    # stored item is credited to it rather than stored again (Google redirect URLs never match).
    title_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    # "Headline - Outlet" from search feeds: the outlet, split off and kept.
    outlet: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The same URL arriving via a second feed is credited here, not duplicated.
    also_seen_in: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # "looked at, nothing here" is not "not looked at yet".
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    source: Mapped["Source"] = relationship(back_populates="feed_items")


class Story(Base):
    """One development, possibly reported by several outlets."""

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    founding_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL", use_alter=True, name="fk_story_founder"), nullable=True
    )
    corroboration_count: Mapped[int] = mapped_column(Integer, default=0)
    distinct_sources: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    first_seen: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)

    signals: Mapped[list["Signal"]] = relationship(
        back_populates="story", foreign_keys="Signal.story_id"
    )


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    feed_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feed_items.id", ondelete="SET NULL"), nullable=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_founder: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    headline_en: Mapped[str] = mapped_column(String(600))
    headline_de: Mapped[str] = mapped_column(String(600))
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_type: Mapped[str] = mapped_column(String(32), index=True)
    places_text: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # The five factors of the brief's score, all stored so the UI never has to
    # show a bare product.
    authority: Mapped[float] = mapped_column(Float, default=0.0)
    regional_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    novelty: Mapped[float] = mapped_column(Float, default=0.0)
    # Consequence for social provision and coordination in Landkreis Miesbach (spec §2.5).
    consequence: Mapped[float] = mapped_column(Float, default=0.0)
    forward_lag: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    nearest_distance: Mapped[float | None] = mapped_column(Float, nullable=True)

    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # The judge model that last read this signal against the questions (re-judged when it changes).
    judged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    judged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    published_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    story: Mapped["Story | None"] = relationship(back_populates="signals", foreign_keys=[story_id])
    source: Mapped["Source | None"] = relationship(foreign_keys=[source_id])
    feed_item: Mapped["FeedItem | None"] = relationship(foreign_keys=[feed_item_id])
    topics: Mapped[list["SignalTopic"]] = relationship(cascade="all, delete-orphan")
    entity_links: Mapped[list["SignalEntity"]] = relationship(cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="signal", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # vocab.ENTITY_KINDS
    name: Mapped[str] = mapped_column(String(300))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    # Where the entity sits in the network graph (vocab.ACTOR_KINDS); places and offices have none.
    actor_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)


class SignalEntity(Base):
    __tablename__ = "signal_entities"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="mentioned")

    entity: Mapped["Entity"] = relationship()


class SignalTopic(Base):
    __tablename__ = "signal_topics"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True
    )
    topic_code: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)


class Event(Base):
    """An event, a deadline or a watch window. The dates are separate on purpose: a
    call's deadline usually matters more than the conference it belongs to. Events
    come from extracted signals (origin "signal") or from the report's calendar
    (origin "report", no signal, keyed by slug)."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    slug: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    origin: Mapped[str] = mapped_column(String(8), default="signal")  # report | signal
    kind: Mapped[str] = mapped_column(String(10), default="event")  # vocab.EVENT_KINDS
    name: Mapped[str] = mapped_column(String(400))  # German (or as written in the source)
    name_en: Mapped[str | None] = mapped_column(String(400), nullable=True)
    place: Mapped[str | None] = mapped_column(String(160), nullable=True)  # entity slug
    programme: Mapped[str | None] = mapped_column(String(160), nullable=True)  # entity slug
    note_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registration_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    funding_program: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(300), nullable=True)

    signal: Mapped["Signal | None"] = relationship(back_populates="events")


class Cycle(Base):
    __tablename__ = "cycles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="mock")  # live | mock
    items_fetched: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    extracted: Mapped[int] = mapped_column(Integer, default=0)
    signals: Mapped[int] = mapped_column(Integer, default=0)
    stories_new: Mapped[int] = mapped_column(Integer, default=0)
    corroborations: Mapped[int] = mapped_column(Integer, default=0)
    failed_sources: Mapped[int] = mapped_column(Integer, default=0)
    judged: Mapped[int] = mapped_column(Integer, default=0)
    judgements: Mapped[int] = mapped_column(Integer, default=0)
    edges_new: Mapped[int] = mapped_column(Integer, default=0)
    digest_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Digest(Base):
    """The template's digest table, served as the weekly Lagebericht."""

    __tablename__ = "digests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="SET NULL"), nullable=True
    )
    lead_en: Mapped[str] = mapped_column(Text)
    lead_de: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    week: Mapped[date | None] = mapped_column(Date, nullable=True)  # ISO week Monday
    # The weekly written update to Caritas (the Freitagsnotiz).
    friday_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    friday_en: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrendCell(Base):
    __tablename__ = "trend_cells"
    __table_args__ = (UniqueConstraint("week", "topic", "layer", name="uq_trend_cell"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    week: Mapped[date] = mapped_column(Date, index=True)  # ISO week Monday
    topic: Mapped[str] = mapped_column(String(40))
    layer: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# The fifteen monitoring questions (spec §4.2)
# ---------------------------------------------------------------------------
class Question(Base):
    """One of the report's standing questions, loaded from data/questions.yaml. "for" is
    the report's "evidence for the concern or transition", "against" its "evidence
    against / stabilising"; each side carries its own label because which side is good
    news differs per question."""

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # q01 … q15
    sort: Mapped[int] = mapped_column(Integer)
    title_de: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(Text)
    driver_de: Mapped[str] = mapped_column(Text)
    driver_en: Mapped[str] = mapped_column(Text)
    sources_de: Mapped[str] = mapped_column(Text)
    for_label_de: Mapped[str] = mapped_column(String(120))
    for_label_en: Mapped[str] = mapped_column(String(120))
    for_de: Mapped[str] = mapped_column(Text)
    for_en: Mapped[str] = mapped_column(Text)
    against_label_de: Mapped[str] = mapped_column(String(120))
    against_label_en: Mapped[str] = mapped_column(String(120))
    against_de: Mapped[str] = mapped_column(Text)
    against_en: Mapped[str] = mapped_column(Text)


class Judgement(Base):
    """A signal read against one question by one judge model. The quote is a verbatim
    piece of the signal's text (checked before storing)."""

    __tablename__ = "judgements"
    __table_args__ = (UniqueConstraint("signal_id", "question_id", "model", name="uq_judgement"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(8), ForeignKey("questions.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # vocab.DIRECTIONS
    strength: Mapped[str] = mapped_column(String(10))  # vocab.STRENGTH_WEIGHTS
    weight: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    rationale_de: Mapped[str] = mapped_column(Text)
    rationale_en: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


# ---------------------------------------------------------------------------
# The evidence graph (spec §4.3)
# ---------------------------------------------------------------------------
class RelationCandidate(Base):
    """A relation the extractor read in a signal, as free text, before its two ends are
    resolved onto entities. Resolved candidates become edges; unresolved ones are dropped."""

    __tablename__ = "relation_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    a_text: Mapped[str] = mapped_column(String(300))
    b_text: Mapped[str] = mapped_column(String(300))
    relation: Mapped[str] = mapped_column(String(16))  # vocab.RELATIONS
    quote: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Edge(Base):
    """Reads "a <relation> b". From the report (origin "report") or from a signal (origin
    "signal"); an edge from a signal without its signal is refused by the database."""

    __tablename__ = "edges"
    __table_args__ = (
        CheckConstraint("origin <> 'signal' OR signal_id IS NOT NULL", name="ck_edge_signal_provenance"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    a_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    b_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(16))  # vocab.RELATIONS
    origin: Mapped[str] = mapped_column(String(8))  # report | signal
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    evidence_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(8), default="medium")  # high | medium | low
    brief_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ForumProfile(Base):
    """What the report knows about a standing coordination forum (one per forum entity)."""

    __tablename__ = "forum_profiles"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    convener_de: Mapped[str] = mapped_column(String(300))
    attendance_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    public_minutes: Mapped[bool] = mapped_column(Boolean, default=False)
    treatment_de: Mapped[str] = mapped_column(Text)
    treatment_en: Mapped[str] = mapped_column(Text)
    brief_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)


class NetworkGap(Base):
    """A known unknown of the graph: a missing edge, an unfound document, an interview question."""

    __tablename__ = "network_gaps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    sort: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))  # missing_edge | not_found | interview
    title_de: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(Text)
    detail_de: Mapped[str] = mapped_column(Text)
    detail_en: Mapped[str] = mapped_column(Text)
    actor_slugs: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
