"""The catalogue is the brief; the live file is what actually resolves. Only the
intersection is collected, and nothing catalogued disappears."""
from pathlib import Path

import pytest
import yaml

from rns.sources import catalogue

FIX = Path(__file__).parent / "fixtures"
DATA = Path(__file__).resolve().parents[2] / "data"


def test_rss_source_without_live_result_is_not_collected():
    # Wrong: trust the yaml and collect every rss entry.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    live = catalogue.load_live(FIX / "sources_live_small.json")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, live)}
    assert rows["mannheim-presse"].collect is True
    assert rows["rnz-heidelberg"].collect is False
    assert "not verified" in rows["rnz-heidelberg"].not_collected_reason


def test_newsletter_source_is_loaded_as_not_collected_with_reason():
    # Wrong: drop non-rss/page sources so Coverage cannot show them.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, {})}
    assert rows["biorn-newsletter"].collect is False
    assert "newsletter" in rows["biorn-newsletter"].not_collected_reason


def test_live_result_overrides_method_and_url_with_what_resolved():
    # Autodiscovery may turn a page monitor into a real feed; the live result wins.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    live = catalogue.load_live(FIX / "sources_live_small.json")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, live)}
    assert rows["rnk-presse"].method == "rss"
    assert rows["rnk-presse"].url == "https://www.rhein-neckar-kreis.de/rss.xml"
    assert rows["rnk-presse"].items_at_check == 8


def test_unknown_layer_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump([{"slug": "x", "name": "x", "layer": "media", "authority": "high",
                                    "scope": "city", "method": "rss", "url": "https://x.test/f"}]))
    with pytest.raises(catalogue.CatalogueError):
        catalogue.load_catalogue(bad)


def test_rss_or_page_entry_needs_a_url_or_a_homepage(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump([{"slug": "x", "name": "x", "layer": "policy", "authority": "high",
                                    "scope": "city", "method": "rss"}]))
    with pytest.raises(catalogue.CatalogueError):
        catalogue.load_catalogue(bad)


def test_real_catalogue_loads_and_covers_all_six_layers():
    entries = catalogue.load_catalogue(DATA / "sources.yaml")
    assert len(entries) >= 70
    assert {e.layer for e in entries} == {"policy", "editorial", "innovation", "corporate", "infrastructure", "funding"}
    assert len({e.slug for e in entries}) == len(entries)


def test_real_entity_dictionary_has_the_reports_places_and_projects():
    from rns.entities import load_seed
    seeds = {s.slug: s for s in load_seed(DATA / "entities.yaml")}
    assert seeds["patrick-henry-village"].kind == "project" and "PHV" in seeds["patrick-henry-village"].aliases
    assert seeds["kurt-schumacher-bruecke"].kind == "project"
    assert seeds["mannheim"].kind == "place" and seeds["bergstrasse"].kind == "place"
