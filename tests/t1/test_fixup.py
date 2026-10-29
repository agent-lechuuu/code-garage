"""Fix-up pass: one rid per GitHub folder (main/master/HEAD/blob spellings), richer duplicate kept, the MCP servers
licence as its LICENSE says, and nothing generated or secret in git (.gitignore + repo guard)."""
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import fixture
from garage import catalog, validate


class GithubRefs(unittest.TestCase):
    def test_tree_and_blob_refs_become_head(self):
        n = catalog.normalize_url
        head = "https://github.com/anthropics/skills/tree/HEAD/skills/web-artifacts-builder"
        for ref in ("main", "master", "HEAD", "v1.2.0"):
            for kind in ("tree", "blob"):
                self.assertEqual(n(f"https://github.com/anthropics/skills/{kind}/{ref}/skills/web-artifacts-builder/"),
                                 head, (kind, ref))
        self.assertEqual(n("https://GitHub.com/o/r/blob/main/docs/a.md#x"), "https://github.com/o/r/tree/HEAD/docs/a.md")

    def test_sha_ref_kept_and_bare_tree_is_the_repo(self):
        n = catalog.normalize_url
        sha = "0123456789abcdef0123456789abcdef01234567"
        self.assertEqual(n(f"https://github.com/o/r/blob/{sha.upper()}/a"), f"https://github.com/o/r/tree/{sha}/a")
        self.assertEqual(n("https://github.com/o/r/tree/main"), "https://github.com/o/r")
        self.assertEqual(n("https://gitlab.com/o/r/tree/main/a"), "https://gitlab.com/o/r/tree/main/a")   # GitHub only

    def test_path_still_found(self):
        self.assertEqual(catalog.github_repo("https://github.com/o/r/tree/main/skills/x"), ("o/r", "skills/x"))


TWO_SPELLINGS = fixture.BACKEND.replace("url: https://lucia-auth.com/",
                                       "url: https://github.com/example/gpl-sessions/tree/main/src").replace(
    "url: https://github.com/example/gpl-sessions.git", "url: https://github.com/example/gpl-sessions/blob/HEAD/src/")


class Duplicates(unittest.TestCase):
    def test_merge_keeps_richer_entry_and_all_topics(self):
        docs = [{"slice": "a", "topics": [
            {"id": "a.x.one", "resources": [{"name": "thin", "url": "https://github.com/o/r/tree/main/s", "kind": "skill"}]},
            {"id": "a.x.two", "resources": [{"name": "rich", "url": "https://github.com/o/r/tree/HEAD/s/", "kind": "skill",
                                             "license": "MIT", "note": "a long useful note", "stars": 5}]}]}]
        res = catalog.merge(docs)["resources"]
        self.assertEqual(list(res), ["https://github.com/o/r/tree/HEAD/s"])
        r = res["https://github.com/o/r/tree/HEAD/s"]
        self.assertEqual((r["name"], r["license"], r["topics"], r["slice"]), ("rich", "MIT", ["a.x.one", "a.x.two"], "a"))

    def test_validate_refuses_two_spellings_in_one_topic(self):
        with fixture.Garage({"catalog/backend.yaml": TWO_SPELLINGS}), \
                mock.patch.object(validate, "optional", fixture.fake_optional()):
            errors, _ = validate.validate()
        self.assertTrue(any("backend.auth.sessions: resource listed twice "
                            "(https://github.com/example/gpl-sessions/tree/HEAD/src)" in e for e in errors), errors)

    def test_real_catalog_has_no_spelling_duplicates(self):
        cat = catalog.load(fixture.ROOT)
        rids = {r for r in cat["resources"]}
        self.assertFalse([r for r in rids if "/tree/main/" in r or "/tree/master/" in r or "/blob/" in r])
        wab = cat["resources"]["https://github.com/anthropics/skills/tree/HEAD/skills/web-artifacts-builder"]
        self.assertGreaterEqual(len(wab["topics"]), 2)
        import yaml
        pins = yaml.safe_load((fixture.ROOT / "lock" / "pins.yaml").read_text())
        reg = yaml.safe_load((fixture.ROOT / "trust" / "registry.yaml").read_text()) or {}
        self.assertEqual([k for k in pins if catalog.normalize_url(k) != k], [])
        self.assertEqual([k for k in reg if catalog.normalize_url(k) != k], [])


class Licence(unittest.TestCase):
    def test_mcp_filesystem_server(self):
        r = catalog.load(fixture.ROOT)["resources"]["https://github.com/modelcontextprotocol/servers/tree/HEAD/src/filesystem"]
        self.assertEqual(r["license"], "Apache-2.0 AND MIT")   # LICENSE at the pin: MIT -> Apache-2.0, both texts
        self.assertIn("MIT -> Apache-2.0", r["license_note"])
        self.assertTrue(catalog.is_permissive(r["license"]))


class GitHygiene(unittest.TestCase):
    def test_gitignore_covers_generated_files(self):
        if not (fixture.ROOT / ".git").exists():
            self.skipTest("not a git clone")
        probe = ["tools/garage/__pycache__/x.cpython-314.pyc", "x.pyc", ".venv/bin/python", "dist/garage-0.1.0-py3-none-any.whl",
                 "trust/registry.lock", "lock/pins.yaml.tmp", "state/x", "mirror/a", "index/garage.db"]
        p = subprocess.run(["git", "-C", str(fixture.ROOT), "check-ignore", "--no-index", *probe],
                           capture_output=True, text=True)
        self.assertEqual(sorted(p.stdout.split()), sorted(probe))
        keep = ["dist/catalog.json", "dist/index/ai.md", "trust/registry.yaml", "lock/pins.yaml", "tools/garage/_dist"]
        p = subprocess.run(["git", "-C", str(fixture.ROOT), "check-ignore", "--no-index", *keep],
                           capture_output=True, text=True)
        self.assertEqual(p.stdout.split(), [])

    def test_guard_passes_on_the_tree(self):
        if not (fixture.ROOT / ".git").exists():
            self.skipTest("not a git clone")
        p = subprocess.run(["git", "-C", str(fixture.ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, text=True, check=True)
        cwd = os.getcwd()
        try:
            os.chdir(fixture.ROOT)
            self.assertEqual(validate.guard([f for f in p.stdout.split("\n") if f]), [])
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
