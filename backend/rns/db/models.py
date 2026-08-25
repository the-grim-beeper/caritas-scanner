"""ORM — the Source → FeedItem → Signal → Story spine, plus entities, events,
digests, cycles and the materialised trend cells (spec §5)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
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
    method: Mapped[str] = mapped_column(String(16))  # rss | page | newsletter | api | social
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    homepage: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="thematic")  # core | thematic
    cadence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    item_selector: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Only live-verified rss/page sources are collected. Everything else stays
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
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL", use_alter=True), nullable=True
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
    economic_materiality: Mapped[float] = mapped_column(Float, default=0.0)
    forward_lag: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    nearest_distance: Mapped[float | None] = mapped_column(Float, nullable=True)

    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    published_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    story: Mapped["Story | None"] = relationship(back_populates="signals", foreign_keys=[story_id])
    topics: Mapped[list["SignalTopic"]] = relationship(cascade="all, delete-orphan")
    entity_links: Mapped[list["SignalEntity"]] = relationship(cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # place | organisation | project | fund
    name: Mapped[str] = mapped_column(String(300))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)


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
    """An event or a deadline. The two dates are separate on purpose: a call's
    deadline usually matters more than the conference it belongs to."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(400))
    organizer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registration_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    funding_program: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(300), nullable=True)


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
    digest_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Digest(Base):
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


class TrendCell(Base):
    __tablename__ = "trend_cells"
    __table_args__ = (UniqueConstraint("week", "topic", "layer", name="uq_trend_cell"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    week: Mapped[date] = mapped_column(Date, index=True)  # ISO week Monday
    topic: Mapped[str] = mapped_column(String(40))
    layer: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer, default=0)
