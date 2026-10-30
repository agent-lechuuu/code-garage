"""`garage accept`: approved proposals move into catalog/<slice>.yaml at the end of their topic's resources, the rest of
the file keeps its layout, and bad proposals change nothing."""
import difflib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import fixture  # noqa: F401 - puts tools/ on sys.path
from garage import catalog, propose

TOPIC = "engineering.ci.github-actions-hardening"


class Accept(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="garage-accept-"))
        shutil.copytree(fixture.ROOT / "catalog", self.tmp / "catalog")
        shutil.copytree(fixture.ROOT / "schema", self.tmp / "schema")
        env = {"GARAGE_REPO": str(self.tmp), "GARAGE_HOME": str(self.tmp / "home")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        cat = catalog.load()
        self.topic = TOPIC if catalog.topic(cat, TOPIC) else cat["topics"][0]["id"]
        self.slice = catalog.topic(cat, self.topic)["slice"]
        self.before = (self.tmp / "catalog" / f"{self.slice}.yaml").read_text(encoding="utf-8")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, **over):
        p = {"proposed": "2026-10-30", "by": "t", "topic": self.topic, "why": "a test proposal for accept",
             "resource": {"name": "acme widget", "url": "https://github.com/acme/widget", "kind": "repo",
                          "license": "MIT", "pushed": "2026-10-01", "tier": 3, "use": "reference",
                          "note": "A note."},
             "status": "proposed", "trust": "n/a", "quality": "Small and tested.", "read_by": "t"}
        p.update(over)
        f = self.tmp / f"{name}.yaml"
        f.write_text(yaml.safe_dump(p, sort_keys=False), encoding="utf-8")
        return f

    def test_moves_the_resource_into_its_topic(self):
        f = self.write("ok")
        r = propose.accept([str(f)])
        self.assertTrue(r["ok"], r)
        self.assertFalse(f.exists())
        cat = catalog.load()
        res = cat["resources"][catalog.normalize_url("https://github.com/acme/widget")]
        self.assertEqual(res["topics"], [self.topic])
        self.assertEqual(res["note"], "A note. Quality: Small and tested.")
        self.assertNotIn("read_by", res)
        after = (self.tmp / "catalog" / f"{self.slice}.yaml").read_text(encoding="utf-8")
        ops = difflib.SequenceMatcher(None, self.before.splitlines(), after.splitlines()).get_opcodes()
        self.assertEqual({o[0] for o in ops}, {"equal", "insert"})  # only added lines; the rest kept as written

    def test_dry_run_and_errors_write_nothing(self):
        f = self.write("ok")
        self.assertTrue(propose.accept([str(f)], dry_run=True)["ok"])
        bad = self.write("bad", topic="no.such.topic")
        long = self.write("long", quality="x" * 600)
        r = propose.accept([str(f), str(bad), str(long)])
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["errors"]), 2, r)
        self.assertTrue(f.exists() and bad.exists() and long.exists())
        self.assertEqual((self.tmp / "catalog" / f"{self.slice}.yaml").read_text(encoding="utf-8"), self.before)

    def test_refuses_an_item_already_in_the_catalog(self):
        cat = catalog.load()
        url = next(iter(cat["resources"].values()))["url"]
        f = self.write("dup", resource={"name": "dup", "url": url, "kind": "repo", "license": "MIT", "tier": 3,
                                        "use": "reference"})
        r = propose.accept([str(f)])
        self.assertFalse(r["ok"])
        self.assertIn("already in the catalog", r["errors"][0])


if __name__ == "__main__":
    unittest.main()
