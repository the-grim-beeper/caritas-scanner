"""The catalogue is the brief; the live file is what actually resolves. Only the
intersection is collected, and nothing catalogued disappears."""
import re
from pathlib import Path

import pytest
import yaml

from mhs import vocab
from mhs.sources import catalogue

FIX = Path(__file__).parent / "fixtures"
DATA = Path(__file__).resolve().parents[2] / "data"

_BASE = {"name": "x", "layer": "landkreis", "authority": "high", "scope": "landkreis"}


def _load_one(tmp_path, **entry):
    path = tmp_path / "one.yaml"
    path.write_text(yaml.safe_dump([{"slug": "x", **_BASE, **entry}]))
    return catalogue.load_catalogue(path)


def test_rss_source_without_live_result_is_not_collected():
    # Wrong: trust the yaml and collect every rss entry.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    live = catalogue.load_live(FIX / "sources_live_small.json")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, live)}
    assert rows["lk-miesbach-presse"].collect is True
    assert rows["merkur-miesbach"].collect is False
    assert "not verified" in rows["merkur-miesbach"].not_collected_reason


def test_newsletter_source_is_loaded_as_not_collected_with_reason():
    # Wrong: drop non-collected methods so Coverage cannot show them.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, {})}
    assert rows["caritas-muenchen-newsletter"].collect is False
    assert "newsletter" in rows["caritas-muenchen-newsletter"].not_collected_reason


def test_live_result_overrides_method_and_url_with_what_resolved():
    # Autodiscovery may turn a page monitor into a real feed; the live result wins.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    live = catalogue.load_live(FIX / "sources_live_small.json")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, live)}
    assert rows["waakirchen-sitzungen"].method == "rss"
    assert rows["waakirchen-sitzungen"].url == "https://www.waakirchen.de/sitzungen.rss"
    assert rows["waakirchen-sitzungen"].items_at_check == 8


def test_query_source_carries_its_query_through_the_merge():
    # Wrong: SourceRow without the query, so the collector has nothing to search for.
    entries = catalogue.load_catalogue(FIX / "sources_small.yaml")
    live = catalogue.load_live(FIX / "sources_live_small.json")
    rows = {r.slug: r for r in catalogue.merge_for_load(entries, live)}
    q = rows["q-waakirchen"]
    assert q.collect is True and q.method == "query"
    assert q.query == '"Waakirchen" (Gemeinderat OR Haushalt OR Pflege)'
    assert rows["lk-miesbach-presse"].query is None


def test_collected_methods_are_the_vocabulary_ones():
    assert catalogue.COLLECTED_METHODS == vocab.COLLECTED_METHODS


def test_unknown_layer_is_rejected(tmp_path):
    with pytest.raises(catalogue.CatalogueError):
        _load_one(tmp_path, layer="policy", method="rss", url="https://x.test/f")


def test_unknown_scope_is_rejected(tmp_path):
    with pytest.raises(catalogue.CatalogueError):
        _load_one(tmp_path, scope="region", method="rss", url="https://x.test/f")


def test_rss_or_page_entry_needs_a_url_or_a_homepage(tmp_path):
    with pytest.raises(catalogue.CatalogueError):
        _load_one(tmp_path, method="rss")
    assert _load_one(tmp_path, method="page", homepage="https://x.test/")[0].method == "page"


def test_query_entry_needs_a_query_but_no_url(tmp_path):
    # Wrong: the template's url-or-homepage rule applied to query sources.
    with pytest.raises(catalogue.CatalogueError):
        _load_one(tmp_path, method="query", url="https://news.google.com/rss")
    [entry] = _load_one(tmp_path, method="query", query='"Hausham" Pflege')
    assert entry.query == '"Hausham" Pflege' and entry.url is None


@pytest.mark.parametrize("method", ["diff", "pdf"])
def test_diff_and_pdf_entries_need_a_url_not_just_a_homepage(tmp_path, method):
    with pytest.raises(catalogue.CatalogueError):
        _load_one(tmp_path, method=method, homepage="https://x.test/")
    assert _load_one(tmp_path, method=method, url="https://x.test/amtsblatt")[0].method == method


_OLD_LAYERS = re.compile(r"^\s*-?\s*layer:\s*(policy|editorial|innovation|corporate|infrastructure|funding)\b", re.M)


def test_real_catalogue_loads_and_covers_all_nine_layers():
    text = (DATA / "sources.yaml").read_text()
    if _OLD_LAYERS.search(text):
        pytest.skip("data/sources.yaml is being rebuilt")
    entries = catalogue.load_catalogue(DATA / "sources.yaml")
    if not entries:
        pytest.skip("data/sources.yaml is the empty placeholder while the catalogue is rebuilt")
    assert len(entries) >= 38  # the report's v1 core alone
    assert {e.layer for e in entries} == set(vocab.LAYERS)
    assert len({e.slug for e in entries}) == len(entries)


def test_real_entity_dictionary_has_the_reports_places_and_kinds():
    from mhs.entities import load_seed
    seeds = {s.slug: s for s in load_seed(DATA / "entities.yaml")}
    municipalities = ["bad-wiessee", "bayrischzell", "fischbachau", "gmund", "hausham", "holzkirchen",
                      "irschenberg", "kreuth", "miesbach", "otterfing", "rottach-egern", "schliersee",
                      "tegernsee", "valley", "waakirchen", "warngau", "weyarn"]
    assert all(seeds[m].kind == "place" for m in municipalities)
    assert seeds["landkreis-miesbach"].kind == "place" and "Kreis Miesbach" in seeds["landkreis-miesbach"].aliases
    assert seeds["sozialbeirat"].kind == "forum" and seeds["sozialbeirat"].actor_kind == "forum"
    assert seeds["sozialraumlotsen"].kind == "programme" and "Sozialraumlotsen" in seeds["sozialraumlotsen"].aliases
    assert seeds["buergermeister-waakirchen"].kind == "office" and seeds["buergermeister-waakirchen"].actor_kind is None
    assert {s.kind for s in seeds.values()} == set(vocab.ENTITY_KINDS)
