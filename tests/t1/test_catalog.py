"""T1: catalog keys and rules (frozen contracts)."""
import unittest

import fixture
from garage import catalog


class NormalizeUrl(unittest.TestCase):
    def test_contract(self):
        n = catalog.normalize_url
        self.assertEqual(n("HTTPS://GitHub.COM/Radix-UI/Primitives/"), "https://github.com/Radix-UI/Primitives")
        self.assertEqual(n("https://github.com/a/b.git"), "https://github.com/a/b")
        self.assertEqual(n("https://github.com/a/b.git/"), "https://github.com/a/b")
        self.assertEqual(n("https://example.org/docs/#install"), "https://example.org/docs")
        self.assertEqual(n("https://example.org/x?tab=readme#y"), "https://example.org/x?tab=readme")
        self.assertEqual(n("  https://example.org  "), "https://example.org")
        self.assertEqual(n("https://example.org/a/b/"), n("https://example.org/a/b"))

    def test_path_case_kept(self):   # only scheme and host are case-insensitive
        self.assertNotEqual(catalog.normalize_url("https://x.org/A"), catalog.normalize_url("https://x.org/a"))

    def test_github_repo(self):
        g = catalog.github_repo
        self.assertEqual(g("https://github.com/anthropics/skills"), ("anthropics/skills", ""))
        self.assertEqual(g("https://github.com/anthropics/skills/tree/HEAD/skills/pdf"), ("anthropics/skills", "skills/pdf"))
        self.assertEqual(g("https://github.com/o/r/blob/main/a/b.md"), ("o/r", "a/b.md"))
        self.assertEqual(g("https://github.com/o/r.git"), ("o/r", ""))
        self.assertEqual(g("https://github.com/o/r/tree/HEAD/Server%20Side"), ("o/r", "Server Side"))
        self.assertIsNone(g("https://gitlab.com/o/r"))
        self.assertIsNone(g("https://github.com/o"))


class Runnable(unittest.TestCase):
    def test_by_use(self):
        for use in ("skill", "mcp", "plugin", "template", "vendor"):
            self.assertTrue(catalog.is_runnable({"use": use, "kind": "repo"}), use)
        for use in ("install", "reference"):
            self.assertFalse(catalog.is_runnable({"use": use, "kind": "repo"}), use)

    def test_by_kind(self):
        for kind in ("skill", "mcp", "plugin", "template", "snippet"):
            self.assertTrue(catalog.is_runnable({"use": "reference", "kind": kind}), kind)
        for kind in ("repo", "docs", "list", "tool", "codepen"):
            self.assertFalse(catalog.is_runnable({"use": "install", "kind": kind}), kind)

    def test_permissive(self):
        p = catalog.is_permissive
        self.assertTrue(p("MIT") and p("Apache-2.0") and p("MIT OR Apache-2.0") and p("GPL-3.0 OR MIT"))
        self.assertTrue(p("MIT AND BSD-3-Clause"))
        self.assertFalse(p("GPL-3.0") or p("none") or p("NOASSERTION") or p("LicenseRef-Mixed"))
        self.assertFalse(p("MIT AND GPL-2.0"))


class Load(unittest.TestCase):
    def test_shape(self):
        with fixture.Garage() as g:
            cat = catalog.load()
            self.assertEqual(len(cat["topics"]), 5)
            self.assertIn("https://github.com/example/gpl-sessions", cat["resources"])   # .git dropped
            r = cat["resources"]["https://github.com/radix-ui/primitives"]
            self.assertEqual((r["slice"], r["topics"]), ("frontend", ["frontend.components.headless"]))
            self.assertEqual(cat["synonyms"]["auth"], ["authentication", "login", "session"])
            self.assertEqual(cat["generated"], "2026-10-28")
            t = catalog.topics_by_id(cat)["frontend.components.headless"]
            self.assertEqual(t["slice"], "frontend")
            self.assertTrue(all("rid" in x for x in t["resources"]))
            self.assertEqual(catalog.sources(g.repo)[-1].name, "synonyms.yaml")

    def test_dist_fallback(self):
        """No catalog/ folder: load() reads dist/catalog.json (what `garage build` writes)."""
        from unittest import mock
        from garage import index
        with fixture.Garage() as g, mock.patch.object(index, "optional", fixture.fake_optional()):
            index.write_dist(g.repo)
            import shutil
            shutil.rmtree(g.repo / "catalog")
            cat = catalog.load(g.repo)
            self.assertEqual(len(cat["topics"]), 5)
            self.assertIn("https://github.com/radix-ui/primitives", cat["resources"])


if __name__ == "__main__":
    unittest.main()
