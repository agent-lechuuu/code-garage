"""T1: search ranking, synonyms, AND-then-OR, filters, trust fallback, answer size, show/resolve."""
import json
import types
import unittest
from unittest import mock

import fixture
from garage import index, search


class SearchCase(unittest.TestCase):
    mods = {}

    def setUp(self):
        self.g = fixture.Garage().__enter__()
        self.p = mock.patch.object(index, "optional", fixture.fake_optional(**self.mods))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.g.__exit__(None, None, None)

    def ids(self, q, **kw):
        return [r["id"] for r in search.search(q, **kw)]


class Ranking(SearchCase):
    def test_title_beats_body(self):
        self.assertEqual(self.ids("headless dialog")[0], "frontend.components.headless")

    def test_best_resource_and_shape(self):
        r = search.search("headless react dialog")[0]
        self.assertEqual(set(r), {"id", "title", "why", "score", "best"})
        self.assertEqual(set(r["best"]), {"name", "url", "kind", "use", "license", "trust", "install", "local_path"})
        self.assertEqual(r["best"]["name"], "Radix Primitives")   # tier 1 and the note matches
        self.assertEqual(r["best"]["install"], "npm install @radix-ui/react-dialog")
        self.assertEqual(r["best"]["trust"], "n/a")

    def test_synonyms(self):
        self.assertEqual(self.ids("auth")[0], "backend.auth.sessions")       # auth -> authentication, login, session
        self.assertIn("frontend.components.headless", self.ids("modal"))     # modal -> dialog

    def test_and_then_or(self):
        # no single row has both words: AND finds nothing, OR still answers
        ids = self.ids("bullmq zod")
        self.assertEqual(set(ids), {"backend.jobs.queues", "frontend.forms.validation"})

    def test_stemmed_last_word(self):   # a prefix query on the last word is not stemmed: "queues" must still match
        self.assertEqual(self.ids("job queues")[0], "backend.jobs.queues")
        self.assertEqual(self.ids("valid")[0], "frontend.forms.validation")   # half typed

    def test_not(self):
        self.assertNotIn("backend.auth.sessions", self.ids("session -login -authentication -cookie"))

    def test_empty(self):
        self.assertEqual(search.search("   "), [])
        self.assertEqual(search.search("xyzzyqqq"), [])


class Filters(SearchCase):
    def test_kind_use_slice(self):
        self.assertEqual(self.ids("form", kind="template"), ["frontend.forms.validation"])
        r = search.search("form", kind="template")[0]
        self.assertEqual(r["best"]["name"], "Form starter template")   # the filter decides `best`
        self.assertEqual(self.ids("session", use="install"), [])
        self.assertEqual(self.ids("form validation", slice="backend"), [])

    def test_license(self):
        r = search.search("session", license="permissive")
        self.assertEqual(r[0]["best"]["name"], "Lucia guide")
        r = search.search("session", license="GPL")
        self.assertEqual(r[0]["best"]["name"], "GPL session server")

    def test_trust_filter(self):
        self.assertEqual(self.ids("frontend", trust="quarantine"), ["frontend.agent.skills", "frontend.forms.validation"])


class TrustFallback(SearchCase):
    def test_without_trust_module(self):
        r = search.search("frontend design skill")[0]
        self.assertEqual(r["best"]["trust"], "quarantine")   # runnable, no trust module: the safe value
        self.assertEqual(search.search("bullmq")[0]["best"]["trust"], "n/a")


class TrustModule(SearchCase):
    mods = {"trust": types.SimpleNamespace(tier=lambda rid: "reviewed")}

    def test_tier_from_module(self):
        self.assertEqual(search.search("frontend design skill")[0]["best"]["trust"], "reviewed")
        self.assertEqual(search.search("bullmq")[0]["best"]["trust"], "n/a")


