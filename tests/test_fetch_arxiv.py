"""Offline unit tests for the fetch_arxiv.py pipeline, run against the frozen
RSS fixtures in tests/fixtures/ (4 categories, announcement day 2026-09-07).

Run: python -m unittest discover tests
"""

import unittest
from pathlib import Path

from fetch_arxiv import (
    build_day,
    filter_papers,
    merge_feeds,
    parse_feed,
    score_paper,
)

FIXTURES = Path(__file__).parent / "fixtures"
CATEGORIES = ["astro-ph.CO", "astro-ph.HE", "gr-qc", "hep-ph"]

# Measured once on the frozen fixtures; regression guards.
N_ENTRIES_PER_CAT = {"astro-ph.CO": 34, "astro-ph.HE": 24, "gr-qc": 40, "hep-ph": 48}
N_TOTAL_ENTRIES = 146
N_UNIQUE = 125          # after dedupe by arXiv id across the 4 feeds
N_NEW_CROSS = 78        # after dropping replace / replace-cross
N_AFTER_KEYWORDS = 21   # seed keyword subset below


SEED_KEYWORDS = [
    "gravitational lensing", "microlensing", "weak lensing",
    "gravitational waves", "dark matter", "cosmology",
    "supermassive black holes", "wave optics",
]


def load_parsed():
    feeds = []
    for cat in CATEGORIES:
        raw = (FIXTURES / f"rss_{cat}.xml").read_bytes()
        feeds.append(parse_feed(raw, cat))
    return feeds


class ParseFeed(unittest.TestCase):
    def test_pubdate_is_channel_date_not_today(self):
        for cat in CATEGORIES:
            raw = (FIXTURES / f"rss_{cat}.xml").read_bytes()
            pubdate, _ = parse_feed(raw, cat)
            self.assertEqual(pubdate, "2026-09-07")

    def test_entry_counts(self):
        for cat in CATEGORIES:
            raw = (FIXTURES / f"rss_{cat}.xml").read_bytes()
            _, items = parse_feed(raw, cat)
            self.assertEqual(len(items), N_ENTRIES_PER_CAT[cat], cat)

    def test_fields_present(self):
        _, items = parse_feed((FIXTURES / "rss_gr-qc.xml").read_bytes(), "gr-qc")
        it = items[0]
        for key in ("id", "title", "abstract", "authors", "surnames",
                    "author_keys", "categories", "primary_category",
                    "announce_type", "link", "pdf"):
            self.assertIn(key, it)
        self.assertTrue(all(len(k) == 2 for k in it["author_keys"]))
        self.assertRegex(it["id"], r"^\d{4}\.\d{4,5}$")
        self.assertNotIn("Announce Type", it["abstract"])
        self.assertTrue(it["pdf"].endswith(it["id"]))


