"""News monitor: date parsing, feed parsing, tagging, deduplication, queue rules."""
import pytest

from src.news import (CONCEPTS, Tagger, detect_entities, dedupe, news_candidates,
                      normalise_date, parse_feed)
from src.entities import alias_map
from src.util import load_config


@pytest.mark.parametrize("raw,want", [
    # AMD's investor feed uses a two-digit year. Missing this dated every AMD
    # item as today, which put months-old releases at the top of the timeline.
    ("Mon, 28 Sep 26 16:05:00 -0400", "2026-09-28"),
    ("Mon, 05 Oct 2026 13:00:57 GMT", "2026-10-05"),
    ("Tue, 22 Jul 2026 09:00:00 +0000", "2026-07-22"),
    ("2026-03-16T08:00:00Z", "2026-03-16"),
    ("2026-07-22", "2026-07-22"),
    ("20261005T120000Z", "2026-10-05"),
    ("16 March 2026", "2026-03-16"),
])
def test_known_feed_date_shapes_parse(raw, want):
    assert normalise_date(raw) == want


@pytest.mark.parametrize("raw", ["", "   ", "not a date", None])
def test_unparseable_dates_return_empty_not_today(raw):
    """Must be empty, so the caller knows to fall back rather than trusting it."""
    assert normalise_date(raw) == ""


def test_rss_and_atom_both_parse():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Co A invests $5 billion in Co B</title>
        <link>https://example.test/a</link>
        <pubDate>Mon, 28 Sep 26 16:05:00 -0400</pubDate>
        <description>&lt;p&gt;Body text&lt;/p&gt;</description></item>
    </channel></rss>"""
    out = parse_feed(rss, "Test", "ir_rss")
    assert len(out) == 1
    assert out[0]["title"] == "Co A invests $5 billion in Co B"
    assert out[0]["url"] == "https://example.test/a"
    assert "<p>" not in out[0]["snippet"]

    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>8-K filed</title>
        <link href="https://example.test/b" rel="alternate"/>
        <updated>2026-09-03T08:03:56-04:00</updated>
        <summary>Filed 2026-09-03</summary></entry></feed>"""
    out = parse_feed(atom, "SEC", "edgar_8k")
    assert len(out) == 1, "Atom titles need the namespace map; without it this is zero"
    assert out[0]["title"] == "8-K filed"
    assert out[0]["url"] == "https://example.test/b"


def test_only_a_short_snippet_is_kept():
    body = "x" * 5000
    rss = (b"""<?xml version="1.0"?><rss version="2.0"><channel><item>
      <title>t</title><link>https://example.test/c</link>
      <description>""" + body.encode() + b"""</description></item></channel></rss>""")
    out = parse_feed(rss, "Test", "ir_rss")
    assert len(out[0]["snippet"]) <= 280, "article bodies must never be stored"


def test_entity_detection_uses_the_alias_table():
    amap = alias_map()
    found = detect_entities("NVIDIA Corporation and OpenAI Global announced", amap)
    assert "Nvidia" in found and "OpenAI" in found
    assert "Advanced Micro Devices" not in found


def test_tagger_scores_financing_text_above_unrelated_text():
    t = Tagger(load_config())
    scores = t.similarity([
        "Company A commits to invest up to $5 billion in Company B",
        "Company A appoints a new corporate fellow",
    ])
    assert scores[0] > scores[1]


def test_keyword_rules_fire_on_financing_language():
    t = Tagger(load_config())
    assert "investment" in t.keyword_tags("the firm will invest $2 billion")
    assert "warrant" in t.keyword_tags("issued warrants to purchase shares")
    assert "loan_guarantee" in t.keyword_tags("agreed to guarantee the lease obligations")
    assert t.keyword_tags("a new corporate fellow was appointed") == []


def test_near_identical_headlines_collapse_to_one_cluster():
    items = [
        {"title": "AMD and Anthropic announce strategic partnership", "source_kind": "gdelt"},
        {"title": "AMD and Anthropic Announce Strategic Partnership!", "source_kind": "ir_rss"},
        {"title": "Oracle reports fourth quarter results", "source_kind": "gdelt"},
    ]
    out = dedupe([dict(i) for i in items], 0.90)
    assert len(out) == 2
    kept = [o for o in out if "AMD" in o["title"]][0]
    assert kept["source_kind"] == "ir_rss", "a company release outranks a media aggregate"


