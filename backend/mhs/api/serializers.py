"""Plain-dict serializers. One shape for a signal everywhere it appears."""
from __future__ import annotations

from mhs.db.models import Entity, Event, Signal, Source, Story


def factors(s: Signal) -> dict:
    return {
        "authority": s.authority,
        "regional_relevance": s.regional_relevance,
        "novelty": s.novelty,
        "consequence": s.consequence,
        "forward_lag": s.forward_lag,
    }


def story_brief(st: Story | None) -> dict | None:
    if st is None:
        return None
    return {
        "id": str(st.id),
        "corroboration_count": st.corroboration_count,
        "distinct_sources": st.distinct_sources,
        "confidence": st.confidence,
        "score": st.score,
        "first_seen": st.first_seen.isoformat() if st.first_seen else None,
        "last_seen": st.last_seen.isoformat() if st.last_seen else None,
    }


def signal_summary(s: Signal, src: Source | None = None, story: Story | None = None) -> dict:
    src = src or s.source
    story = story if story is not None else s.story
    return {
        "id": str(s.id),
        "headline_en": s.headline_en,
        "headline_de": s.headline_de,
        "summary_en": s.summary_en,
        "summary_de": s.summary_de,
        "signal_type": s.signal_type,
        "layer": src.layer if src else None,
        "source_name": src.name if src else None,
        "source_slug": src.slug if src else None,
        "authority_tier": src.authority if src else None,
        "url": s.feed_item.url if s.feed_item else None,
        "original_title": s.feed_item.title if s.feed_item else None,
        "published_at": s.published_at.isoformat() if s.published_at else None,
        "score": s.score,
        "is_founder": s.is_founder,
        "factors": factors(s),
        "topics": [t.topic_code for t in s.topics],
        "places": list(s.places_text or []),
        "story": story_brief(story),
    }


def signal_member(s: Signal) -> dict:
    return {
        "id": str(s.id),
        "headline_de": s.headline_de,
        "headline_en": s.headline_en,
        "source_name": s.source.name if s.source else None,
        "source_slug": s.source.slug if s.source else None,
        "layer": s.source.layer if s.source else None,
        "url": s.feed_item.url if s.feed_item else None,
        "published_at": s.published_at.isoformat() if s.published_at else None,
        "is_founder": s.is_founder,
        "nearest_distance": s.nearest_distance,
    }


def entity_brief(e: Entity) -> dict:
    return {
        "id": str(e.id), "slug": e.slug, "kind": e.kind, "name": e.name, "seeded": e.seeded,
        "actor_kind": e.actor_kind,
    }


def event_out(e: Event, signal: Signal | None = None) -> dict:
    out = {
        "id": str(e.id),
        "name": e.name,
        # Calendar fields (spec §4.5): seeded report entries have a slug and no signal.
        "name_en": e.name_en,
        "kind": e.kind,
        "origin": e.origin,
        "slug": e.slug,
        "place": e.place,
        "programme": e.programme,
        "note_de": e.note_de,
        "note_en": e.note_en,
        "brief_ref": e.brief_ref,
        "organizer": e.organizer,
        "location": e.location,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "deadline": e.deadline.isoformat() if e.deadline else None,
        "topic": e.topic,
        "registration_url": e.registration_url,
        "funding_program": e.funding_program,
        "target_audience": e.target_audience,
        "signal_id": str(e.signal_id) if e.signal_id else None,
    }
    if signal is not None:
        out["signal"] = {
            "id": str(signal.id),
            "headline_en": signal.headline_en,
            "headline_de": signal.headline_de,
            "layer": signal.source.layer if signal.source else None,
            "url": signal.feed_item.url if signal.feed_item else None,
        }
    return out


def source_out(s: Source, items_7d: int = 0, signals_7d: int = 0, items_30d: int = 0) -> dict:
    return {
        "id": str(s.id),
        "slug": s.slug,
        "name": s.name,
        "layer": s.layer,
        "authority": s.authority,
        "scope": s.scope,
        "places": list(s.places or []),
        "language": s.language,
        "method": s.method,
        "url": s.url,
        "homepage": s.homepage,
        "priority": s.priority,
        "cadence": s.cadence,
        "notes": s.notes,
        "brief_ref": s.brief_ref,
        "origin": s.origin,
        "items_30d": items_30d,
        "collect": s.collect,
        "not_collected_reason": s.not_collected_reason,
        "items_at_check": s.items_at_check,
        "status": s.status,
        "consecutive_failures": s.consecutive_failures,
        "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
        "last_ok_at": s.last_ok_at.isoformat() if s.last_ok_at else None,
        "last_error": s.last_error,
        "items_7d": items_7d,
        "signals_7d": signals_7d,
    }
