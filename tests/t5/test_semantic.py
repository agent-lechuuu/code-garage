"""T5: search by meaning (garage.semantic + the fusion in garage.search).

The unit tests run a stand-in embedding service in this process (a word-concept model, no numpy, no model files),
so they check the plumbing: vectors built and reused, fusion, filters, -words, the silent fall-back (no service, a
slow one, another model) and the answer cap. RealEval measures the real thing when the server's service answers:
FTS-only against hybrid on tests/eval/needs.yaml, tests/t5/paraphrases.yaml and the owner's ten needs, on one index.
"""
import json
import math
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "t1"))
import fixture  # noqa: E402 - puts tools/ on sys.path
from garage import index, paths, search, semantic  # noqa: E402

CONCEPTS = {"jobs": ["background", "job", "jobs", "deferred", "task", "tasks", "worker", "queue", "queues"],
            "dialog": ["dialog", "dialogs", "popup", "overlay", "popover", "popovers"]}
DIMS = {w: k for k, ws in enumerate(CONCEPTS.values()) for w in ws}


class FakeEmbedder:
    """Counts concept words only: texts that share a concept point the same way, everything else is zero."""
    name = semantic.MODEL

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 384
            for w in re.findall(r"\w+", t.lower()):
                if w in DIMS:
                    v[DIMS[w]] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out

    def query(self, q):
        return self.embed([q])[0]


class Service:
    """garage.semantic.serve in a thread, on a temporary socket."""

    def __init__(self, sock, emb=None):
        self.sock, self.emb, self.srv = sock, emb or FakeEmbedder(), None
        up = threading.Event()

        def ready(srv):
            self.srv = srv
            up.set()
        self.t = threading.Thread(target=semantic.serve, kwargs=dict(sock=sock, emb=self.emb, ready=ready),
                                  daemon=True)
        self.t.start()
        up.wait(5)

    def stop(self):
        self.srv.shutdown()
        self.t.join(5)


class Silent:
    """A socket that accepts and never answers (a hung service)."""

    def __init__(self, sock):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.bind(str(sock))
        self.s.listen(8)

    def stop(self):
        self.s.close()


class Case(unittest.TestCase):
    def setUp(self):
        self.g = fixture.Garage().__enter__()
        self.sock = self.g.home / "run" / "embed.sock"
        self.env = mock.patch.dict(os.environ, {"GARAGE_SEMANTIC": "service"})
        self.env.start()
        os.environ.pop("GARAGE_EMBED_SOCKET", None)
        os.environ.pop("GARAGE_EMBED_MODEL", None)
        semantic._vecs.clear()
        self.svc = None

    def tearDown(self):
        if self.svc:
            self.svc.stop()
        self.env.stop()
        self.g.__exit__(None, None, None)

    def start(self, emb=None):
        self.svc = Service(self.sock, emb)

    def ids(self, q, **kw):
        return [r["id"] for r in search.search(q, **kw)]

    def off(self, q, **kw):
        with mock.patch.dict(os.environ, {"GARAGE_SEMANTIC": "0"}):
            return search.search(q, **kw)


class Plumbing(Case):
    def test_socket_is_open_to_every_user(self):
        self.start()
        self.assertEqual(self.sock.stat().st_mode & 0o777, 0o666)
        self.assertEqual(semantic.ask({"op": "ping"})["model"], semantic.MODEL)

    def test_vectors_built_per_topic_and_reused(self):
        self.start()
        s = index.build()
        self.assertEqual((s["vectors"], s["vectors_new"]), (5, 5))   # the fixture's five topics
        s = index.build()
        self.assertEqual((s["vectors"], s["vectors_new"]), (5, 0))   # unchanged texts: reused from the old index
        c = index.connect()
        try:
            self.assertEqual(c.execute("select v from meta where k = 'vec_model'").fetchone()[0], semantic.MODEL)
            self.assertEqual(c.execute("select count(*) from vec").fetchone()[0], 5)
        finally:
            index.release(c)

    def test_no_service_no_vectors_index_unchanged(self):
        s = index.build()
        self.assertEqual(s.get("vectors"), 0)
        c = index.connect()
        try:
            self.assertIsNone(c.execute("select name from sqlite_master where name = 'vec'").fetchone())
        finally:
            index.release(c)

    def test_off_builds_no_vectors(self):
        self.start()
        with mock.patch.dict(os.environ, {"GARAGE_SEMANTIC": "0"}):
            s = index.build()
        self.assertNotIn("vectors", s)