class MergeFeeds(unittest.TestCase):
    def test_dedupe_and_type_filter(self):
        feeds = load_parsed()
        total = sum(len(items) for _, items in feeds)
        self.assertEqual(total, N_TOTAL_ENTRIES)

        _, all_types = merge_feeds(feeds, CATEGORIES,
                                   ["new", "cross", "replace", "replace-cross"])
        self.assertEqual(len(all_types), N_UNIQUE)

        pubdate, new_cross = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        self.assertEqual(pubdate, "2026-09-07")
        self.assertEqual(len(new_cross), N_NEW_CROSS)
        self.assertTrue(all(p["announce_type"] in ("new", "cross") for p in new_cross))

    def test_replace_item_excluded(self):
        feeds = load_parsed()
        _, new_cross = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        ids = {p["id"] for p in new_cross}
        self.assertNotIn("2507.08687", ids)  # a 'replace' in the CO fixture

    def test_cross_listed_paper_unions_categories(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        paper = next(p for p in merged if p["id"] == "2609.04308")
        self.assertEqual(paper["categories"],
                         ["astro-ph.CO", "astro-ph.HE", "hep-ph"])
        self.assertEqual(paper["matched_categories"],
                         ["astro-ph.CO", "astro-ph.HE", "hep-ph"])
        self.assertEqual(paper["announce_type"], "new")


class FilterAndScore(unittest.TestCase):
    def test_keyword_filter_count(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        kept = filter_papers(merged, keywords=SEED_KEYWORDS,
                             exclude_keywords=[], author_surnames=[])
        self.assertEqual(len(kept), N_AFTER_KEYWORDS)
        for p in kept:
            self.assertTrue(p["matched_keywords"] or p["matched_authors"])

    def test_exclude_keyword_removes(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        base = filter_papers(merged, keywords=SEED_KEYWORDS,
                             exclude_keywords=[], author_surnames=[])
        excl = filter_papers(merged, keywords=SEED_KEYWORDS,
                             exclude_keywords=["dark matter"], author_surnames=[])
        self.assertLess(len(excl), len(base))
        self.assertFalse(any("dark matter" in p["matched_keywords"] for p in excl))

    def test_empty_filters_keep_all(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        kept = filter_papers(merged, keywords=[], exclude_keywords=[],
                             author_surnames=[])
        self.assertEqual(len(kept), len(merged))

    def test_mode_all_keeps_unmatched_but_still_tags(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        gated = filter_papers([dict(p) for p in merged], keywords=SEED_KEYWORDS,
                              exclude_keywords=[], author_surnames=[])
        allkept = filter_papers([dict(p) for p in merged], keywords=SEED_KEYWORDS,
                                exclude_keywords=[], author_surnames=[], mode="all")
        self.assertEqual(len(allkept), len(merged))       # nothing dropped
        self.assertGreater(len(allkept), len(gated))
        # match lists are still populated for scoring / the UI
        self.assertTrue(all("matched_keywords" in p and "matched_authors" in p
                            for p in allkept))
        self.assertTrue(any(p["matched_keywords"] for p in allkept))
        self.assertTrue(any(not p["matched_keywords"] and not p["matched_authors"]
                            for p in allkept))

    def test_mode_all_still_honours_excludes(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        allkept = filter_papers([dict(p) for p in merged], keywords=[],
                                exclude_keywords=["dark matter"],
                                author_surnames=[], mode="all")
        self.assertLess(len(allkept), len(merged))
        for p in allkept:
            self.assertNotIn("dark matter",
                             f"{p['title']} {p['abstract']}".lower())

    def test_author_surname_exact_not_substring(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        # 'Hu' should not pull in every paper with a 'Hubble' / 'Chung' author.
        kept = filter_papers(merged, keywords=[], exclude_keywords=[],
                             author_surnames=["Hu"])
        for p in kept:
            self.assertIn("hu", p["surnames"])
            self.assertIn("hu", p["matched_authors"])

    def test_first_initial_narrows_common_surname(self):
        feeds = load_parsed()
        _, merged = merge_feeds(feeds, CATEGORIES, ["new", "cross"])
        bare = filter_papers([dict(p) for p in merged], keywords=[],
                             exclude_keywords=[], author_surnames=["Yu"])
        # Fixture 'Yu' authors: Felix J. Yu, Hao Yu, Huai-Min Yu -> initials f,h,h
        w_yu = filter_papers([dict(p) for p in merged], keywords=[],
                             exclude_keywords=[], author_surnames=["W. Yu"])
        f_yu = filter_papers([dict(p) for p in merged], keywords=[],
                             exclude_keywords=[], author_surnames=["F. Yu"])
        self.assertGreater(len(bare), 0)
        self.assertEqual(len(w_yu), 0)
        self.assertEqual(len(f_yu), 1)

    def test_score_rewards_title_and_author_hits(self):
        scoring = {"title_weight": 3, "abstract_weight": 1, "author_bonus": 5}
        title_hit = {"title": "dark matter halos", "abstract": "x",
                     "matched_authors": []}
        abstract_hit = {"title": "halos", "abstract": "we discuss dark matter",
                        "matched_authors": []}
        author_hit = {"title": "halos", "abstract": "x", "matched_authors": ["carr"]}
        kw = ["dark matter"]
        self.assertGreater(score_paper(title_hit, keywords=kw, scoring=scoring),
                           score_paper(abstract_hit, keywords=kw, scoring=scoring))
        self.assertGreater(score_paper(author_hit, keywords=kw, scoring=scoring),
                           score_paper(title_hit, keywords=kw, scoring=scoring))


class BuildDay(unittest.TestCase):
    CONFIG = {
        "categories": CATEGORIES,
        "announce_types": ["new", "cross"],
        "keywords": SEED_KEYWORDS,
        "exclude_keywords": [],
        "authors": [],
        "scoring": {"title_weight": 3, "abstract_weight": 1, "author_bonus": 5},
        "site": {"max_papers_per_day": 100},
    }

    def test_end_to_end_shape(self):
        day = build_day(load_parsed(), self.CONFIG)
        self.assertEqual(day["pubdate"], "2026-09-07")
        self.assertEqual(day["schema_version"], 2)
        self.assertEqual(len(day["papers"]), N_AFTER_KEYWORDS)
        scores = [p["score"] for p in day["papers"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_max_papers_truncates(self):
        cfg = {**self.CONFIG, "keywords": [], "site": {"max_papers_per_day": 5}}
        day = build_day(load_parsed(), cfg)
        self.assertEqual(len(day["papers"]), 5)

    def test_zero_match_day_is_valid(self):
        cfg = {**self.CONFIG, "keywords": ["zzz-nonexistent-term-zzz"]}
        day = build_day(load_parsed(), cfg)
        self.assertEqual(day["papers"], [])
        self.assertEqual(day["pubdate"], "2026-09-07")


if __name__ == "__main__":
    unittest.main()
