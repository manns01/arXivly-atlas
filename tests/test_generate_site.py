"""Offline unit tests for generate_site.py — render synthetic raw days into a
temp docs/ and check structure, relative links, and the embedded atlas JSON.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from generate_site import (
    _json_for_script,
    _snippet,
    _subject_buckets,
    render_site,
)

CONFIG = {
    "categories": ["astro-ph.CO"],
    "keywords": ["dark matter", "cosmology"],
    "similarity": {},
    "atlas": {"window_days": 3},
    "site": {"title": "arXivly-atlas", "base_url": "/arXivly-atlas"},
}


def _raw_paper(pid, title, abstract):
    return {
        "id": pid, "title": title, "abstract": abstract,
        "authors": ["A. Author"], "surnames": ["author"],
        "author_keys": [["a", "author"]],
        "categories": ["astro-ph.CO"], "primary_category": "astro-ph.CO",
        "announce_type": "new", "link": f"https://arxiv.org/abs/{pid}",
        "pdf": f"https://arxiv.org/pdf/{pid}",
        "matched_keywords": ["dark matter"], "matched_authors": [],
        "score": 4,
    }


def _write_day(path, pubdate, papers):
    path.write_text(json.dumps({
        "schema_version": 2, "generated_at": "x", "pubdate": pubdate,
        "categories": [], "papers": papers,
    }))


class Helpers(unittest.TestCase):
    def test_snippet_truncates_on_word_boundary(self):
        s = _snippet("word " * 100, limit=20)
        self.assertTrue(s.endswith("…"))
        self.assertLessEqual(len(s), 21)

    def test_snippet_short_text_untouched(self):
        self.assertEqual(_snippet("short"), "short")

    def test_json_for_script_escapes_tag_breakers(self):
        out = _json_for_script({"t": "</script><b>&"})
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertNotIn("&", out)
        self.assertEqual(json.loads(out), {"t": "</script><b>&"})


class RenderSite(unittest.TestCase):
    def _build(self, tmp):
        raw = Path(tmp) / "raw"
        raw.mkdir()
        docs = Path(tmp) / "docs"
        _write_day(raw / "2026-09-04.json", "2026-09-04", [
            _raw_paper("1", "dark matter subhalo abundance",
                       "substructure lensing perturbations in cold dark matter cosmology"),
            _raw_paper("2", "dark matter subhalo abundance",
                       "substructure lensing perturbations from cold dark matter cosmology halos"),
        ])
        _write_day(raw / "2026-09-05.json", "2026-09-05", [
            _raw_paper("2", "dark matter subhalo abundance",
                       "substructure lensing perturbations from cold dark matter cosmology halos"),
            _raw_paper("3", "supernova nebular spectroscopy",
                       "late time oxygen emission lines in a stripped envelope explosion"),
        ])
        result = render_site(CONFIG, out_dir=docs, raw_dir=raw)
        return docs, result

    def test_files_and_index_is_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, result = self._build(tmp)
            self.assertEqual(result, {"days": 2, "newest": "2026-09-05"})
            for rel in ["index.html", "archive/index.html",
                        "archive/2026-09-04.html", "archive/2026-09-05.html",
                        "assets/style.css", "assets/graph.js", "assets/d3.v7.min.js"]:
                self.assertTrue((docs / rel).exists(), rel)
            idx = (docs / "index.html").read_text()
            newest_archive = (docs / "archive/2026-09-05.html").read_text()
            # Same day, same papers -- differ only by link depth + canonical URL.
            self.assertIn("<h1>2026-09-05</h1>", idx)
            self.assertEqual(
                re.findall(r'id="paper-\d+"', idx),
                re.findall(r'id="paper-\d+"', newest_archive),
            )

    def test_relative_links_differ_by_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
            arc = (docs / "archive/2026-09-04.html").read_text()
        self.assertIn('href="assets/style.css"', idx)
        self.assertIn('href="../assets/style.css"', arc)
        self.assertIn('href="archive/index.html"', idx)
        self.assertIn('href="../archive/index.html"', arc)

    def test_embedded_atlas_json_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
        payload = re.search(r'id="atlas-data">(.*?)</script>', idx, re.S).group(1)
        self.assertNotIn("<", payload)
        obj = json.loads(payload)
        self.assertIn("nodes", obj)
        self.assertIn("links", obj)
        self.assertTrue(all("id" in n for n in obj["nodes"]))

    def test_atlas_json_carries_filter_facets(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
        obj = json.loads(re.search(r'id="atlas-data">(.*?)</script>', idx, re.S).group(1))
        self.assertEqual(obj["days"], ["2026-09-05", "2026-09-04"])
        self.assertIn("corpus_categories", obj)
        self.assertIn("astro-ph.CO", obj["corpus_categories"])
        self.assertEqual(obj["repo_url"], "")
        # the maintainer's config set travels for the "use site defaults" button,
        # NOT pre-filled into the fields
        self.assertEqual(obj["site_defaults"]["topics"], "dark matter, cosmology")
        self.assertEqual(obj["site_defaults"]["categories"], "astro-ph.CO")
        for n in obj["nodes"]:
            for key in ("text", "au", "starred", "categories", "keywords",
                        "priority", "first_pubdate", "announce_type", "spotlight"):
                self.assertIn(key, n)
            self.assertNotIn("abstract", n)
            self.assertIsInstance(n["priority"], bool)
            self.assertEqual(n["text"], n["text"].lower())
            self.assertLessEqual(len(n["text"]), 800)

    def test_filter_panel_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
        # the panel is visible now (collapsed abstracts hide from browser find),
        # rendered open so the fields are one glance away
        self.assertIn('<section class="filters" aria-label="View filters">', idx)
        self.assertNotIn('<section class="filters" hidden', idx)
        for f in ("topics", "authors", "categories", "exclude"):
            self.assertEqual(idx.count('name="%s"' % f), 1, f)
        self.assertEqual(idx.count('name="cat"'), 0)
        self.assertEqual(idx.count('name="kw"'), 0)
        # fields start EMPTY, no data-default, config is not pre-filled
        self.assertIn('name="topics" value=""', idx)
        self.assertIn('name="categories" value=""', idx)
        self.assertNotIn('data-default=', idx)
        self.assertNotIn('value="dark matter, cosmology"', idx)
        # save / clear / load-defaults affordances
        self.assertIn('class="filter-save"', idx)
        self.assertIn('class="filter-clear"', idx)
        self.assertIn('filter-load-defaults', idx)
        self.assertIn('name="priority-only"', idx)
        self.assertIn('name="window"', idx)
        self.assertIn('class="filter-warn"', idx)
        self.assertIn("assets/filters.js", idx)
        # atlas-data must be outside the >=2 graph block so filters always see it
        self.assertLess(idx.index('id="atlas-data"'), idx.index('id="atlas-graph"'))

    def test_dedup_paper_2_appears_once_and_not_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
        self.assertEqual(idx.count('id="paper-2"'), 1)
        # paper 2 first appeared on 09-04, newest day is 09-05
        self.assertIn("seen 2026-09-04", idx)

    def test_spotlight_section_lists_matching_papers(self):
        cfg = dict(CONFIG)
        cfg["spotlight"] = [{
            "label": "ML in astro",
            "match": ["neural network", "simulation-based inference"],
        }]
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            docs = Path(tmp) / "docs"
            _write_day(raw / "2026-09-06.json", "2026-09-06", [
                _raw_paper("10", "a convolutional neural network for cosmic shear",
                           "we train a neural network on cosmological simulations"),
                _raw_paper("11", "classical halo mass function",
                           "press-schechter with no learning at all"),
            ])
            render_site(cfg, out_dir=docs, raw_dir=raw)
            idx = (docs / "index.html").read_text()
        self.assertIn('class="spotlight"', idx)
        self.assertIn("ML in astro", idx)
        # matching paper is linked in the section; the non-matching one is not
        self.assertIn('href="#paper-10"', idx)
        self.assertNotIn('href="#paper-11"', idx)
        # the section links, it does not re-emit the card id (no dup DOM ids)
        self.assertEqual(idx.count('id="paper-10"'), 1)
        # the spotlight flag travels in the atlas json
        obj = json.loads(re.search(r'id="atlas-data">(.*?)</script>', idx, re.S).group(1))
        flags = {n["id"]: n["spotlight"] for n in obj["nodes"]}
        self.assertTrue(flags["10"])
        self.assertFalse(flags["11"])

    def test_no_spotlight_key_renders_no_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
        self.assertNotIn('class="spotlight"', idx)

    def test_archive_index_lists_days_reverse_chronological(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            ai = (docs / "archive/index.html").read_text()
        i5 = ai.index("2026-09-05.html")
        i4 = ai.index("2026-09-04.html")
        self.assertLess(i5, i4)

    def test_subjects_render_and_flat_fallback(self):
        subj_cfg = dict(CONFIG)
        subj_cfg["subjects"] = [
            {"label": "Lensing", "match": ["lensing", "substructure", "subhalo"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            _write_day(raw / "2026-09-06.json", "2026-09-06", [
                _raw_paper("20", "substructure lensing perturbations",
                           "cold dark matter subhalo lensing"),
                _raw_paper("21", "more substructure lensing",
                           "subhalo mass function from lensing"),
            ])
            docs = Path(tmp) / "docs"
            render_site(subj_cfg, out_dir=docs, raw_dir=raw)
            with_subjects = (docs / "index.html").read_text()

        self.assertIn('class="subject"', with_subjects)
        self.assertIn('<span class="subject-label">Lensing', with_subjects)

        with tempfile.TemporaryDirectory() as tmp:              # empty -> flat
            docs, _ = self._build(tmp)
            flat = (docs / "index.html").read_text()
        self.assertNotIn('class="subject"', flat)
        self.assertIn('class="cluster"', flat)


class SubjectBuckets(unittest.TestCase):
    def _cluster(self, cid, label, cats, n=3, today=3):
        return {
            "id": cid, "label": label, "today_count": today,
            "papers": [{"id": f"{cid}-{i}", "title": label.replace("/", " "),
                        "categories": list(cats), "primary_category": cats[0]}
                       for i in range(n)],
        }

    CFG = {
        "subjects": [
            {"label": "Lensing", "match": ["lensing", "shear"]},
            {"label": "Cosmology", "match": ["bao", "hubble"]},
        ],
        "particle_only_last": True,
        "site": {"open_subjects": 1, "open_clusters": 1},
    }

    def test_label_match_first_then_other_then_particle(self):
        clusters = [
            self._cluster(0, "weak/lensing/shear/psf", ["astro-ph.CO"]),
            self._cluster(1, "hubble/tension/bao/ladder", ["astro-ph.CO"]),
            self._cluster(2, "galaxy/formation/feedback/disk", ["astro-ph.GA"]),
            self._cluster(3, "quark/gluon/plasma/qcd", ["hep-ph"]),
        ]
        buckets = _subject_buckets(clusters, self.CFG)
        got = {b["label"]: [c["id"] for c in b["clusters"]] for b in buckets}
        self.assertEqual(got["Lensing"], [0])
        self.assertEqual(got["Cosmology"], [1])
        self.assertEqual(got["Other"], [2])
        self.assertEqual(got["Particle physics"], [3])
        # order: config subjects, then Other, then Particle physics
        self.assertEqual([b["label"] for b in buckets],
                         ["Lensing", "Cosmology", "Other", "Particle physics"])

    def test_first_matching_subject_wins(self):
        clusters = [self._cluster(0, "lensing/bao/shear/hubble", ["astro-ph.CO"])]
        buckets = _subject_buckets(clusters, self.CFG)
        self.assertEqual(buckets[0]["label"], "Lensing")

    def test_particle_only_yields_to_a_subject_match(self):
        # gr-qc-only cluster but its label says "lensing" -> Lensing, not last
        clusters = [self._cluster(0, "lensing/waveform/gw/ray", ["gr-qc"])]
        buckets = _subject_buckets(clusters, self.CFG)
        self.assertEqual(buckets[0]["label"], "Lensing")

    def test_empty_subjects_returns_none(self):
        self.assertIsNone(_subject_buckets([self._cluster(0, "x/y", ["astro-ph"])],
                                           {"subjects": []}))
        self.assertIsNone(_subject_buckets([], {}))

    def test_open_flags_follow_config(self):
        clusters = [
            self._cluster(0, "weak/lensing", ["astro-ph.CO"]),
            self._cluster(1, "hubble/bao", ["astro-ph.CO"]),
        ]
        buckets = _subject_buckets(clusters, self.CFG)
        self.assertTrue(buckets[0]["open"])       # open_subjects: 1
        self.assertFalse(buckets[1]["open"])


if __name__ == "__main__":
    unittest.main()