class Mirror(SearchCase):
    def setUp(self):
        super().setUp()
        snap = self.g.home / "mirror" / "example__skills" / "abc" / "skills" / "frontend-design"
        snap.mkdir(parents=True)
        (snap / "SKILL.md").write_text("---\nname: frontend-design\n---\nUse bold typography and zanzibarite colors.\n")
        (snap / "app.js").write_text("const x = 1;\nfunction zanzibarite() { return 42 }\n")
        self.snap = snap
        mirror = types.SimpleNamespace(
            local_path=lambda rid: str(snap) if rid.endswith("frontend-design") else None)
        self.p.stop()
        self.p = mock.patch.object(index, "optional", fixture.fake_optional(mirror=mirror))
        self.p.start()

    def test_mirror_chunks_are_searched(self):
        r = search.search("zanzibarite")
        self.assertEqual(r[0]["id"], "frontend.agent.skills")
        self.assertEqual(r[0]["best"]["local_path"], str(self.snap))

    def test_grep(self):
        r = search.grep("frontend.agent.skills", r"zanzi\w+\(")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["matches"], [{"file": "app.js", "line": 2, "text": "function zanzibarite() { return 42 }"}])
        with mock.patch.object(search.shutil, "which", lambda _: None):   # the Python fallback finds the same
            r2 = search.grep("frontend.agent.skills", r"zanzi\w+\(")
        self.assertEqual(r2["matches"], r["matches"])
        self.assertFalse(search.grep("backend.jobs.queues", "x")["ok"])   # not mirrored


class ShowResolve(SearchCase):
    def test_resolve(self):
        t, rs = search.resolve("frontend.forms.validation")
        self.assertEqual((t["id"], len(rs)), ("frontend.forms.validation", 2))
        self.assertEqual(search.resolve("https://github.com/radix-ui/primitives/")[1][0]["name"], "Radix Primitives")
        self.assertEqual(search.resolve("taskforcesh/bullmq")[1][0]["name"], "BullMQ")
        self.assertEqual(search.resolve("example/skills")[1][0]["name"], "frontend-design skill")
        self.assertEqual(search.resolve("zod")[1][0]["url"], "https://www.npmjs.com/package/zod")
        self.assertEqual(search.resolve("nope"), (None, []))

    def test_show(self):
        d = search.show("frontend.components.headless")
        self.assertEqual(d["see_also"], ["frontend.forms.validation"])
        self.assertEqual(len(d["practices"]), 1)
        self.assertEqual(d["resources"][0]["install"], "npm install @radix-ui/react-dialog")
        z = search.show("zod")
        self.assertEqual((z["install"], z["topics"]), ("npm install zod", ["frontend.forms.validation"]))
        s = search.show("frontend.agent.skills")["resources"][0]
        self.assertEqual(s["trust"], "quarantine")
        self.assertTrue(search.show("https://github.com/example/skills/tree/HEAD/skills/frontend-design")["runnable"])
        self.assertTrue(s["install"].startswith("garage skill add "))
        self.assertEqual(search.show("nope"), {})


class StaleIndex(SearchCase):
    def test_reader_serves_a_stale_index(self):
        index.build()
        import os
        import time
        f = self.g.repo / "catalog" / "backend.yaml"
        f.write_text(f.read_text().replace("Background job queues", "Background job queues and workers"))
        os.utime(f, (time.time() + 5, time.time() + 5))
        with mock.patch.object(index.os, "access", lambda *a: False):   # not ours to write
            self.assertEqual(self.ids("queues")[0], "backend.jobs.queues")
            self.assertTrue(index.state["stale"])
        self.assertEqual(self.ids("workers")[0], "backend.jobs.queues")   # ours again: rebuilt, fresh
        self.assertFalse(index.state["stale"])


class RealCatalog(unittest.TestCase):
    """The full catalog: answers stay under 3 KB (agents' context) and the obvious query finds its topic."""

    def test_size_and_hit(self):
        with fixture.Garage() as g, mock.patch.dict("os.environ", {"GARAGE_REPO": str(fixture.ROOT)}):
            for q in ("headless dialog react", "postgres migrations linter", "mcp server for github", "auth"):
                r = search.search(q)
                self.assertEqual(len(r), 5, q)
                self.assertLessEqual(len(json.dumps(r).encode()), 3072, q)
            self.assertEqual(search.search("postgres migration linter")[0]["id"], "backend.safe-db.migration-linters")
            self.assertEqual(search.search("background jobs node")[0]["id"], "backend.jobs.queues-node")
            self.assertLessEqual(len(json.dumps(search.show("ai.skills.workflow-packs"), ensure_ascii=False).encode()), 3072)
            del g


if __name__ == "__main__":
    unittest.main()
