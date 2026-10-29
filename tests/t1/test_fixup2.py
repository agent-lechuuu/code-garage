"""T1 (second fix-up): off-server pins and trust from the package's bundled catalog, install hints for packages, and
propose refusing unknown topics."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fixture  # noqa: F401 - puts tools/ on sys.path
from garage import catalog, pins, search, trust

# The owner's ten real needs (2026-10-29 end-to-end test): the expected topic family or kind of answer, never an exact
# item, so the catalog can improve without breaking this. Each check gets (top result, its best resource).
NEEDS = [
    ("Solidity ERC-4626 vault", lambda t, b: "erc4626" in t["id"] and "test" not in b["name"].lower()),
    ("Solana Anchor testing", lambda t, b: t["id"].startswith("web3.solana.") and
     any(w in t["id"] for w in ("testing", "anchor", "security-tools"))),
    ("zero-downtime Postgres migration", lambda t, b: t["id"].startswith("backend.safe-db.")),
    ("bash strict mode", lambda t, b: "strict-mode" in t["id"]),
    ("low-latency ring buffer C++", lambda t, b: t["id"].startswith("systems.concurrency.") and
     "java" not in b["name"].lower()),
    ("OWASP input validation", lambda t, b: "input-validation" in t["id"] and "cheat sheet" in b["name"].lower()),
    ("landing page hero animation", lambda t, b: t["id"].startswith(("frontend.components.animated", "frontend.anim"))),
    ("Claude skill for code review", lambda t, b: "code-review" in t["id"] and "skill" in (b["kind"], b["use"])),
    ("MCP server for Postgres", lambda t, b: "mcp" in (b["kind"], b["use"]) and "mcp" in t["id"]),
    ("rate limiting algorithm", lambda t, b: "rate-limiting" in t["id"]),
]

DIST = fixture.ROOT / "dist" / "catalog.json"
REVIEWED = "https://github.com/obra/superpowers/tree/HEAD/skills/test-driven-development"
TRUSTED = "https://github.com/anthropics/skills/tree/HEAD/skills/frontend-design"


@unittest.skipUnless(DIST.is_file(), "no dist/catalog.json (run garage build)")
class OffServer(unittest.TestCase):
    """A pip/uvx install: no repo at $GARAGE_REPO, only garage/_dist/catalog.json inside the package."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="garage-off-"))
        self.old = {k: os.environ.get(k) for k in ("GARAGE_REPO", "GARAGE_HOME", "GARAGE_UNATTENDED")}
        os.environ["GARAGE_REPO"] = str(self.tmp / "no-repo")
        os.environ["GARAGE_HOME"] = str(self.tmp / "home")
        os.environ.pop("GARAGE_UNATTENDED", None)
        self.packaged = self.tmp / "pkg" / "catalog.json"
        self.packaged.parent.mkdir()
        shutil.copy(DIST, self.packaged)
        self.patch = mock.patch.object(catalog, "PACKAGED", self.packaged)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pins_and_trust_come_from_the_bundled_catalog(self):
        self.assertEqual(catalog.dist_file(), self.packaged)
        pin = pins.get(REVIEWED)
        self.assertTrue(pin and len(pin["sha"]) == 40, pin)
        self.assertEqual(trust.tier(REVIEWED), "reviewed")
        self.assertTrue(trust.allowed(REVIEWED, unattended=False)[0])
        self.assertFalse(trust.allowed(REVIEWED, unattended=True)[0])
        self.assertEqual(trust.tier(TRUSTED), "trusted")
        self.assertTrue(trust.allowed(TRUSTED, unattended=True)[0])
        cat = catalog.load()
        q = next(rid for rid, r in cat["resources"].items()
                 if catalog.is_runnable(r) and rid not in trust.load() and pins.get(rid))
        self.assertEqual(trust.tier(q), "quarantine")
        self.assertFalse(trust.allowed(q, unattended=False)[0])

    def test_a_repo_with_its_own_catalog_never_reads_the_bundled_one(self):
        with fixture.Garage() as g:
            self.assertIsNone(catalog.dist_file(g.repo))
            self.assertEqual(pins.load(g.repo), {})


class OwnerNeeds(unittest.TestCase):
    """Search quality regression on the real catalog (no mirror: as CI and a fresh install see it)."""

    def test_the_ten_needs(self):
        misses = []
        with fixture.Garage(), mock.patch.dict("os.environ", {"GARAGE_REPO": str(fixture.ROOT)}):
            for q, ok in NEEDS:
                r = search.search(q, limit=3)
                if not r or not ok(r[0], r[0]["best"]):
                    misses.append(f"{q!r} -> {r[0]['id'] + ' / ' + r[0]['best']['name'] if r else 'nothing'}")
        self.assertEqual(misses, [], "\n".join(misses))

    def test_intent_words_only_rank(self):
        core, langs, kinds = search.intent(["mcp", "server", "postgres"])
        self.assertEqual((core, langs, kinds), (["postgres"], set(), {"mcp"}))
        pos, _ = search.terms_of("low-latency ring buffer C++", {"ring buffer": ["spsc"]})
        self.assertEqual(pos, ["low", "latency", "ring buffer", "cpp"])
        self.assertEqual(search.intent(pos)[:2], (["ring buffer"], {"cpp"}))


class InstallHints(unittest.TestCase):
    def line(self, **res):
        res.setdefault("use", "install")
        res.setdefault("kind", "repo")
        return search.install_line(res)

    def test_curated_and_registry_lines_win(self):
        self.assertEqual(self.line(url="https://github.com/a/b", install="npm i b"), "npm i b")
        self.assertEqual(self.line(url="https://pypi.org/project/httpx/"), "pip install httpx")

    def test_note_command_only_for_this_package(self):
        self.assertEqual(self.line(name="anthropics/anthropic-sdk-python", url="https://github.com/anthropics/"
                                   "anthropic-sdk-python", note="Official SDK; pip install anthropic."),
                         "pip install anthropic")
        r = self.line(name="npq", url="https://github.com/lirantal/npq", note="Audits before npm install runs.")
        self.assertEqual(r, "install as its README says: https://github.com/lirantal/npq")
        r = self.line(name="Foo", url="https://github.com/o/foo", note="Like bar; pip install bar is the other one.")
        self.assertTrue(r.startswith("install as its README says"), r)

    def test_scoped_npm_name(self):
        self.assertEqual(self.line(name="@upstash/ratelimit", url="https://github.com/upstash/ratelimit-js"),
                         "npm install @upstash/ratelimit")
        self.assertTrue(self.line(name="@solana/web3.js v3", url="https://github.com/x/y").startswith("install as"))

    def test_every_package_gets_a_hint_never_a_mirror_path(self):
        with fixture.Garage():
            for res in catalog.load()["resources"].values():
                if res.get("use") == "install" and not catalog.is_runnable(res):
                    line = search.install_line(res)
                    self.assertTrue(line and "/mirror/" not in line, (res["rid"], line))


if __name__ == "__main__":
    unittest.main()
