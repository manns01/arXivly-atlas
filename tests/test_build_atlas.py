"""Offline unit tests for build_atlas.py.  Run: python -m unittest discover tests"""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from build_atlas import (
    average_linkage,
    build_atlas,
    label_cluster,
    load_window,
    mutual_knn_edges,
    tfidf_matrix,
    tokenize,
)

CFG = {"keywords": ["dark matter", "cosmology"], "similarity": {}}


def _paper(pid, title, abstract, *, score=0, is_today=True, pubdate="2026-09-07"):
    return {
        "id": pid, "title": title, "abstract": abstract,
        "primary_category": "astro-ph.CO", "score": score,
        "is_today": is_today, "first_pubdate": pubdate,
    }


def _write_day(path, pubdate, papers):
    path.write_text(json.dumps({
        "schema_version": 2, "generated_at": "x", "pubdate": pubdate,
        "categories": [], "papers": papers,
    }))


class LoadWindow(unittest.TestCase):
    def test_dedupe_keeps_earliest_and_tags_today(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            _write_day(raw / "2026-09-01.json", "2026-09-01",
                       [{"id": "A", "title": "a", "abstract": "", "score": 1}])
            _write_day(raw / "2026-09-02.json", "2026-09-02",
                       [{"id": "A", "title": "a", "abstract": "", "score": 1},
                        {"id": "B", "title": "b", "abstract": "", "score": 2}])
            pubdate, papers = load_window(raw, window_days=14)
        self.assertEqual(pubdate, "2026-09-02")
        by_id = {p["id"]: p for p in papers}
        self.assertEqual(by_id["A"]["first_pubdate"], "2026-09-01")
        self.assertTrue(by_id["A"]["is_today"])   # A also re-appears on the 2nd
        self.assertTrue(by_id["B"]["is_today"])
        self.assertEqual(len(papers), 2)

    def test_window_truncates_to_n_files(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            for i in range(1, 6):
                _write_day(raw / f"2026-09-0{i}.json", f"2026-09-0{i}",
                           [{"id": f"p{i}", "title": "t", "abstract": "", "score": 0}])
            pubdate, papers = load_window(raw, window_days=3)
        self.assertEqual(pubdate, "2026-09-05")
        self.assertEqual({p["id"] for p in papers}, {"p3", "p4", "p5"})

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_window(Path(d), 14), ("", []))


class Tokenize(unittest.TestCase):
    def test_drops_english_and_short_tokens(self):
        toks = tokenize("We show a New Model of X", extra_stop=set())
        self.assertNotIn("we", toks)
        self.assertNotIn("a", toks)
        self.assertNotIn("x", toks)          # 1-char
        self.assertNotIn("model", toks)      # in the built-in stoplist

    def test_keyword_stoplist_removes_filter_terms(self):
        extra = {"dark", "matter", "cosmology"}
        toks = tokenize("dark matter in cosmology and lensing", extra)
        self.assertEqual(toks, ["lensing"])


class TfidfMatrix(unittest.TestCase):
    def test_rows_l2_normalized(self):
        m, vocab = tfidf_matrix([["alpha", "beta"], ["beta", "gamma", "gamma"]])
        self.assertEqual(vocab, ["alpha", "beta", "gamma"])
        np.testing.assert_allclose(np.linalg.norm(m, axis=1), [1.0, 1.0])

    def test_empty_vocab(self):
        m, vocab = tfidf_matrix([[], []])
        self.assertEqual(vocab, [])
        self.assertEqual(m.shape, (2, 0))


class MutualKnnEdges(unittest.TestCase):
    def test_requires_mutual_and_threshold(self):
        # 0-1 close, 2 far from both.
        cos = np.array([
            [1.0, 0.6, 0.05],
            [0.6, 1.0, 0.04],
            [0.05, 0.04, 1.0],
        ])
        edges = mutual_knn_edges(cos, k=1, threshold=0.08)
        self.assertEqual(edges, [(0, 1, 0.6)])

    def test_threshold_filters_weak_mutual_pair(self):
        cos = np.array([[1.0, 0.05], [0.05, 1.0]])
        self.assertEqual(mutual_knn_edges(cos, k=1, threshold=0.08), [])

    def test_under_two_nodes(self):
        self.assertEqual(mutual_knn_edges(np.array([[1.0]]), k=4, threshold=0.0), [])


class AverageLinkage(unittest.TestCase):
    D = np.array([
        [0.00, 0.10, 0.90],
        [0.10, 0.00, 0.95],
        [0.90, 0.95, 0.00],
    ])

    def test_merges_close_pair_only(self):
        groups = sorted(sorted(g) for g in average_linkage(self.D, 0.5))
        self.assertEqual(groups, [[0, 1], [2]])

    def test_high_threshold_merges_all(self):
        groups = average_linkage(self.D, 0.99)
        self.assertEqual(sorted(groups[0]), [0, 1, 2])

    def test_low_threshold_all_singletons(self):
        groups = sorted(sorted(g) for g in average_linkage(self.D, 0.05))
        self.assertEqual(groups, [[0], [1], [2]])

    def test_average_linkage_uses_mean_distance(self):
        # After merging 0+1, distance to 2 must be mean(0.90, 0.95) = 0.925,
        # so a threshold of 0.92 leaves them apart but 0.93 merges.
        self.assertEqual(len(average_linkage(self.D, 0.92)), 2)
        self.assertEqual(len(average_linkage(self.D, 0.93)), 1)


class LabelCluster(unittest.TestCase):
    def test_picks_distinctive_terms(self):
        docs = [
            ["neutron", "star", "merger", "tidal"],
            ["neutron", "star", "merger", "deformability"],
            ["galaxy", "cluster", "lensing", "shear"],
        ]
        m, vocab = tfidf_matrix(docs)
        label = label_cluster([0, 1], m, vocab)
        self.assertTrue(label)
        self.assertTrue({"neutron", "star", "merger"} & set(label.split("/")))
        self.assertNotIn("galaxy", label.split("/"))


class BuildAtlas(unittest.TestCase):
    def test_zero_papers(self):
        a = build_atlas([], CFG)
        self.assertEqual(a["window_size"], 0)
        self.assertEqual((a["nodes"], a["links"], a["clusters"]), ([], [], []))

    def test_one_paper_is_lone_unclustered_node(self):
        a = build_atlas([_paper("1", "lone", "text about something")], CFG)
        self.assertEqual(len(a["nodes"]), 1)
        self.assertEqual(a["links"], [])
        self.assertEqual(a["clusters"], [])
        self.assertEqual(a["unclustered"], ["1"])
        self.assertEqual(a["nodes"][0]["cluster"], -1)

    def test_three_papers_one_cluster_one_singleton(self):
        papers = [
            _paper("1", "neutron star equation of state",
                   "tidal deformability lambda from gravitational wave signal of merger"),
            _paper("2", "neutron star equation of state",
                   "tidal deformability lambda from gravitational wave observations of mergers"),
            _paper("3", "galaxy cluster weak lensing mass",
                   "shear profile stacking of clusters in a photometric survey"),
        ]
        a = build_atlas(papers, CFG)
        self.assertEqual(len(a["clusters"]), 1)
        self.assertEqual(sorted(a["clusters"][0]["members"]), ["1", "2"])
        self.assertEqual(a["clusters"][0]["today_count"], 2)
        self.assertEqual(a["unclustered"], ["3"])
        self.assertEqual({(l["source"], l["target"]) for l in a["links"]}, {("1", "2")})
        self.assertEqual(a["nodes"][0]["cluster"], a["nodes"][1]["cluster"])
        self.assertEqual(a["nodes"][2]["cluster"], -1)

    def test_keyword_stoplist_keeps_filter_terms_out_of_labels(self):
        papers = [
            _paper("1", "dark matter cosmology halo",
                   "dark matter cosmology substructure subhalo abundance"),
            _paper("2", "dark matter cosmology halo",
                   "dark matter cosmology substructure subhalo mass function"),
        ]
        a = build_atlas(papers, CFG)
        self.assertEqual(len(a["clusters"]), 1)
        label_terms = set(a["clusters"][0]["label"].split("/"))
        self.assertNotIn("dark", label_terms)
        self.assertNotIn("matter", label_terms)
        self.assertNotIn("cosmology", label_terms)

    def test_fixture_window_smoke(self):
        # The real single-day raw file committed by fetch_arxiv.py.
        raw = Path("data/raw")
        if not (raw / "2026-09-07.json").exists():
            self.skipTest("data/raw/2026-09-07.json not present")
        pubdate, papers = load_window(raw, 14)
        a = build_atlas(papers, {
            "keywords": ["gravitational lensing", "dark matter", "cosmology",
                         "gravitational waves"],
            "similarity": {},
        })
        self.assertEqual(a["window_size"], len(papers))
        self.assertGreaterEqual(len(a["clusters"]), 1)
        covered = {n["id"] for n in a["nodes"]}
        clustered = {m for c in a["clusters"] for m in c["members"]}
        self.assertEqual(clustered | set(a["unclustered"]), covered)
        self.assertFalse(clustered & set(a["unclustered"]))


if __name__ == "__main__":
    unittest.main()