def test_queue_entries_are_unverified_and_carry_no_amount():
    items = [{
        "financing_relevant": True, "entities": "AMD;Anthropic",
        "date": "2026-07-22", "url": "https://example.test/x",
        "title": "AMD commits up to $5 billion", "snippet": "",
        "publisher": "AMD IR", "source_kind": "ir_rss", "tags": "investment",
    }]
    cands = news_candidates(items)
    assert len(cands) == 1
    c = cands[0]
    assert c["review_status"] == "pending"
    assert c["quote_snippet"] == "", "a queue entry never carries a quote until review"
    assert c["amount_usd_low"] == "" and c["amount_usd_high"] == ""
    assert c["status"] == "reported"
    assert "UNVERIFIED" in c["notes"]


def test_a_single_entity_item_never_becomes_a_candidate_edge():
    items = [{"financing_relevant": True, "entities": "AMD", "date": "2026-07-22",
              "url": "https://example.test/y", "title": "t", "snippet": "",
              "publisher": "p", "source_kind": "ir_rss", "tags": "investment"}]
    assert news_candidates(items) == [], "an edge needs two parties"


def test_media_items_get_the_t3_tier_and_releases_get_t2():
    base = {"financing_relevant": True, "entities": "AMD;Anthropic",
            "date": "2026-07-22", "url": "https://example.test/z", "title": "t",
            "snippet": "", "publisher": "p", "tags": "investment"}
    assert news_candidates([{**base, "source_kind": "gdelt"}])[0]["evidence_tier"] == "T3"
    assert news_candidates([{**base, "source_kind": "ir_rss"}])[0]["evidence_tier"] == "T2"
    assert news_candidates([{**base, "source_kind": "edgar_8k"}])[0]["evidence_tier"] == "T1"


def _tag(items):
    """Run the relevance gate the way src.news.run does, without any network."""
    from src.news import NOISE, SIZE_HINT
    t = Tagger(load_config())
    amap = alias_map()
    out = []
    scores = t.similarity([f"{i['title']} {i.get('snippet','')}" for i in items])
    for i, sc in zip(items, scores):
        blob = f"{i['title']} {i.get('snippet','')}"
        kw = bool(t.keyword_tags(blob))
        sem = float(sc) >= t.threshold
        n_ent = len(detect_entities(blob, amap))
        sized = bool(SIZE_HINT.search(blob))
        noisy = bool(NOISE.search(blob))
        if i["source_kind"] == "edgar_8k":
            rel = bool(str(i.get("financing_item", "")).lower() == "true" or kw or sem)
        elif i["source_kind"] == "ir_rss":
            rel = bool((kw or sem) and (n_ent >= 2 or sized) and not noisy)
        else:
            rel = bool(kw and (sem or n_ent >= 2) and not noisy)
        out.append(rel)
    return out


def test_corporate_citizenship_copy_is_not_flagged():
    """These all fire the investment keyword and none of them is an edge."""
    noise = [
        {"title": "5 ways Amazon is investing in Connecticut", "source_kind": "ir_rss"},
        {"title": "Amazon in the community: what is happening in Seattle", "source_kind": "ir_rss"},
        {"title": "AMD Appoints Tim Ryan to Board of Directors", "source_kind": "ir_rss"},
        {"title": "How Cooley is accelerating IPO work with ChatGPT", "source_kind": "ir_rss"},
    ]
    assert not any(_tag(noise))


def test_a_real_financing_release_is_still_flagged():
    real = [{"title": "AMD and Anthropic Announce Strategic Partnership to Deploy Up to "
                      "2 Gigawatts of AMD Instinct MI450 Series GPUs",
             "snippet": "AMD has committed to make a strategic equity investment of up "
                        "to $5 billion in Anthropic.",
             "source_kind": "ir_rss"}]
    assert all(_tag(real))


def test_a_financing_item_8k_is_flagged_whatever_the_headline_says():
    item = [{"title": "Oracle files 8-K", "snippet": "", "source_kind": "edgar_8k",
             "financing_item": "true"}]
    assert all(_tag(item))