class Fusion(Case):
    def test_finds_by_meaning_what_words_miss(self):
        self.assertEqual(self.off("deferred task runner"), [])
        self.start()
        index.build()
        self.assertEqual(self.ids("deferred task runner")[0], "backend.jobs.queues")

    def test_keyword_answers_stay_first(self):
        self.start()
        index.build()
        self.assertEqual(self.ids("headless dialog")[0], "frontend.components.headless")
        self.assertEqual(self.ids("auth")[0], "backend.auth.sessions")

    def test_filters_apply_to_vector_results(self):
        self.start()
        index.build()
        self.assertEqual(self.ids("deferred task runner", slice="frontend"), [])
        for r in search.search("popup overlay", kind="template") + search.search("popup overlay", trust="trusted"):
            self.fail(f"a filtered-out topic came back: {r['id']}")

    def test_minus_word_drops_vector_results(self):
        self.start()
        index.build()
        self.assertIn("backend.jobs.queues", self.ids("deferred task runner"))
        self.assertNotIn("backend.jobs.queues", self.ids("deferred task runner -retries"))

    def test_answer_stays_under_the_cap(self):
        from garage import mcp_server
        self.start()
        index.build()
        for q in ("popup overlay dialog", "deferred task runner", "headless dialog react"):
            out = mcp_server.tool_search(q, limit=10)
            self.assertLessEqual(len(out.encode()), mcp_server.LIMIT)
            self.assertTrue(json.loads(out)["results"])


class FallBack(Case):
    QS = ("headless dialog", "auth", "form validation", "deferred task runner", "xyzzyqqq")

    def same_as_off(self):
        for q in self.QS:
            self.assertEqual(search.search(q), self.off(q), q)

    def test_no_service(self):
        self.same_as_off()

    def test_service_gone_after_the_build(self):
        self.start()
        index.build()
        self.svc.stop()
        self.svc = None
        self.same_as_off()

    def test_hung_service_costs_at_most_the_timeout(self):
        self.start()
        index.build()
        self.svc.stop()
        self.svc = None
        self.sock.unlink(missing_ok=True)
        hung = Silent(self.sock)
        try:
            t = time.time()
            r = search.search("headless dialog")
            self.assertLess(time.time() - t, semantic.TIMEOUT + 1.0)
            self.assertEqual(r, self.off("headless dialog"))
        finally:
            hung.stop()

    def test_other_model_is_ignored(self):
        self.start()
        index.build()
        self.svc.stop()
        other = FakeEmbedder()
        other.name = "bge-small-en-v1.5"
        self.svc = Service(self.sock, other)
        self.same_as_off()

    def test_broken_semantic_module_never_breaks_search(self):
        self.start()
        index.build()
        with mock.patch.object(semantic, "vector_hits", side_effect=RuntimeError("boom")):
            self.same_as_off()


class Model(unittest.TestCase):
    def test_pins_are_exact(self):
        for name, m in semantic.MODELS.items():
            self.assertRegex(m["rev"], r"^[0-9a-f]{40}$", name)
            for f, sha in m["files"].items():
                self.assertRegex(sha, r"^[0-9a-f]{64}$", f)

    def test_verify_catches_a_changed_file(self):
        d = Path(tempfile.mkdtemp(prefix="garage-t5-"))
        try:
            for f in semantic.MODELS[semantic.MODEL]["files"]:
                (d / f).write_bytes(b"not the model")
            bad = semantic.verify(d)
            self.assertEqual(len(bad), 3)
            self.assertTrue(all("sha256 mismatch" in b for b in bad))
        finally:
            shutil.rmtree(d)

    def test_requirements_and_extra_are_pinned(self):
        req = (ROOT / "infra" / "install.d" / "15-semantic.requirements.txt").read_text()
        pkgs = [ln for ln in req.splitlines() if ln and not ln.startswith("#")]
        self.assertTrue(pkgs and all(re.fullmatch(r"[\w.-]+==[\w.]+", p) for p in pkgs), pkgs)
        import tomllib
        extra = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]["semantic"]
        pinned = {p.split("==")[0].lower(): p for p in pkgs}
        for p in extra:
            self.assertIn(p, pinned.values(), f"{p} differs from 15-semantic.requirements.txt")
        base = (ROOT / "infra" / "install.d" / "10-base.requirements.txt").read_text()
        for heavy in ("numpy", "onnxruntime", "tokenizers"):
            self.assertNotIn(heavy, base, "the base venv (CLI, MCP, tailnet image) stays light")


