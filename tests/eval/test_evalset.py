"""The evaluation-set scorer (tools/garage/evalset.py): the 2/1/0 rules on synthetic results, and the set itself
names only topics and resources that exist. Run: python3 -I -m unittest discover -s tests/eval -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from garage import evalset  # noqa: E402

CAT = {"topics": [], "resources": {"https://github.com/o/arch": {"archived": True}}}


def row(tid, url, trust="n/a", kind="repo", use="install"):
    return {"id": tid, "best": {"name": url.rsplit("/", 1)[-1], "url": url, "trust": trust, "kind": kind, "use": use}}


class Rules(unittest.TestCase):
    need = {"q": "x", "slice": "s", "ideal": ["a.b.c", "https://github.com/o/good"], "acceptable": ["a.b.d"]}

    def test_ideal_topic_or_rid_scores_two(self):
        self.assertEqual(evalset.score_one(self.need, [row("a.b.c", "https://x/y")], CAT)["score"], 2)
        self.assertEqual(evalset.score_one(self.need, [row("z.z.z", "https://github.com/o/good/")], CAT)["score"], 2)

    def test_acceptable_or_buried_ideal_scores_one(self):
        self.assertEqual(evalset.score_one(self.need, [row("a.b.d", "https://x/y")], CAT)["score"], 1)
        r = evalset.score_one(self.need, [row("z.z.z", "https://x/y"), row("a.b.c", "https://x/y")], CAT)
        self.assertEqual((r["score"], r["reason"]), (1, "ideal at rank 2-3"))

    def test_miss_scores_zero(self):
        self.assertEqual(evalset.score_one(self.need, [row("z.z.z", "https://x/y")], CAT)["score"], 0)
        self.assertEqual(evalset.score_one(self.need, [], CAT)["score"], 0)

    def test_quarantine_runnable_or_archived_pick_caps_at_one(self):
        r = evalset.score_one(self.need, [row("a.b.c", "https://x/y", trust="quarantine", kind="mcp", use="mcp")], CAT)
        self.assertEqual((r["score"], r["relevance"]), (1, 2))
        r = evalset.score_one(self.need, [row("a.b.c", "https://x/y", trust="reviewed", kind="mcp", use="mcp")], CAT)
        self.assertEqual(r["score"], 2)
        r = evalset.score_one(self.need, [row("a.b.c", "https://github.com/o/arch")], CAT)
        self.assertEqual((r["score"], r["reason"]), (1, "top is ideal but its best pick is archived"))

    def test_totals_per_slice(self):
        rows = [{"slice": "a", "score": 2, "relevance": 2}, {"slice": "a", "score": 1, "relevance": 2},
                {"slice": "b", "score": 0, "relevance": 0}]
        tot, mx, per = evalset.totals(rows)
        self.assertEqual((tot, mx, dict(per)), (3, 6, {"a": [3, 4], "b": [0, 2]}))


@unittest.skipUnless((ROOT / "catalog").is_dir(), "no catalog/ (not a checkout)")
class TheSet(unittest.TestCase):
    def test_every_id_and_rid_exists(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"GARAGE_REPO": str(ROOT)}):
            from garage import catalog
            catalog._cache.clear()
            needs = evalset.load_needs()
            self.assertGreaterEqual(len(needs), 60)
            self.assertEqual(evalset.check(needs, catalog.load()), [])
            self.assertEqual(len({n["q"] for n in needs}), len(needs), "duplicate queries")
            slices = {n["slice"] for n in needs}
            self.assertEqual(slices, {"web3", "ai", "systems", "backend", "frontend", "security", "engineering"})


if __name__ == "__main__":
    unittest.main()
