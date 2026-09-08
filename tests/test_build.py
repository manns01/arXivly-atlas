"""Offline tests for the build.py orchestrator: stage ordering and fail-fast."""

import unittest
from unittest import mock

import build


class Orchestrator(unittest.TestCase):
    def test_missing_date_file_returns_1_without_running_stages(self):
        with mock.patch.object(build.build_atlas, "main") as atlas, \
             mock.patch.object(build.generate_site, "main") as site:
            rc = build.main(["--date", "1999-01-01"])
        self.assertEqual(rc, 1)
        atlas.assert_not_called()
        site.assert_not_called()

    def test_no_date_runs_fetch_then_atlas_then_generate(self):
        calls = []
        with mock.patch.object(build.fetch_arxiv, "main",
                               side_effect=lambda: calls.append("fetch") or 0), \
             mock.patch.object(build.build_atlas, "main",
                               side_effect=lambda: calls.append("atlas") or 0), \
             mock.patch.object(build.generate_site, "main",
                               side_effect=lambda: calls.append("gen") or 0):
            rc = build.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["fetch", "atlas", "gen"])

    def test_fetch_failure_stops_before_atlas(self):
        with mock.patch.object(build.fetch_arxiv, "main", return_value=2), \
             mock.patch.object(build.build_atlas, "main") as atlas, \
             mock.patch.object(build.generate_site, "main") as site:
            rc = build.main([])
        self.assertEqual(rc, 2)
        atlas.assert_not_called()
        site.assert_not_called()

    def test_atlas_failure_stops_before_generate(self):
        with mock.patch.object(build.fetch_arxiv, "main", return_value=0), \
             mock.patch.object(build.build_atlas, "main", return_value=3), \
             mock.patch.object(build.generate_site, "main") as site:
            rc = build.main([])
        self.assertEqual(rc, 3)
        site.assert_not_called()

    def test_date_mode_skips_fetch(self):
        with mock.patch.object(build.Path, "exists", return_value=True), \
             mock.patch.object(build.fetch_arxiv, "main") as fetch, \
             mock.patch.object(build.build_atlas, "main", return_value=0), \
             mock.patch.object(build.generate_site, "main", return_value=0):
            rc = build.main(["--date", "2026-09-07"])
        self.assertEqual(rc, 0)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