def _service_up():
    return os.environ.get("GARAGE_SEMANTIC", "service") != "0" and bool(semantic.ask({"op": "ping"}, timeout=5))


@unittest.skipUnless(_service_up(), f"no embedding service at {semantic.socket_path()} (infra/install.d/15-semantic.sh)")
class RealEval(unittest.TestCase):
    """FTS-only vs hybrid, same tree, same index, same moment. Prints the numbers infra/checks/t5.sh reports."""

    @classmethod
    def setUpClass(cls):
        import yaml
        from garage import catalog, evalset
        cls.evalset = evalset
        real = paths.home()
        cls.tmp = Path(tempfile.mkdtemp(prefix="garage-t5-eval-"))
        home = cls.tmp / "home"
        (home / "index").mkdir(parents=True)
        for d in ("mirror", "quarantine"):
            if (real / d).is_dir():
                (home / d).symlink_to(real / d)
        if paths.index_db().is_file():   # its vectors are reused where the topic text is unchanged
            shutil.copy(paths.index_db(), home / "index" / "garage.db")
        cls.env = mock.patch.dict(os.environ, {"GARAGE_HOME": str(home), "GARAGE_REPO": str(ROOT),
                                               "GARAGE_EMBED_SOCKET": str(semantic.socket_path()),
                                               "GARAGE_SEMANTIC": "service"})
        cls.env.start()
        cls.stats = index.build()
        needs = evalset.load_needs()
        by = {n["q"]: n for n in needs}
        para = yaml.safe_load((ROOT / "tests" / "t5" / "paraphrases.yaml").read_text())["paraphrases"]
        cls.sets = {"needs": needs, "plain": [dict(by[p["of"]], q=p["q"]) for p in para if p["of"] in by]}
        cls.cat = catalog.load()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_set(self, needs, mode):
        with mock.patch.dict(os.environ, {"GARAGE_SEMANTIC": mode}):
            search.search("warm up")
            rows, ts = [], []
            for n in needs:
                t = time.time()
                r = search.search(n["q"], limit=3)
                ts.append(time.time() - t)
                x = self.evalset.score_one(n, r, self.cat)
                x.update(q=n["q"], slice=n["slice"])
                rows.append(x)
        ts.sort()
        return rows, ts[len(ts) // 2], ts[int(len(ts) * 0.95)]

    def test_hybrid_wins_and_keeps_the_owner_needs(self):
        self.assertGreater(self.stats.get("vectors", 0), 0, self.stats)
        out = {}
        for name, needs in self.sets.items():
            fts, f50, f95 = self.run_set(needs, "0")
            hyb, h50, h95 = self.run_set(needs, "service")
            a, b = sum(r["score"] for r in fts), sum(r["score"] for r in hyb)
            up = sum(1 for x, y in zip(fts, hyb) if y["score"] > x["score"])
            down = sum(1 for x, y in zip(fts, hyb) if y["score"] < x["score"])
            out[name] = (a, b, 2 * len(needs), up, down)
            print(f"\nT5 {name}: FTS {a}/{2 * len(needs)} -> hybrid {b} ({up} better, {down} worse); "
                  f"p50 {1000 * f50:.0f} -> {1000 * h50:.0f} ms, p95 {1000 * f95:.0f} -> {1000 * h95:.0f} ms",
                  file=sys.stderr)
        from test_fixup2 import NEEDS
        misses = [q for q, ok in NEEDS for r in [search.search(q, limit=3)] if not (r and ok(r[0], r[0]["best"]))]
        self.assertEqual(misses, [], "owner needs lost with search by meaning on")
        self.assertGreaterEqual(out["needs"][1], out["needs"][0], out)
        self.assertGreaterEqual(out["plain"][1], out["plain"][0] + 4, out)


if __name__ == "__main__":
    unittest.main()
