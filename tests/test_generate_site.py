"""Offline unit tests for generate_site.py — render synthetic raw days into a
temp docs/ and check structure, relative links, and the embedded atlas JSON.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from generate_site import _json_for_script, _snippet, render_site

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
        for n in obj["nodes"]:
            for key in ("text", "au", "starred", "categories", "keywords",
                        "priority", "first_pubdate", "announce_type"):
                self.assertIn(key, n)
            self.assertNotIn("abstract", n)
            self.assertIsInstance(n["priority"], bool)
            self.assertEqual(n["text"], n["text"].lower())
            self.assertLessEqual(len(n["text"]), 800)

    def test_filter_panel_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            idx = (docs / "index.html").read_text()
        self.assertIn('<section class="filters" hidden', idx)
        for f in ("topics", "authors", "categories", "exclude"):
            self.assertEqual(idx.count('name="%s"' % f), 1, f)
        self.assertEqual(idx.count('name="cat"'), 0)
        self.assertEqual(idx.count('name="kw"'), 0)
        # config values seed the fields (value= and data-default=)
        self.assertIn('value="dark matter, cosmology"', idx)
        self.assertIn('data-default="dark matter, cosmology"', idx)
        self.assertIn('value="astro-ph.CO"', idx)
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
        self.assertIn("first seen 2026-09-04", idx)

    def test_archive_index_lists_days_reverse_chronological(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, _ = self._build(tmp)
            ai = (docs / "archive/index.html").read_text()
        i5 = ai.index("2026-09-05.html")
        i4 = ai.index("2026-09-04.html")
        self.assertLess(i5, i4)


if __name__ == "__main__":
    unittest.main()
